# BoxOffice Frontend

React + Vite frontend for the ticket booking system.

## Setup
```
npm install
cp .env.example .env   # set VITE_API_URL to your backend URL
npm run dev
```

## What's here
- Auth (register/login, JWT stored in localStorage)
- Event browsing + filtering
- Seat map per showtime with live WebSocket updates, hold countdown, checkout
- Waitlist join (auto-shown for sold-out categories) + claim offer
- Booking history with cancel
- Organiser tools: create venue (admin), create event + showtimes (organiser), revenue summary

Talks to the FastAPI backend in `../backend`.
