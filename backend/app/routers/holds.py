import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models import User, UserRole, Show
from app.schemas import HoldRequest, HoldOut, ReleaseOut
from app.services.hold_service import place_hold, release_hold, SeatConflictError

router = APIRouter(prefix="/shows", tags=["seat-hold"])


@router.post("/{show_id}/hold", response_model=HoldOut, status_code=status.HTTP_201_CREATED)
async def hold_seats(
    show_id: uuid.UUID,
    payload: HoldRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer)),
):
    if not db.get(Show, show_id):
        raise HTTPException(status_code=404, detail="Show not found")
    if not payload.seat_ids:
        raise HTTPException(status_code=400, detail="seat_ids cannot be empty")

    try:
        updated, expires_at = await place_hold(db, show_id, payload.seat_ids, current_user.id)
    except SeatConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Seat {e.seat_id} is no longer available",
        )

    return HoldOut(held_seat_ids=[s.seat_id for s in updated], hold_expires_at=expires_at)


@router.post("/{show_id}/hold/release", response_model=ReleaseOut)
async def release_seats(
    show_id: uuid.UUID,
    payload: HoldRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer)),
):
    released = await release_hold(db, show_id, payload.seat_ids, current_user.id)
    return ReleaseOut(released_seat_ids=[s.seat_id for s in released])
