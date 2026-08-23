import { useEffect, useState } from "react";
import { api } from "../lib/api";

export default function Bookings() {
  const [bookings, setBookings] = useState(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);

  useEffect(() => {
    load();
  }, []);

  function load() {
    api
      .history()
      .then(setBookings)
      .catch((e) => setError(e.message));
  }

  async function cancel(id) {
    setBusyId(id);
    setError("");
    try {
      await api.cancelBooking(id);
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="page">
      <h1 className="page-title">My Tickets</h1>
      <p className="page-sub">Every confirmed booking sends a QR ticket to your email too.</p>

      {error && <div className="error-banner">{error}</div>}
      {!bookings && !error && <p className="hint">Loading…</p>}

      {bookings && bookings.length === 0 && (
        <div className="empty-state">
          <h3>No tickets yet</h3>
          <p>Once you book a seat, it'll show up here as a tearable stub.</p>
        </div>
      )}

      {bookings &&
        bookings.map((b) => (
          <div className="ticket" key={b.id}>
            <div className="ticket-main">
              <h3>{b.event_title || "Event"}</h3>
              <div className="ticket-meta">
                {b.show_starts_at &&
                  new Date(b.show_starts_at).toLocaleString(undefined, {
                    weekday: "short",
                    month: "short",
                    day: "numeric",
                    hour: "numeric",
                    minute: "2-digit",
                  })}
              </div>
              <div className="ticket-seats">
                {b.seats.map((s) => `${s.row}${s.number}`).join(", ")} · {b.seats[0]?.category}
              </div>
              <div className="ticket-id">Booking ID {b.id}</div>
            </div>
            <div className="ticket-stub">
              <span className={`ticket-status status-${b.status}`}>{b.status}</span>
              {b.status === "confirmed" && (
                <button className="link-btn" onClick={() => cancel(b.id)} disabled={busyId === b.id}>
                  {busyId === b.id ? "Cancelling…" : "Cancel"}
                </button>
              )}
            </div>
          </div>
        ))}
    </div>
  );
}
