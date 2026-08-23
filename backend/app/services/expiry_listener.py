import asyncio
import logging

from app.core.redis_client import redis_client
from app.core.ws_manager import manager
from app.database import SessionLocal
from app.models import ShowSeat, SeatStatus

logger = logging.getLogger(__name__)


def _sync_release_expired(show_id: str, seat_id: str):
    """Runs in a worker thread (via asyncio.to_thread) since SQLAlchemy here is sync."""
    db = SessionLocal()
    try:
        show_seat = db.query(ShowSeat).filter(
            ShowSeat.show_id == show_id, ShowSeat.seat_id == seat_id
        ).first()
        # Only release if still HELD -- if the customer already checked out,
        # the booking flow (Feature 5) will have set it to BOOKED and deleted
        # the Redis key itself, so this event either won't fire or is a no-op.
        if show_seat and show_seat.status == SeatStatus.held:
            show_seat.status = SeatStatus.available
            show_seat.held_by_user_id = None
            show_seat.hold_expires_at = None
            db.commit()
            return True
        return False
    finally:
        db.close()


async def _handle_waitlist_offer_expiry(entry_id: str):
    """Cascades an unclaimed waitlist offer to the next person in line (or
    releases the seat if the queue is now empty), broadcasts the resulting
    seat status, and emails the next person their own time-limited offer.
    Kept on the main event loop (not a worker thread) since it needs to
    await the shared async Redis client -- spinning up a second event loop
    in a thread for that client risks cross-loop connection errors."""
    from app.services.waitlist_service import expire_offer, WaitlistEntry, WaitlistStatus
    from app.models import User, Show

    db = SessionLocal()
    try:
        result = await expire_offer(db, entry_id)
        if not result:
            return
        seat_id, new_status = result
        seat_id = str(seat_id)

        show_seat = db.query(ShowSeat).filter(ShowSeat.seat_id == seat_id).first()
        show_id = str(show_seat.show_id) if show_seat else None
        if show_id:
            await manager.broadcast_seat_update(show_id, [{"seat_id": seat_id, "status": new_status}])

        if new_status != "held":
            return

        next_entry = (
            db.query(WaitlistEntry)
            .filter(WaitlistEntry.offered_seat_id == seat_id, WaitlistEntry.status == WaitlistStatus.offered)
            .order_by(WaitlistEntry.created_at.desc())
            .first()
        )
        if not next_entry:
            return

        user = db.get(User, next_entry.user_id)
        try:
            from app.services.email_service import send_waitlist_offer_email
            from app.core.config import settings

            await send_waitlist_offer_email(
                to_email=user.email,
                claim_url=f"{settings.frontend_url.rstrip('/')}/waitlist",
                expires_at=str(next_entry.offer_expires_at),
            )
        except Exception:
            logger.exception("[email] FAILED to send cascaded waitlist offer notification")
    finally:
        db.close()


async def start_expiry_listener():
    """
    Subscribes to Redis keyspace notifications for expired keys (requires
    `notify-keyspace-events Ex`, already set in docker-compose.yml). Handles
    two kinds of expiry:
      - hold:{show_id}:{seat_id} -- a customer's seat-hold TTL ran out
        without checking out -> flip the seat back to AVAILABLE.
      - waitlist_offer:{entry_id} -- a waitlist offer's time-limited window
        ran out unclaimed -> cascade the seat to the next person in line
        (or release it if nobody's left waiting), and email that next
        person their own time-limited offer.
    Either way, broadcasts the resulting seat status over the show's
    WebSocket so every connected seat map updates in real time.
    """
    pubsub = redis_client.pubsub()
    await pubsub.psubscribe("__keyevent@0__:expired")
    logger.info("Seat-hold / waitlist-offer expiry listener started")

    async for message in pubsub.listen():
        if message["type"] != "pmessage":
            continue
        expired_key = message["data"]

        if expired_key.startswith("hold:"):
            try:
                _, show_id, seat_id = expired_key.split(":", 2)
            except ValueError:
                continue
            released = await asyncio.to_thread(_sync_release_expired, show_id, seat_id)
            if released:
                await manager.broadcast_seat_update(show_id, [{"seat_id": seat_id, "status": "available"}])

        elif expired_key.startswith("waitlist_offer:"):
            _, entry_id = expired_key.split(":", 1)
            await _handle_waitlist_offer_expiry(entry_id)