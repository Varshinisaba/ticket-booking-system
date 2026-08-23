import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis_client import redis_client
from app.models import (
    WaitlistEntry,
    WaitlistStatus,
    ShowSeat,
    SeatStatus,
    Seat,
    Booking,
    BookingStatus,
)


def _offer_key(entry_id) -> str:
    return f"waitlist_offer:{entry_id}"


class WaitlistError(Exception):
    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def join_waitlist(db: Session, show_id: uuid.UUID, category: str, user_id: uuid.UUID) -> WaitlistEntry:
    """
    Only makes sense once the category is actually sold out -- if seats are
    still available the customer should just book directly, so we reject
    the join instead of silently queueing them behind nothing.
    One active entry per (user, show, category) at a time.
    """
    available_exists = (
        db.query(ShowSeat)
        .join(Seat, ShowSeat.seat_id == Seat.id)
        .filter(
            ShowSeat.show_id == show_id,
            Seat.category == category,
            ShowSeat.status == SeatStatus.available,
        )
        .first()
    )
    if available_exists:
        raise WaitlistError(f"Category '{category}' still has available seats -- book directly instead")

    existing = (
        db.query(WaitlistEntry)
        .filter(
            WaitlistEntry.show_id == show_id,
            WaitlistEntry.category == category,
            WaitlistEntry.user_id == user_id,
            WaitlistEntry.status.in_([WaitlistStatus.waiting, WaitlistStatus.offered]),
        )
        .first()
    )
    if existing:
        raise WaitlistError("You're already on the waitlist for this category")

    entry = WaitlistEntry(show_id=show_id, category=category, user_id=user_id, status=WaitlistStatus.waiting)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


async def try_assign_or_release(db: Session, show_seat: ShowSeat) -> str:
    """
    Called whenever a seat becomes free -- either a fresh cancellation, or a
    waitlist offer itself expiring unclaimed (that's the cascade-to-next-
    person case). FIFO: earliest 'waiting' entry for this show+category wins.
    Sets the seat back to HELD (reserved for that one person, TTL-limited)
    rather than AVAILABLE if someone's waiting. Returns the resulting status
    string ("held" or "available") so the caller knows what to broadcast.
    """
    seat = db.get(Seat, show_seat.seat_id)
    next_entry = (
        db.query(WaitlistEntry)
        .filter(
            WaitlistEntry.show_id == show_seat.show_id,
            WaitlistEntry.category == seat.category,
            WaitlistEntry.status == WaitlistStatus.waiting,
        )
        .order_by(WaitlistEntry.created_at.asc())
        .with_for_update()
        .first()
    )

    if not next_entry:
        show_seat.status = SeatStatus.available
        show_seat.held_by_user_id = None
        show_seat.hold_expires_at = None
        db.commit()
        return "available"

    ttl = settings.waitlist_offer_ttl_seconds
    expires_at = datetime.utcnow() + timedelta(seconds=ttl)

    show_seat.status = SeatStatus.held
    show_seat.held_by_user_id = next_entry.user_id
    show_seat.hold_expires_at = expires_at

    next_entry.status = WaitlistStatus.offered
    next_entry.offered_seat_id = show_seat.seat_id
    next_entry.offer_expires_at = expires_at
    db.commit()

    # Redis key is the actual TTL clock (mirrors hold:{show_id}:{seat_id}
    # from Feature 4) -- the expiry listener reacts to this key expiring,
    # not to the Postgres offer_expires_at timestamp.
    await redis_client.set(_offer_key(next_entry.id), str(show_seat.seat_id), ex=ttl)

    return "held"


async def expire_offer(db: Session, entry_id: uuid.UUID):
    """
    Called by the expiry listener when waitlist_offer:{entry_id}'s TTL runs
    out unclaimed. Marks the entry expired, then cascades the seat to the
    *next* person in line via the same try_assign_or_release used for
    cancellations -- or releases it to AVAILABLE if the queue is now empty.
    Returns (seat_id, new_status) for broadcasting, or None if there was
    nothing to do (offer was already claimed in the race window).
    """
    entry = db.get(WaitlistEntry, entry_id)
    if not entry or entry.status != WaitlistStatus.offered:
        return None

    entry.status = WaitlistStatus.expired
    db.commit()

    show_seat = (
        db.query(ShowSeat)
        .filter(ShowSeat.show_id == entry.show_id, ShowSeat.seat_id == entry.offered_seat_id)
        .with_for_update()
        .first()
    )
    if not show_seat or show_seat.status != SeatStatus.held or show_seat.held_by_user_id != entry.user_id:
        return None  # state already changed under us -- don't stomp on it

    new_status = await try_assign_or_release(db, show_seat)
    return show_seat.seat_id, new_status


async def claim_offer(db: Session, entry_id: uuid.UUID, user_id: uuid.UUID) -> Booking:
    """
    Converts a still-valid waitlist offer into a real booking. Same two-
    source-of-truth check as checkout_service.checkout(): the Redis offer
    key must still exist (hasn't hit TTL) AND Postgres must agree the seat
    is still HELD for this exact user.
    """
    entry = db.query(WaitlistEntry).filter(WaitlistEntry.id == entry_id).with_for_update().first()
    if not entry or entry.user_id != user_id:
        raise WaitlistError("Waitlist offer not found")
    if entry.status != WaitlistStatus.offered:
        raise WaitlistError("This offer is no longer active")

    still_valid = await redis_client.get(_offer_key(entry.id))
    if still_valid != str(entry.offered_seat_id):
        raise WaitlistError("Offer has expired")

    show_seat = (
        db.query(ShowSeat)
        .filter(ShowSeat.show_id == entry.show_id, ShowSeat.seat_id == entry.offered_seat_id)
        .with_for_update()
        .first()
    )
    if not show_seat or show_seat.status != SeatStatus.held or show_seat.held_by_user_id != user_id:
        raise WaitlistError("Seat is no longer reserved for you")

    booking = Booking(user_id=user_id, show_id=entry.show_id, status=BookingStatus.confirmed)
    db.add(booking)
    db.flush()

    show_seat.status = SeatStatus.booked
    show_seat.booking_id = booking.id
    show_seat.held_by_user_id = None
    show_seat.hold_expires_at = None

    entry.status = WaitlistStatus.fulfilled

    db.commit()
    db.refresh(booking)

    await redis_client.delete(_offer_key(entry.id))
    return booking


def get_my_waitlist_entries(db: Session, user_id: uuid.UUID) -> list[WaitlistEntry]:
    return (
        db.query(WaitlistEntry)
        .filter(WaitlistEntry.user_id == user_id)
        .order_by(WaitlistEntry.created_at.desc())
        .all()
    )
