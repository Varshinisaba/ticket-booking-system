import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, EmailStr, ConfigDict

from app.models import UserRole, EventType


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: UserRole = UserRole.customer  # admin accounts should be created manually, not via public signup


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---- Venues ----

class SeatCreate(BaseModel):
    row: str
    number: int
    category: str


class SeatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    row: str
    number: int
    category: str


class VenueCreate(BaseModel):
    name: str
    address: str
    seats: List[SeatCreate]


class VenueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    address: str
    seats: List[SeatOut] = []


# ---- Events & Shows ----

class EventCreate(BaseModel):
    title: str
    type: EventType
    venue_id: uuid.UUID


class CategoryPriceIn(BaseModel):
    category: str
    price: Decimal


class ShowCreate(BaseModel):
    starts_at: datetime
    prices: List[CategoryPriceIn]


class CategoryPriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    category: str
    price: Decimal


class ShowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    starts_at: datetime
    prices: List[CategoryPriceOut] = []


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    type: EventType
    venue: VenueOut
    organiser_id: uuid.UUID
    shows: List[ShowOut] = []

# ---- Seat map (Feature 3) ----

class ShowSeatOut(BaseModel):
    show_seat_id: uuid.UUID
    seat_id: uuid.UUID
    row: str
    number: int
    category: str
    status: str


class SeatMapOut(BaseModel):
    show_id: uuid.UUID
    prices: List[CategoryPriceOut]
    seats: List[ShowSeatOut]


# ---- Seat hold (Feature 4) ----

class HoldRequest(BaseModel):
    seat_ids: List[uuid.UUID]


class HoldOut(BaseModel):
    held_seat_ids: List[uuid.UUID]
    hold_expires_at: datetime


class ReleaseOut(BaseModel):
    released_seat_ids: List[uuid.UUID]


# ---- Booking (Feature 5) ----

class CheckoutRequest(BaseModel):
    show_id: uuid.UUID
    seat_ids: List[uuid.UUID]


class BookedSeatOut(BaseModel):
    seat_id: uuid.UUID
    row: str
    number: int
    category: str


class BookingOut(BaseModel):
    id: uuid.UUID
    show_id: uuid.UUID
    status: str
    created_at: datetime
    cancelled_at: Optional[datetime] = None
    seats: List[BookedSeatOut] = []
    event_title: Optional[str] = None
    show_starts_at: Optional[datetime] = None


# ---- Waitlist (Feature 6) ----

class WaitlistJoinRequest(BaseModel):
    category: str


class WaitlistOut(BaseModel):
    id: uuid.UUID
    show_id: uuid.UUID
    category: str
    status: str
    created_at: datetime
    offer_expires_at: Optional[datetime] = None


# ---- Organiser summary & revenue (Feature 7) ----

class ShowSummaryOut(BaseModel):
    show_id: uuid.UUID
    starts_at: datetime
    seats_total: int
    seats_booked: int
    seats_held: int
    seats_available: int
    revenue: Decimal


class EventSummaryOut(BaseModel):
    event_id: uuid.UUID
    title: str
    total_bookings: int
    total_revenue: Decimal
    shows: List[ShowSummaryOut]