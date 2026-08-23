import uuid

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.database import get_db
from app.models import User, UserRole, WaitlistEntry, Show
from app.schemas import WaitlistJoinRequest, WaitlistOut
from app.services.waitlist_service import join_waitlist, claim_offer, get_my_waitlist_entries, WaitlistError
from app.services.email_service import send_booking_confirmation_email
from app.routers.bookings import _to_booking_out  # reuse the exact same shape checkout/history use

router = APIRouter(prefix="/waitlist", tags=["waitlist"])


def _to_waitlist_out(entry: WaitlistEntry) -> WaitlistOut:
    return WaitlistOut(
        id=entry.id,
        show_id=entry.show_id,
        category=entry.category,
        status=entry.status.value,
        created_at=entry.created_at,
        offer_expires_at=entry.offer_expires_at,
    )


@router.post("/shows/{show_id}/join", response_model=WaitlistOut, status_code=status.HTTP_201_CREATED)
def join_waitlist_endpoint(
    show_id: uuid.UUID,
    payload: WaitlistJoinRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer)),
):
    if not db.get(Show, show_id):
        raise HTTPException(status_code=404, detail="Show not found")
    try:
        entry = join_waitlist(db, show_id, payload.category, current_user.id)
    except WaitlistError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.detail)
    return _to_waitlist_out(entry)


@router.get("/my", response_model=list[WaitlistOut])
def my_waitlist_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer)),
):
    return [_to_waitlist_out(e) for e in get_my_waitlist_entries(db, current_user.id)]


@router.post("/{entry_id}/claim", status_code=status.HTTP_201_CREATED)
async def claim_offer_endpoint(
    entry_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer)),
):
    """
    Completes the booking for a still-valid, time-limited waitlist offer.
    This is what the link in send_waitlist_offer_email's email should point
    to on the frontend (frontend calls this endpoint when the customer
    clicks "claim").
    """
    try:
        booking = await claim_offer(db, entry_id, current_user.id)
    except WaitlistError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.detail)

    booking_out = _to_booking_out(db, booking)

    background_tasks.add_task(
        send_booking_confirmation_email,
        current_user.email,
        str(booking.id),
        booking_out.event_title or "Your event",
        str(booking_out.show_starts_at),
        [f"{s.row}{s.number}" for s in booking_out.seats],
    )

    return booking_out
