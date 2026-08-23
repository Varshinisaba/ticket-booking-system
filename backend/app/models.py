import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, DateTime, Numeric, ForeignKey, Enum as SAEnum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class UserRole(str, enum.Enum):
    customer = "customer"
    organiser = "organiser"
    admin = "admin"


class User(Base):
    """
    Single users table for all three roles. Role-based access is enforced
    at the route level (see app/core/deps.py), not via separate tables --
    keeps auth simple while still letting organisers/admins have normal
    customer-style profiles if needed later.
    """
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.customer)
    created_at = Column(DateTime, default=datetime.utcnow)


class EventType(str, enum.Enum):
    movie = "movie"
    concert = "concert"


class Venue(Base):
    __tablename__ = "venues"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    address = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    seats = relationship("Seat", back_populates="venue", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="venue")


class Seat(Base):
    """Fixed physical seat belonging to a venue's layout (row/number/category)."""
    __tablename__ = "seats"
    __table_args__ = (UniqueConstraint("venue_id", "row", "number", name="uq_seat_venue_row_number"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    venue_id = Column(UUID(as_uuid=True), ForeignKey("venues.id"), nullable=False)
    row = Column(String, nullable=False)
    number = Column(Integer, nullable=False)
    category = Column(String, nullable=False)  # e.g. Premium, Standard

    venue = relationship("Venue", back_populates="seats")


class Event(Base):
    """A movie or concert listing, owned by an organiser, tied to one venue."""
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    type = Column(SAEnum(EventType), nullable=False)
    organiser_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    venue_id = Column(UUID(as_uuid=True), ForeignKey("venues.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    venue = relationship("Venue", back_populates="events")
    shows = relationship("Show", back_populates="event", cascade="all, delete-orphan")


class Show(Base):
    """A specific date/time instance of an event. Seat map + pricing hang off this, not Event."""
    __tablename__ = "shows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False)
    starts_at = Column(DateTime, nullable=False)

    event = relationship("Event", back_populates="shows")
    prices = relationship("CategoryPrice", back_populates="show", cascade="all, delete-orphan")
    show_seats = relationship("ShowSeat", back_populates="show", cascade="all, delete-orphan")


class CategoryPrice(Base):
    __tablename__ = "category_prices"
    __table_args__ = (UniqueConstraint("show_id", "category", name="uq_price_show_category"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    show_id = Column(UUID(as_uuid=True), ForeignKey("shows.id"), nullable=False)
    category = Column(String, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)

    show = relationship("Show", back_populates="prices")


class SeatStatus(str, enum.Enum):
    available = "available"
    held = "held"
    booked = "booked"


class ShowSeat(Base):
    """
    Per-show seat state -- this is what the seat map renders and what
    hold/booking logic mutates. One row per venue seat per show, created
    when the show is created (see events.py create_show).
    """
    __tablename__ = "show_seats"
    __table_args__ = (UniqueConstraint("show_id", "seat_id", name="uq_showseat_show_seat"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    show_id = Column(UUID(as_uuid=True), ForeignKey("shows.id"), nullable=False)
    seat_id = Column(UUID(as_uuid=True), ForeignKey("seats.id"), nullable=False)
    status = Column(SAEnum(SeatStatus), nullable=False, default=SeatStatus.available)
    held_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    hold_expires_at = Column(DateTime, nullable=True)
    booking_id = Column(UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=True)

    show = relationship("Show", back_populates="show_seats")
    seat = relationship("Seat")
    booking = relationship("Booking", back_populates="seats")


class BookingStatus(str, enum.Enum):
    confirmed = "confirmed"
    cancelled = "cancelled"


class Booking(Base):
    """
    A confirmed reservation covering one or more ShowSeat rows for one show.
    QR is generated on demand (encodes the booking id) rather than stored as
    a file -- see app/services/qr_service.py.
    """
    __tablename__ = "bookings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    show_id = Column(UUID(as_uuid=True), ForeignKey("shows.id"), nullable=False)
    status = Column(SAEnum(BookingStatus), nullable=False, default=BookingStatus.confirmed)
    created_at = Column(DateTime, default=datetime.utcnow)
    cancelled_at = Column(DateTime, nullable=True)

    seats = relationship("ShowSeat", back_populates="booking")
    show = relationship("Show")
    user = relationship("User")


class WaitlistStatus(str, enum.Enum):
    waiting = "waiting"      # in queue, no seat offered yet
    offered = "offered"      # a specific seat is held for this entry, offer_expires_at is live
    fulfilled = "fulfilled"  # claimed in time -> became a real Booking
    expired = "expired"      # offer TTL ran out unclaimed -- seat cascaded to next in line
    cancelled = "cancelled"  # customer left the queue voluntarily (not wired to an endpoint yet)


class WaitlistEntry(Base):
    """
    FIFO queue per (show_id, category). created_at is the queue order --
    oldest 'waiting' entry always gets the next freed seat in that category.
    offered_seat_id + offer_expires_at are only meaningful while status is
    'offered'; the matching Redis key waitlist_offer:{id} is the actual
    TTL enforcement (mirrors the hold:{show_id}:{seat_id} pattern from
    Feature 4) -- Postgres here is the readable record, Redis is the clock.
    """
    __tablename__ = "waitlist_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    show_id = Column(UUID(as_uuid=True), ForeignKey("shows.id"), nullable=False)
    category = Column(String, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status = Column(SAEnum(WaitlistStatus), nullable=False, default=WaitlistStatus.waiting)
    created_at = Column(DateTime, default=datetime.utcnow)
    offered_seat_id = Column(UUID(as_uuid=True), ForeignKey("seats.id"), nullable=True)
    offer_expires_at = Column(DateTime, nullable=True)

    show = relationship("Show")
    user = relationship("User")
    offered_seat = relationship("Seat")