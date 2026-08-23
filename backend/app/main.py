from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, venues, events, shows, holds, bookings, waitlist
from app.services.expiry_listener import start_expiry_listener
from app.database import Base, engine
import asyncio

app = FastAPI(title="Ticket Booking System", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this before deploying
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(venues.router)
app.include_router(events.router)
app.include_router(shows.router)
app.include_router(holds.router)
app.include_router(bookings.router)
app.include_router(waitlist.router)


@app.on_event("startup")
async def on_startup():
    # No Alembic migrations wired up yet (see backend/README.md) -- create_all
    # is idempotent, so this is a safe way to get tables onto a fresh managed
    # Postgres instance on first deploy without a manual shell step.
    Base.metadata.create_all(bind=engine)
    asyncio.create_task(start_expiry_listener())


@app.get("/health")
def health_check():
    return {"status": "ok"}