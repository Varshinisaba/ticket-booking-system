import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.orm import Session, joinedload

from app.core.deps import require_role
from app.database import get_db
from app.models import User, UserRole, ShowSeat, Show, Event, Booking
from app.schemas import CheckoutRequest, BookingOut, BookedSeatOut
from app.services.checkout_service import checkout, get_booking_history, cancel_booking, CheckoutError
from app.services.email_service import send_booking_confirmation_email

logger = logging.getLogger("bookings")


async def _send_confirmation_email_safe(*args, **kwargs):
    """Wraps the email send so any failure is guaranteed to print loudly,
    instead of silently vanishing inside a background task."""
    try:
        await send_booking_confirmation_email(*args, **kwargs)
        print("[email] booking confirmation sent OK")
    except Exception:
        logger.exception("[email] FAILED to send booking confirmation")


router = APIRouter(prefix="/bookings", tags=["bookings"])


def _to_booking_out(db: Session, booking: Booking) -> BookingOut:
    show_seats = (
        db.query(ShowSeat)
        .options(joinedload(ShowSeat.seat))
        .filter(ShowSeat.booking_id == booking.id)
        .all()
    )
    show = db.query(Show).options(joinedload(Show.event)).filter(Show.id == booking.show_id).first()
    return BookingOut(
        id=booking.id,
        show_id=booking.show_id,
        status=booking.status.value,
        created_at=booking.created_at,
        cancelled_at=booking.cancelled_at,
        seats=[
            BookedSeatOut(seat_id=ss.seat_id, row=ss.seat.row, number=ss.seat.number, category=ss.seat.category)
            for ss in show_seats
        ],
        event_title=show.event.title if show else None,
        show_starts_at=show.starts_at if show else None,
    )


@router.post("/checkout", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
async def checkout_endpoint(
    payload: CheckoutRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer)),
):
    try:
        booking = await checkout(db, payload.show_id, payload.seat_ids, current_user.id)
    except CheckoutError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.detail)

    booking_out = _to_booking_out(db, booking)

    # Email is sent in the background -- checkout returns immediately rather
    # than waiting on an SMTP round trip.
    background_tasks.add_task(
        _send_confirmation_email_safe,
        current_user.email,
        str(booking.id),
        booking_out.event_title or "Your event",
        str(booking_out.show_starts_at),
        [f"{s.row}{s.number}" for s in booking_out.seats],
    )

    return booking_out


@router.get("/history", response_model=list[BookingOut])
def history_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer)),
):
    bookings = get_booking_history(db, current_user.id)
    return [_to_booking_out(db, b) for b in bookings]


@router.post("/{booking_id}/cancel", response_model=BookingOut)
async def cancel_endpoint(
    booking_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer)),
):
    try:
        booking = await cancel_booking(db, booking_id, current_user.id)
    except CheckoutError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail)
    return _to_booking_out(db, booking)