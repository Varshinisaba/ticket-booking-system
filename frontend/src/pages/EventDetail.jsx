import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../lib/api";
import SeatMap from "../components/SeatMap";

export default function EventDetail() {
  const { id } = useParams();
  const [event, setEvent] = useState(null);
  const [selectedShow, setSelectedShow] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .getEvent(id)
      .then((ev) => {
        setEvent(ev);
        if (ev.shows.length) setSelectedShow(ev.shows[0]);
      })
      .catch((e) => setError(e.message));
  }, [id]);

  if (error) return <div className="page"><div className="error-banner">{error}</div></div>;
  if (!event) return <div className="page"><p className="hint">Loading…</p></div>;

  return (
    <div className="page">
      <span className="event-type-pill">{event.type}</span>
      <h1 className="page-title" style={{ marginTop: 10 }}>{event.title}</h1>
      <p className="page-sub">
        {event.venue.name} · {event.venue.address}
      </p>

      {event.shows.length === 0 ? (
        <div className="empty-state">
          <h3>No showtimes yet</h3>
          <p>The organiser hasn't scheduled any showtimes for this event.</p>
        </div>
      ) : (
        <>
          <div className="tabs">
            {event.shows.map((s) => (
              <button
                key={s.id}
                className={selectedShow?.id === s.id ? "active" : ""}
                onClick={() => setSelectedShow(s)}
              >
                {new Date(s.starts_at).toLocaleString(undefined, {
                  weekday: "short",
                  month: "short",
                  day: "numeric",
                  hour: "numeric",
                  minute: "2-digit",
                })}
              </button>
            ))}
          </div>

          <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 24 }}>
            {selectedShow?.prices.map((p) => (
              <span key={p.category} className="event-type-pill">
                {p.category} · ₹{Number(p.price).toFixed(2)}
              </span>
            ))}
          </div>

          {selectedShow && <SeatMap key={selectedShow.id} show={selectedShow} />}
        </>
      )}
    </div>
  );
}
