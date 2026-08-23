import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.redis_client import redis_client
from app.core.ws_manager import manager
from app.models import ShowSeat, SeatStatus, Booking, BookingStatus, Show, Event, WaitlistEntry, WaitlistStatus, User
from app.services.waitlist_service import try_assign_or_release


class CheckoutError(Exception):
    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


async def checkout(db: Session, show_id: uuid.UUID, seat_ids: list[uuid.UUID], user_id: uuid.UUID) -> Booking:
    """
    Converts an active hold into a confirmed booking.
    Re-validates against both sources of truth before committing:
      1. Redis -- the hold key must still exist AND belong to this user
         (catches TTL expiry that happened a split second before checkout).
      2. Postgres -- SELECT ... FOR UPDATE locks each ShowSeat row so no
         concurrent process (another checkout, a cancellation, an expiry
         worker) can mutate it while this transaction decides its fate --
         the second safety net on top of the Redis lock from Feature 4.
    Both must agree the seat is HELD by this user or the whole checkout is
    rejected -- no partial bookings.
    """
    for seat_id in seat_ids:
        holder = await redis_client.get(f"hold:{show_id}:{seat_id}")
        if holder != str(user_id):
            raise CheckoutError(f"Hold on seat {seat_id} is no longer valid")

    show_seats = (
        db.query(ShowSeat)
        .filter(ShowSeat.show_id == show_id, ShowSeat.seat_id.in_(seat_ids))
        .with_for_update()
        .all()
    )
    if len(show_seats) != len(seat_ids):
        raise CheckoutError("One or more seats not found")

    for ss in show_seats:
        if ss.status != SeatStatus.held or ss.held_by_user_id != user_id:
            raise CheckoutError(f"Seat {ss.seat_id} is no longer held by you")

    booking = Booking(user_id=user_id, show_id=show_id, status=BookingStatus.confirmed)
    db.add(booking)
    db.flush()  # get booking.id

    for ss in show_seats:
        ss.status = SeatStatus.booked
        ss.booking_id = booking.id
        ss.held_by_user_id = None
        ss.hold_expires_at = None

    db.commit()
    db.refresh(booking)

    # Seat is booked now -- delete the redis hold key so it can't spuriously
    # expire later and flip a BOOKED seat back to AVAILABLE.
    keys = [f"hold:{show_id}:{seat_id}" for seat_id in seat_ids]
    await redis_client.delete(*keys)

    await manager.broadcast_seat_update(
        str(show_id), [{"seat_id": str(ss.seat_id), "status": "booked"} for ss in show_seats]
    )
    return booking


def get_booking_history(db: Session, user_id: uuid.UUID) -> list[Booking]:
    return (
        db.query(Booking)
        .filter(Booking.user_id == user_id)
        .order_by(Booking.created_at.desc())
        .all()
    )


async def cancel_booking(db: Session, booking_id: uuid.UUID, user_id: uuid.UUID) -> Booking:
    booking = db.query(Booking).filter(Booking.id == booking_id).with_for_update().first()
    if not booking or booking.user_id != user_id:
        raise CheckoutError("Booking not found")
    if booking.status != BookingStatus.confirmed:
        raise CheckoutError("Booking already cancelled")

    booking.status = BookingStatus.cancelled
    booking.cancelled_at = datetime.utcnow()

    show_seats = db.query(ShowSeat).filter(ShowSeat.booking_id == booking.id).all()
    broadcast_updates = []
    offers_to_notify = []  # (waitlist_entry, show_seat) pairs that need an email
    for ss in show_seats:
        # Check the waitlist for this seat's category before freeing it --
        # if someone's waiting, they get a time-limited offer on this exact
        # seat instead of it going straight back to AVAILABLE.
        new_status = await try_assign_or_release(db, ss)
        broadcast_updates.append({"seat_id": str(ss.seat_id), "status": new_status})

        if new_status == "held":
            entry = (
                db.query(WaitlistEntry)
                .filter(WaitlistEntry.offered_seat_id == ss.seat_id, WaitlistEntry.status == WaitlistStatus.offered)
                .order_by(WaitlistEntry.created_at.desc())
                .first()
            )
            if entry:
                offers_to_notify.append(entry)

    db.commit()

    await manager.broadcast_seat_update(str(booking.show_id), broadcast_updates)

    for entry in offers_to_notify:
        await _send_waitlist_offer_notification(db, entry)

    return booking


async def _send_waitlist_offer_notification(db: Session, entry: WaitlistEntry) -> None:
    """Looks up the waiting customer's email and the show/seat details, then
    fires the time-limited-offer email. Isolated so a bad email address or
    SMTP hiccup can't roll back the cancellation/offer itself -- errors here
    are logged, not raised."""
    import logging
    from app.services.email_service import send_waitlist_offer_email

    logger = logging.getLogger("waitlist")
    try:
        user = db.get(User, entry.user_id)
        claim_url = f"{_frontend_url()}/waitlist"
        await send_waitlist_offer_email(
            to_email=user.email,
            claim_url=claim_url,
            expires_at=str(entry.offer_expires_at),
        )
    except Exception:
        logger.exception("[email] FAILED to send waitlist offer notification")


def _frontend_url() -> str:
    from app.core.config import settings

    return settings.frontend_url.rstrip("/")
