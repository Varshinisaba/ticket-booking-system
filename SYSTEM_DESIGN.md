# System Design — Ticket Booking System

*(~780 words)*

## Seat hold & TTL mechanism

Every `show_seats` row (one per venue seat, per show) carries a `status` of
`available`, `held`, or `booked`. When a customer selects seats, the backend
doesn't touch Postgres first — it goes to Redis and runs `SET
hold:{show_id}:{seat_id} {user_id} NX EX {ttl}` for each seat. `NX` (set-if-
not-exists) makes the operation atomic: if a key is already present, the
command is a no-op and returns failure. That single atomic check is what
decides who "wins" a seat, before either process ever touches the database.

Only after every requested seat's lock is acquired does the code write
`status = held`, `held_by_user_id`, and `hold_expires_at` to Postgres. If
any seat in the request is already locked, every lock acquired earlier in
that same call is rolled back (`DEL` on each key) and the whole request
fails with a 409 — holds are all-or-nothing, so a customer never ends up
holding three seats out of a requested four.

The TTL is the expiry mechanism: Redis keys with `EX` disappear on their
own after `SEAT_HOLD_TTL_SECONDS` (default 600s), no cron job or polling
needed. To actually *act* on that expiry — flipping the Postgres row back
to `available` — the backend subscribes to Redis keyspace notifications
(`notify-keyspace-events Ex`), which publish an event the moment a key
expires. A background listener task, started on app startup, reacts to
`hold:*` expiry events by releasing the corresponding seat and broadcasting
the update over WebSocket, so every connected seat map reflects it live.

## Concurrency prevention

The design deliberately uses **two sources of truth with different jobs**:
Redis is the fast, atomic lock and clock; Postgres is the durable, queryable
record. Relying on Postgres alone (e.g. `UPDATE ... WHERE status =
'available'`) would work for the "first write wins" case but gives no
built-in expiry — you'd need a polling job to sweep expired holds, adding
latency and a window where two customers could believe they hold the same
seat. Relying on Redis alone would work for locking but leave no relational
store for seat maps, revenue reporting, or booking history.

Because two stores exist, every state transition re-validates against both
before committing:
- **Checkout**: confirms the Redis hold key still exists and still belongs
  to the requesting user, *and* locks the Postgres row with `SELECT ... FOR
  UPDATE` to confirm it's still `held` by that user. `FOR UPDATE` blocks
  any other transaction (a concurrent checkout, a cancellation, the expiry
  listener) from touching that row until this one commits or rolls back —
  the second, database-level safety net beneath the Redis lock. Both
  checks must pass or the booking is rejected with no partial writes.
- **Waitlist offer claim**: identical two-source check — Redis offer key
  must still be live, Postgres row must still show `held` for that exact
  user — before the offer becomes a real booking.

This closes the race where a hold's TTL expires a fraction of a second
before the user hits "confirm": if the Redis key is already gone, checkout
fails cleanly instead of booking a seat nobody actually still holds.

## Waitlist auto-assignment flow

Joining the waitlist is only permitted once a `(show, category)` combination
has zero available seats — otherwise the customer is directed to book
directly, so nobody queues behind an empty line. `waitlist_entries` is a
FIFO queue ordered by `created_at`.

Whenever a seat frees up — a cancellation, or a waitlist offer itself
expiring unclaimed — `try_assign_or_release` runs: it looks up the oldest
`waiting` entry for that show+category with `SELECT ... FOR UPDATE` (so two
seats freeing at once can't both be assigned to the same waiting entry). If
someone's waiting, the seat is set to `held` — reserved for that one
person — instead of `available`, and their entry flips to `offered`. If
nobody's waiting, the seat is simply released to `available`.

## Time-limited offer handling

An offer reuses the exact same primitive as a seat hold: a Redis key
(`waitlist_offer:{entry_id}`) with a TTL (`WAITLIST_OFFER_TTL_SECONDS`,
default 900s) is the actual clock; the `offer_expires_at` column on
`waitlist_entries` is just the readable mirror of it. The customer gets an
email with a claim link the moment they're offered a seat.

If they claim in time, `claim_offer` runs the same dual-store validation as
checkout and converts the entry to a `Booking`. If the Redis key expires
first, the keyspace listener fires `expire_offer`: the entry is marked
`expired`, and — critically — the *same* `try_assign_or_release` function
is called again on that seat. This is what makes the queue self-cascading:
an unclaimed offer doesn't just release the seat, it automatically re-offers
it to the next person in line, who gets their own fresh TTL window and
their own email, with no manual intervention or separate code path.
