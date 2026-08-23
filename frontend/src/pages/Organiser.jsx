import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../lib/AuthContext";

export default function Organiser() {
  const { user } = useAuth();
  const isAdmin = user.role === "admin";

  return (
    <div className="page">
      <h1 className="page-title">Organiser Desk</h1>
      <p className="page-sub">
        {isAdmin ? "Set up venues for organisers to build events on." : "List your events, schedule showtimes, and track revenue."}
      </p>

      <div className="two-col">
        {isAdmin && <VenueForm />}
        <div>
          <VenueList />
          {!isAdmin && <EventTools />}
        </div>
      </div>
    </div>
  );
}

function VenueForm() {
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [seats, setSeats] = useState([{ row: "A", number: 1, category: "Standard" }]);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function updateSeat(i, field, value) {
    setSeats((s) => s.map((row, idx) => (idx === i ? { ...row, [field]: value } : row)));
  }
  function addSeat() {
    setSeats((s) => [...s, { row: "A", number: s.length + 1, category: "Standard" }]);
  }
  function removeSeat(i) {
    setSeats((s) => s.filter((_, idx) => idx !== i));
  }

  async function generateGrid(rows, perRow, category) {
    const generated = [];
    for (let r = 0; r < rows; r++) {
      const rowLabel = String.fromCharCode(65 + r);
      for (let n = 1; n <= perRow; n++) {
        generated.push({ row: rowLabel, number: n, category: r < Math.ceil(rows / 3) ? "Premium" : category });
      }
    }
    setSeats(generated);
  }

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setMsg("");
    setBusy(true);
    try {
      const venue = await api.createVenue({ name, address, seats });
      setMsg(`Venue "${venue.name}" created with ${venue.seats.length} seats.`);
      setName("");
      setAddress("");
      setSeats([{ row: "A", number: 1, category: "Standard" }]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>Create Venue</h3>
      {error && <div className="error-banner">{error}</div>}
      {msg && <div className="error-banner" style={{ background: "rgba(76,154,107,0.12)", borderColor: "var(--available)", color: "#bdeed0" }}>{msg}</div>}
      <form onSubmit={onSubmit}>
        <div className="field">
          <label>Venue name</label>
          <input required value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="field">
          <label>Address</label>
          <input required value={address} onChange={(e) => setAddress(e.target.value)} />
        </div>

        <div className="field">
          <label>Quick seat grid</label>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => generateGrid(6, 10, "Standard")}>
              6 rows × 10 seats
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => generateGrid(10, 14, "Standard")}>
              10 rows × 14 seats
            </button>
          </div>
          <span className="hint">Generates rows A, B, C… with front rows as Premium.</span>
        </div>

        <div className="field">
          <label>Seats ({seats.length})</label>
          <div style={{ maxHeight: 220, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
            {seats.map((s, i) => (
              <div key={i} style={{ display: "flex", gap: 6 }}>
                <input style={{ width: 50 }} value={s.row} onChange={(e) => updateSeat(i, "row", e.target.value)} />
                <input
                  type="number"
                  style={{ width: 60 }}
                  value={s.number}
                  onChange={(e) => updateSeat(i, "number", Number(e.target.value))}
                />
                <input value={s.category} onChange={(e) => updateSeat(i, "category", e.target.value)} />
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => removeSeat(i)}>
                  ✕
                </button>
              </div>
            ))}
          </div>
          <button type="button" className="btn btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={addSeat}>
            + Add seat row
          </button>
        </div>

        <button className="btn btn-primary" disabled={busy}>
          {busy ? "Creating…" : "Create Venue"}
        </button>
      </form>
    </div>
  );
}

function VenueList() {
  const [venues, setVenues] = useState(null);
  useEffect(() => {
    api.listVenues().then(setVenues).catch(() => {});
  }, []);
  if (!venues) return null;
  return (
    <div className="card" style={{ marginBottom: 24 }}>
      <h3 style={{ marginTop: 0 }}>Venues</h3>
      {venues.length === 0 && <p className="hint">No venues yet.</p>}
      {venues.map((v) => (
        <div key={v.id} style={{ marginBottom: 8, fontSize: 13 }}>
          <strong>{v.name}</strong> — {v.address} · {v.seats.length} seats
        </div>
      ))}
    </div>
  );
}

function EventTools() {
  const { user } = useAuth();
  const [venues, setVenues] = useState([]);
  const [events, setEvents] = useState(null);
  const [title, setTitle] = useState("");
  const [type, setType] = useState("movie");
  const [venueId, setVenueId] = useState("");
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.listVenues().then(setVenues).catch(() => {});
    loadEvents();
  }, []);

  function loadEvents() {
    api.listEvents().then(setEvents).catch(() => {});
  }

  async function createEvent(e) {
    e.preventDefault();
    setError("");
    setMsg("");
    try {
      await api.createEvent({ title, type, venue_id: venueId });
      setMsg("Event created.");
      setTitle("");
      loadEvents();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <>
      <div className="card" style={{ marginBottom: 24 }}>
        <h3 style={{ marginTop: 0 }}>List an Event</h3>
        {error && <div className="error-banner">{error}</div>}
        {msg && <div className="error-banner" style={{ background: "rgba(76,154,107,0.12)", borderColor: "var(--available)", color: "#bdeed0" }}>{msg}</div>}
        <form onSubmit={createEvent}>
          <div className="field">
            <label>Title</label>
            <input required value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="field">
            <label>Type</label>
            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option value="movie">Movie</option>
              <option value="concert">Concert</option>
            </select>
          </div>
          <div className="field">
            <label>Venue</label>
            <select required value={venueId} onChange={(e) => setVenueId(e.target.value)}>
              <option value="">Select a venue…</option>
              {venues.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
          </div>
          <button className="btn btn-primary">Create Event</button>
        </form>
      </div>

      <h2 className="section-title">Your Events</h2>
      {events && events.filter((ev) => ev.organiser_id === user.id).length === 0 && (
        <p className="hint">You haven't listed any events yet.</p>
      )}
      {events &&
        events
          .filter((ev) => ev.organiser_id === user.id)
          .map((ev) => (
            <EventCard key={ev.id} event={ev} onShowCreated={loadEvents} />
          ))}
    </>
  );
}

function EventCard({ event, onShowCreated }) {
  const [showForm, setShowForm] = useState(false);
  const [startsAt, setStartsAt] = useState("");
  const [prices, setPrices] = useState([{ category: "Standard", price: 200 }]);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");

  function updatePrice(i, field, value) {
    setPrices((p) => p.map((row, idx) => (idx === i ? { ...row, [field]: value } : row)));
  }

  async function createShow(e) {
    e.preventDefault();
    setError("");
    try {
      await api.createShow(event.id, { starts_at: new Date(startsAt).toISOString(), prices });
      setShowForm(false);
      setStartsAt("");
      onShowCreated();
    } catch (err) {
      setError(err.message);
    }
  }

  async function loadSummary() {
    try {
      const s = await api.eventSummary(event.id);
      setSummary(s);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <strong>{event.title}</strong> <span className="hint">· {event.type} · {event.venue.name}</span>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-ghost btn-sm" onClick={() => setShowForm((s) => !s)}>
            + Showtime
          </button>
          <button className="btn btn-ghost btn-sm" onClick={loadSummary}>
            Revenue
          </button>
        </div>
      </div>

      {error && <div className="error-banner" style={{ marginTop: 12 }}>{error}</div>}

      {showForm && (
        <form onSubmit={createShow} style={{ marginTop: 16, borderTop: "1px solid var(--line)", paddingTop: 16 }}>
          <div className="field">
            <label>Date & time</label>
            <input type="datetime-local" required value={startsAt} onChange={(e) => setStartsAt(e.target.value)} />
          </div>
          <div className="field">
            <label>Category pricing</label>
            {prices.map((p, i) => (
              <div key={i} style={{ display: "flex", gap: 8, marginBottom: 6 }}>
                <input value={p.category} onChange={(e) => updatePrice(i, "category", e.target.value)} />
                <input
                  type="number"
                  value={p.price}
                  onChange={(e) => updatePrice(i, "price", Number(e.target.value))}
                />
              </div>
            ))}
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setPrices((p) => [...p, { category: "Premium", price: 400 }])}
            >
              + Category
            </button>
          </div>
          <button className="btn btn-primary btn-sm">Create Showtime</button>
        </form>
      )}

      {event.shows.length > 0 && (
        <div className="hint" style={{ marginTop: 10 }}>
          {event.shows.length} showtime{event.shows.length > 1 ? "s" : ""} scheduled
        </div>
      )}

      {summary && (
        <table className="summary-table" style={{ marginTop: 14 }}>
          <thead>
            <tr>
              <th>Show</th>
              <th>Booked</th>
              <th>Held</th>
              <th>Available</th>
              <th>Revenue</th>
            </tr>
          </thead>
          <tbody>
            {summary.shows.map((s) => (
              <tr key={s.show_id}>
                <td>{new Date(s.starts_at).toLocaleDateString()}</td>
                <td>{s.seats_booked}</td>
                <td>{s.seats_held}</td>
                <td>{s.seats_available}</td>
                <td className="num">₹{Number(s.revenue).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {summary && (
        <div className="stat-strip" style={{ marginTop: 14 }}>
          <div className="stat-box">
            <div className="stat-label">Total bookings</div>
            <div className="stat-value">{summary.total_bookings}</div>
          </div>
          <div className="stat-box">
            <div className="stat-label">Total revenue</div>
            <div className="stat-value">₹{Number(summary.total_revenue).toFixed(2)}</div>
          </div>
        </div>
      )}
    </div>
  );
}