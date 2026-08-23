import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis_client import redis_client
from app.core.ws_manager import manager
from app.models import ShowSeat, SeatStatus


def _hold_key(show_id, seat_id) -> str:
    return f"hold:{show_id}:{seat_id}"


class SeatConflictError(Exception):
    def __init__(self, seat_id):
        super().__init__(f"Seat {seat_id} is no longer available")
        self.seat_id = seat_id


async def place_hold(db: Session, show_id: uuid.UUID, seat_ids: list[uuid.UUID], user_id: uuid.UUID):
    """
    Concurrency guard: Redis SETNX on hold:{show_id}:{seat_id} is atomic --
    if two customers hit the same seat at the same instant, only one SETNX
    call succeeds. That's the single source of truth for "who holds this
    seat right now"; Postgres is updated afterward purely to reflect status
    for reads (seat map, admin views).
    All-or-nothing: if any requested seat fails to lock, every lock already
    acquired in this call is released before returning the conflict.
    """
    ttl = settings.seat_hold_ttl_seconds
    acquired: list[str] = []

    try:
        for seat_id in seat_ids:
            key = _hold_key(show_id, seat_id)
            got_lock = await redis_client.set(key, str(user_id), nx=True, ex=ttl)
            if not got_lock:
                raise SeatConflictError(seat_id)
            acquired.append(key)

            # Redis lock won -- now confirm this seat isn't already BOOKED
            # (a booked seat's redis key was deleted at booking time, so a
            # fresh SETNX on it would otherwise succeed incorrectly).
            show_seat = db.query(ShowSeat).filter(
                ShowSeat.show_id == show_id, ShowSeat.seat_id == seat_id
            ).first()
            if not show_seat or show_seat.status != SeatStatus.available:
                raise SeatConflictError(seat_id)
    except SeatConflictError:
        if acquired:
            await redis_client.delete(*acquired)
        raise

    expires_at = datetime.utcnow() + timedelta(seconds=ttl)
    updated = []
    for seat_id in seat_ids:
        show_seat = db.query(ShowSeat).filter(
            ShowSeat.show_id == show_id, ShowSeat.seat_id == seat_id
        ).first()
        show_seat.status = SeatStatus.held
        show_seat.held_by_user_id = user_id
        show_seat.hold_expires_at = expires_at
        updated.append(show_seat)
    db.commit()
    for s in updated:
        db.refresh(s)

    await manager.broadcast_seat_update(
        str(show_id), [{"seat_id": str(s.seat_id), "status": "held"} for s in updated]
    )
    return updated, expires_at


async def release_hold(db: Session, show_id: uuid.UUID, seat_ids: list[uuid.UUID], user_id: uuid.UUID):
    """Explicit release on checkout abandonment (vs. waiting for TTL expiry)."""
    released = []
    for seat_id in seat_ids:
        key = _hold_key(show_id, seat_id)
        current_holder = await redis_client.get(key)
        if current_holder != str(user_id):
            continue  # not held, or held by someone else -- skip silently

        await redis_client.delete(key)
        show_seat = db.query(ShowSeat).filter(
            ShowSeat.show_id == show_id, ShowSeat.seat_id == seat_id
        ).first()
        if show_seat and show_seat.status == SeatStatus.held:
            show_seat.status = SeatStatus.available
            show_seat.held_by_user_id = None
            show_seat.hold_expires_at = None
            released.append(show_seat)
    db.commit()

    if released:
        await manager.broadcast_seat_update(
            str(show_id), [{"seat_id": str(s.seat_id), "status": "available"} for s in released]
        )
    return released
