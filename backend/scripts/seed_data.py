"""
Seeds the database with one account per role plus a working demo venue,
event, and show -- so the app has something to look at and every role is
immediately testable, instead of needing Swagger or manual SQL to bootstrap
the very first admin account.

Safe to re-run: skips anything that already exists by email/name, so running
it twice won't create duplicates.

Usage (from the backend/ folder, venv active):
    python scripts/seed_data.py
"""
import sys
import os
from datetime import datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base, engine, SessionLocal
from app.core.security import hash_password
from app.models import (
    User, UserRole, Venue, Seat, Event, EventType, Show, CategoryPrice, ShowSeat,
)

DEMO_ACCOUNTS = [
    ("admin@marquee.app", "Admin User", "Admin123!", UserRole.admin),
    ("organiser@marquee.app", "Priya Organiser", "Organiser123!", UserRole.organiser),
    ("customer@marquee.app", "Varshini Customer", "Customer123!", UserRole.customer),
]


def get_or_create_user(db, email, full_name, password, role):
    user = db.query(User).filter(User.email == email).first()
    if user:
        return user, False
    user = User(email=email, full_name=full_name, hashed_password=hash_password(password), role=role)
    db.add(user)
    db.flush()
    return user, True


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    print("=== Seeding accounts ===")
    users = {}
    for email, name, password, role in DEMO_ACCOUNTS:
        user, created = get_or_create_user(db, email, name, password, role)
        users[role] = user
        print(f"  {'created' if created else 'exists '} {role.value:10s} {email} / {password}")
    db.commit()

    print("\n=== Seeding venue ===")
    venue = db.query(Venue).filter(Venue.name == "Marquee Grand Hall").first()
    if not venue:
        venue = Venue(name="Marquee Grand Hall", address="12 Anna Salai, Chennai")
        db.add(venue)
        db.flush()
        # 5 rows (A-E) x 10 seats: front 2 rows Premium, rest Standard
        for row_idx, row in enumerate(["A", "B", "C", "D", "E"]):
            category = "Premium" if row_idx < 2 else "Standard"
            for number in range(1, 11):
                db.add(Seat(venue_id=venue.id, row=row, number=number, category=category))
        db.commit()
        print(f"  created venue '{venue.name}' with 50 seats (rows A-E)")
    else:
        print(f"  exists  venue '{venue.name}'")

    print("\n=== Seeding events + shows ===")
    events_to_seed = [
        ("Interstellar: Re-release", EventType.movie, [
            (timedelta(days=1, hours=19), {"Premium": Decimal("350.00"), "Standard": Decimal("200.00")}),
            (timedelta(days=2, hours=19), {"Premium": Decimal("350.00"), "Standard": Decimal("200.00")}),
        ]),
        ("Arijit Singh Live", EventType.concert, [
            (timedelta(days=7, hours=20), {"Premium": Decimal("2500.00"), "Standard": Decimal("1200.00")}),
        ]),
    ]

    organiser = users[UserRole.organiser]
    venue_seats = db.query(Seat).filter(Seat.venue_id == venue.id).all()

    for title, event_type, shows in events_to_seed:
        event = db.query(Event).filter(Event.title == title).first()
        if event:
            print(f"  exists  event '{title}'")
            continue

        event = Event(title=title, type=event_type, organiser_id=organiser.id, venue_id=venue.id)
        db.add(event)
        db.flush()

        for offset, prices in shows:
            show = Show(event_id=event.id, starts_at=datetime.utcnow() + offset)
            db.add(show)
            db.flush()
            for category, price in prices.items():
                db.add(CategoryPrice(show_id=show.id, category=category, price=price))
            for seat in venue_seats:
                db.add(ShowSeat(show_id=show.id, seat_id=seat.id))

        db.commit()
        print(f"  created event '{title}' with {len(shows)} show(s)")

    db.close()

    print("\n=== Done ===")
    print("Log in at the frontend with any of the accounts above.")
    print("Admin -> Organiser Console -> New Venue (manage venues)")
    print("Organiser -> Organiser Console -> New Event / New Show / Revenue")
    print("Customer -> browse Events, book seats, join waitlists")


if __name__ == "__main__":
    seed()
