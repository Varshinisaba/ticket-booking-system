# Ticket Booking System

## Feature 1 — Project setup, DB, auth ✅

### What's in this commit
- FastAPI app skeleton (`app/main.py`)
- SQLAlchemy engine/session (`app/database.py`)
- `User` model with `role` enum: customer / organiser / admin (`app/models.py`)
- JWT auth: register, login, `/auth/me` (`app/routers/auth.py`)
- Password hashing (bcrypt via passlib) + JWT create/decode (`app/core/security.py`)
- Role-based access control dependency: `require_role(...)` (`app/core/deps.py`) — every future route
  that needs "admin only" or "organiser or admin" will use this
- Docker Compose for local Postgres + Redis (Redis already configured with
  `--notify-keyspace-events Ex` for the seat-hold-expiry feature coming in Feature 4)

### Run it locally
```bash
# 1. start postgres + redis
docker compose up -d

# 2. install deps
python -m venv venv

source venv/bin/activate   # venv\Scripts\activate on Windows
pip install -r requirements.txt

# 3. configure env
cp .env.example .env
# edit .env: set JWT_SECRET_KEY to something random

# 4. create tables (no Alembic migration yet -- quick create_all for now,
#    Alembic gets wired up once we add the venue/event models in Feature 2)
python -c "from app.database import Base, engine; from app import models; Base.metadata.create_all(bind=engine)"

# 5. run
uvicorn app.main:app --reload
```

Then hit `http://localhost:8000/docs` for interactive Swagger UI.

### Test it
```bash
# register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","full_name":"Your Name","password":"secret123"}'

# login (note: form data, not JSON -- OAuth2PasswordRequestForm)
curl -X POST http://localhost:8000/auth/login \
  -d "username=you@example.com&password=secret123"

# use the returned access_token
curl http://localhost:8000/auth/me -H "Authorization: Bearer <token>"
```

### Known gotcha fixed here
`passlib==1.7.4` + `bcrypt>=4.1` breaks (`bcrypt` removed the `__about__` attribute
passlib's version detector relies on). Pinned `bcrypt==4.0.1` in requirements.txt.

### Next up: Feature 2 — venue & event management
`Venue`, `Seat`, `Event`, `Show` models + admin venue CRUD + organiser event CRUD,
built on top of the `require_role()` dependency from this feature.
