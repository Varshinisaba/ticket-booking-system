import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from typing import Optional

from app.core.deps import require_role, get_current_user
from app.database import get_db
from app.models import (
    Event, Show, CategoryPrice, Venue, Seat, ShowSeat, SeatStatus, User, UserRole, Booking, BookingStatus,
)
from app.schemas import EventCreate, EventOut, ShowCreate, ShowOut, EventSummaryOut, ShowSummaryOut

router = APIRouter(prefix="/events", tags=["events"])


def _event_query(db: Session):
    return db.query(Event).options(
        joinedload(Event.venue).joinedload(Venue.seats),
        joinedload(Event.shows).joinedload(Show.prices),
    )


@router.post("/", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def create_event(
    payload: EventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.organiser)),
):
    venue = db.get(Venue, payload.venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    event = Event(title=payload.title, type=payload.type, venue_id=payload.venue_id, organiser_id=current_user.id)
    db.add(event)
    db.commit()
    db.refresh(event)
    return _event_query(db).filter(Event.id == event.id).first()


@router.post("/{event_id}/shows", response_model=ShowOut, status_code=status.HTTP_201_CREATED)
def create_show(
    event_id: uuid.UUID,
    payload: ShowCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.organiser)),
):
    """
    Creates a Show (a specific date/time instance) with per-category pricing,
    and generates the show's seat map: one ShowSeat row per venue seat, all
    starting AVAILABLE. This is what GET /shows/{id}/seatmap (Feature 3) reads.
    """
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.organiser_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your event")

    show = Show(event_id=event_id, starts_at=payload.starts_at)
    db.add(show)
    db.flush()

    for p in payload.prices:
        db.add(CategoryPrice(show_id=show.id, category=p.category, price=p.price))

    venue_seats = db.query(Seat).filter(Seat.venue_id == event.venue_id).all()
    for seat in venue_seats:
        db.add(ShowSeat(show_id=show.id, seat_id=seat.id))

    db.commit()
    db.refresh(show)
    return show


@router.get("/", response_model=list[EventOut])
def list_events(
    type: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = _event_query(db)
    if type:
        query = query.filter(Event.type == type)
    if q:
        query = query.filter(Event.title.ilike(f"%{q}%"))
    return query.all()


@router.get("/{event_id}", response_model=EventOut)
def get_event(event_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    event = _event_query(db).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.get("/{event_id}/summary", response_model=EventSummaryOut)
def get_event_summary(
    event_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.organiser, UserRole.admin)),
):
    """
    Per-show seat breakdown + revenue, and event-level totals. Revenue is
    computed from *currently booked* seats (status == booked) rather than
    from historical Booking rows -- that way a cancelled-then-reassigned
    seat (via the waitlist, Feature 6) is counted once under whoever holds
    it now, with no double-counting or manual reconciliation needed.
    Organisers only see their own events; admins can view any event.
    """
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if current_user.role == UserRole.organiser and event.organiser_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your event")

    shows = db.query(Show).filter(Show.event_id == event_id).all()

    show_summaries: list[ShowSummaryOut] = []
    total_revenue = Decimal("0")

    for show in shows:
        show_seats = (
            db.query(ShowSeat)
            .options(joinedload(ShowSeat.seat))
            .filter(ShowSeat.show_id == show.id)
            .all()
        )
        prices = {
            p.category: p.price
            for p in db.query(CategoryPrice).filter(CategoryPrice.show_id == show.id).all()
        }

        seats_booked = sum(1 for ss in show_seats if ss.status == SeatStatus.booked)
        seats_held = sum(1 for ss in show_seats if ss.status == SeatStatus.held)
        seats_available = sum(1 for ss in show_seats if ss.status == SeatStatus.available)

        revenue = sum(
            (prices.get(ss.seat.category, Decimal("0")) for ss in show_seats if ss.status == SeatStatus.booked),
            Decimal("0"),
        )
        total_revenue += revenue

        show_summaries.append(
            ShowSummaryOut(
                show_id=show.id,
                starts_at=show.starts_at,
                seats_total=len(show_seats),
                seats_booked=seats_booked,
                seats_held=seats_held,
                seats_available=seats_available,
                revenue=revenue,
            )
        )

    total_bookings = (
        db.query(Booking)
        .join(Show, Booking.show_id == Show.id)
        .filter(Show.event_id == event_id, Booking.status == BookingStatus.confirmed)
        .count()
    )

    return EventSummaryOut(
        event_id=event.id,
        title=event.title,
        total_bookings=total_bookings,
        total_revenue=total_revenue,
        shows=show_summaries,
    )