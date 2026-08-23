import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";

export default function Events() {
  const [events, setEvents] = useState(null);
  const [type, setType] = useState("");
  const [q, setQ] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type]);

  function load() {
    const params = new URLSearchParams();
    if (type) params.set("type", type);
    if (q) params.set("q", q);
    const qs = params.toString();
    api
      .get(`/events/${qs ? `?${qs}` : ""}`)
      .then(setEvents)
      .catch((e) => setError(e.message));
  }

  return (
    <div className="page">
      <h1 className="page-title">Now Showing</h1>
      <p className="page-sub">Browse movies and concerts, then pick your seat.</p>

      <div className="filter-row">
        <input
          className="field-input"
          style={{
            background: "var(--panel)",
            border: "1px solid var(--line)",
            borderRadius: 6,
            padding: "9px 12px",
            color: "var(--cream)",
            flex: 1,
            minWidth: 200,
          }}
          placeholder="Search by title…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && load()}
        />
        <select
          value={type}
          onChange={(e) => setType(e.target.value)}
          style={{
            background: "var(--panel)",
            border: "1px solid var(--line)",
            borderRadius: 6,
            padding: "9px 12px",
            color: "var(--cream)",
          }}
        >
          <option value="">All types</option>
          <option value="movie">Movies</option>
          <option value="concert">Concerts</option>
        </select>
        <button className="btn btn-ghost" onClick={load}>
          Search
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {!events && !error && <p className="hint">Loading listings…</p>}

      {events && events.length === 0 && (
        <div className="empty-state">
          <h3>No events yet</h3>
          <p>Check back soon, or ask an organiser to list one.</p>
        </div>
      )}

      {events && events.length > 0 && (
        <div className="event-grid">
          {events.map((ev) => (
            <Link key={ev.id} to={`/events/${ev.id}`} className="event-card">
              <span className="event-type-pill">{ev.type}</span>
              <h3>{ev.title}</h3>
              <div className="venue">{ev.venue?.name}</div>
              <div className="shows-count">
                {ev.shows.length} showtime{ev.shows.length === 1 ? "" : "s"}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
