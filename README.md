# Ticket Booking System

Full-stack seat-level ticket booking platform for movies and concerts, with
real-time seat maps, TTL-based seat holds, waitlist auto-assignment, and QR
code tickets.

- **Backend**: FastAPI (Python) + PostgreSQL + Redis + WebSockets
- **Frontend**: React 19 + Vite

---

## 1. Architecture at a glance

```
┌─────────────┐      REST + WS       ┌──────────────────┐
│   Frontend   │ ───────────────────▶│  FastAPI backend  │
│  React/Vite  │◀─────────────────── │                    │
└─────────────┘   seat:update events └───────┬───────────┘
                                              │
                          ┌───────────────────┼────────────────────┐
                          ▼                                        ▼
                 ┌─────────────────┐                      ┌──────────────────┐
                 │   PostgreSQL     │                      │      Redis        │
                 │ source of truth  │                      │  hold/offer TTLs  │
                 │ for all records  │                      │  + keyspace events │
                 └─────────────────┘                      └──────────────────┘
```

Postgres holds every durable record (users, venues, events, shows, seats,
bookings, waitlist entries). Redis is used purely as a **distributed lock +
expiry clock** for seat holds and waitlist offers — see [Section 5](#5-seat-hold--waitlist-design)
for why two stores are used instead of one.

---

## 2. Setup guide

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker (for local Postgres + Redis) — or your own instances of both

### Backend

```bash
cd backend

# 1. start Postgres + Redis (Redis needs keyspace notifications enabled —
#    already configured in docker-compose.yml)
docker compose up -d

# 2. install dependencies
python -m venv venv
source venv/bin/activate        # venv\Scripts\activate on Windows
pip install -r requirements.txt

# 3. configure environment
cp .env.example .env
# edit .env — at minimum, set JWT_SECRET_KEY to a random value

# 4. run the API
uvicorn app.main:app --reload
```

Tables are created automatically on startup (`Base.metadata.create_all`) —
no migration step needed for a fresh database. Visit
`http://localhost:8000/docs` for interactive Swagger docs.

Optional: seed sample venues/events/shows for local testing:

```bash
python scripts/seed_data.py
```

### Frontend

```bash
cd frontend
cp .env.example .env     # set VITE_API_URL if the backend isn't on :8000
npm install
npm run dev
```

Visit `http://localhost:5173`.

### Environment variables

**backend/.env.example**
```bash
# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ticket_booking

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT
JWT_SECRET_KEY=change-me-to-a-random-value
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Seat hold / waitlist offer TTLs (seconds)
SEAT_HOLD_TTL_SECONDS=600
WAITLIST_OFFER_TTL_SECONDS=900

# Email (SMTP — e.g. Gmail app password, or SendGrid SMTP relay)
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_FROM=your-email@gmail.com
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_FROM_NAME=Ticket Booking System

# Needed so waitlist/booking emails can link back to the right frontend
FRONTEND_URL=http://localhost:5173
```

**frontend/.env.example**
```bash
VITE_API_URL=http://localhost:8000
```

> `JWT_SECRET_KEY` must be changed before any real deployment — never reuse
> the placeholder value from the example file.

---

## 3. Deployment

Deploy configs are already checked in:

- **`render.yaml`** — one-click Render Blueprint: provisions a free Postgres
  database, a free Redis (key-value) instance, and the FastAPI web service,
  wires the connection strings together automatically, and generates a
  random `JWT_SECRET_KEY`. In the Render dashboard: **New → Blueprint →**
  point at this repo. You'll be prompted for the `sync: false` secrets
  (`FRONTEND_URL`, SMTP credentials) after the blueprint is created.
- **`frontend/vercel.json`** — SPA rewrite rule for React Router. Import the
  `frontend/` directory as the project root in Vercel, set `VITE_API_URL`
  to your deployed backend's URL as a build-time env var, deploy.

Order matters: deploy the backend first (via the Render blueprint), copy its
public URL into the frontend's `VITE_API_URL`, then deploy the frontend.
Once the frontend URL is live, set it as `FRONTEND_URL` on the backend
service so booking/waitlist emails link to the right place.

*(This zip ships the deploy configs but was not pushed to a live Render/Vercel
account as part of this delivery — see the accompanying note for why, and
the steps above to stand it up in a few minutes.)*

---

## 4. Database schema

| Table              | Purpose                                                                 |
|---------------------|--------------------------------------------------------------------------|
| `users`             | Single table for all three roles (`customer`, `organiser`, `admin`), role enforced at the route level. |
| `venues`            | Physical venue: name, address.                                          |
| `seats`             | Fixed seat layout for a venue (`row`, `number`, `category`), unique per venue. |
| `events`            | A movie/concert listing owned by an organiser, tied to one venue.       |
| `shows`             | A specific date/time instance of an event — pricing and seat state hang off this, not the event. |
| `category_prices`   | Per-show, per-category price.                                           |
| `show_seats`        | **Per-show** seat state (`available` / `held` / `booked`) — one row per venue seat per show, created when the show is created. This is what the seat map renders and what hold/booking logic mutates. |
| `bookings`          | A confirmed reservation covering one or more `show_seats` rows.         |
| `waitlist_entries`  | FIFO queue per `(show_id, category)`; `created_at` is queue order.      |

Key relationships: `venues 1—N seats`, `events N—1 venues`, `events 1—N shows`,
`shows 1—N show_seats`, `show_seats N—1 seats`, `bookings 1—N show_seats`,
`waitlist_entries N—1 seats` (via `offered_seat_id`, only set once an offer
is live).

`show_seats` (not `seats`) is the source of truth for availability — the
same physical seat is `available` for one show and `booked` for another.

---

## 5. Seat hold & waitlist design

### Seat hold
- Placing a hold does a Redis `SETNX hold:{show_id}:{seat_id}` with a TTL
  (`SEAT_HOLD_TTL_SECONDS`, default 600s). `SETNX` is atomic, so if two
  customers click the same seat at the same instant, only one succeeds —
  Redis is the concurrency lock; Postgres (`show_seats.status = held`) is
  updated after, purely for reads (seat map, admin views).
- Hold requests are all-or-nothing: if any seat in the request is already
  taken, every lock acquired earlier in that same call is released before
  returning a `409`.
- Redis keyspace notifications (`notify-keyspace-events Ex`) fire when a
  hold key's TTL runs out. A background listener catches that event and
  flips the seat back to `available` in Postgres — no polling required.
- At checkout, the hold is re-validated against **both** stores (Redis key
  still exists and belongs to this user, **and** Postgres row is still
  `held` by this user under a `SELECT ... FOR UPDATE`) before the booking
  is committed — this catches the race where the TTL expires a moment
  before checkout lands.

### Waitlist auto-assignment
- Joining the waitlist is only allowed once a category is actually sold
  out — if seats are open, the customer is directed to book directly.
- When a seat frees up (cancellation, or an unclaimed waitlist offer
  cascading), the earliest `waiting` entry for that `(show, category)` is
  looked up with `SELECT ... FOR UPDATE`, and the seat is set to `held`
  for that person rather than going back to `available`. Their entry moves
  to `offered` with an `offer_expires_at`.
- The same Redis pattern is reused for the offer clock:
  `waitlist_offer:{entry_id}` with `WAITLIST_OFFER_TTL_SECONDS` (default
  900s). Postgres holds the readable record; Redis is the actual timer.
- If the offer is claimed in time, it converts into a real `Booking` (same
  dual-store validation as checkout). If it expires unclaimed, the
  keyspace listener cascades the seat to the *next* person in line (or
  releases it to `available` if the queue is empty) and emails that next
  person their own time-limited offer.

### Real-time updates
Every hold, release, booking, cancellation, and waitlist cascade broadcasts
a `seat:update` message over a per-show WebSocket, so every connected seat
map updates live without polling.

---

## 6. API reference

Interactive Swagger docs are always the source of truth: `GET /docs`. Summary:

| Method & path                          | Auth              | Purpose |
|-----------------------------------------|-------------------|---------|
| `POST /auth/register`                   | —                 | Create an account (`customer`/`organiser`/`admin`) |
| `POST /auth/login`                      | —                 | Form-encoded login, returns JWT |
| `GET /auth/me`                          | any                | Current user |
| `POST /venues/`                         | organiser/admin   | Create venue + seat layout |
| `GET /venues/` `/venues/{id}`           | any                | List / fetch venues |
| `POST /events/`                         | organiser         | Create an event |
| `POST /events/{id}/shows`               | organiser (owner) | Create a show + pricing; generates the show's seat map |
| `GET /events/` `/events/{id}`           | any                | List / fetch events |
| `GET /events/{id}/summary`              | organiser/admin   | Per-show seat + revenue breakdown |
| `GET /shows/{id}/seatmap`               | any                | Full seat map with live status |
| `WS /shows/{id}/ws`                     | any                | Live `seat:update` stream |
| `POST /shows/{id}/hold`                 | customer          | Place TTL-limited seat hold(s) |
| `POST /shows/{id}/hold/release`         | customer          | Explicitly release held seat(s) |
| `POST /bookings/checkout`                | customer          | Convert a valid hold into a booking |
| `GET /bookings/history`                  | customer          | Booking history |
| `POST /bookings/{id}/cancel`             | customer          | Cancel a booking; triggers waitlist cascade |
| `POST /waitlist/shows/{id}/join`         | customer          | Join the waitlist for a sold-out category |
| `GET /waitlist/my`                       | customer          | This user's waitlist entries |
| `POST /waitlist/{id}/claim`              | customer          | Claim a still-valid waitlist offer |

---

## 7. Project layout

```
backend/
  app/
    core/       # config, JWT/password security, Redis client, WS manager, role deps
    routers/    # auth, venues, events, shows, holds, bookings, waitlist
    services/   # hold_service, waitlist_service, checkout_service, expiry_listener, email, qr
    models.py   # SQLAlchemy models
    schemas.py  # Pydantic request/response models
  scripts/      # seed_data.py, test_email.py
frontend/
  src/
    pages/      # Events, EventDetail, Login, Register, Bookings, Waitlist, Organiser
    components/ # Layout, ProtectedRoute, SeatMap
    lib/        # api.js (fetch wrapper), AuthContext
```
