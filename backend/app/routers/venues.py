import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.deps import require_role
from app.database import get_db
from app.models import Venue, Seat, UserRole
from app.schemas import VenueCreate, VenueOut

router = APIRouter(prefix="/venues", tags=["venues"])


@router.post("/", response_model=VenueOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_role(UserRole.admin))])
def create_venue(payload: VenueCreate, db: Session = Depends(get_db)):
    venue = Venue(name=payload.name, address=payload.address)
    db.add(venue)
    db.flush()  # get venue.id before creating seats

    for seat_in in payload.seats:
        db.add(Seat(venue_id=venue.id, row=seat_in.row, number=seat_in.number, category=seat_in.category))

    db.commit()
    db.refresh(venue)
    return venue


@router.get("/", response_model=list[VenueOut])
def list_venues(db: Session = Depends(get_db)):
    return db.query(Venue).options(joinedload(Venue.seats)).all()


@router.get("/{venue_id}", response_model=VenueOut)
def get_venue(venue_id: uuid.UUID, db: Session = Depends(get_db)):
    venue = db.query(Venue).options(joinedload(Venue.seats)).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    return venue
