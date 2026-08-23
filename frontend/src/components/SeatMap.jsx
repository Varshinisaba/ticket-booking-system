import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, parseServerDate } from "../lib/api";

const LEGEND = [
  { cls: "seat-available", label: "Available" },
  { cls: "seat-selected", label: "Your selection" },
  { cls: "seat-held-other", label: "Held by someone else" },
  { cls: "seat-booked", label: "Booked" },
];

export default function SeatMap({ show, onBookingComplete }) {
  const [seats, setSeats] = useState(null);
  const [prices, setPrices] = useState([]);
  const [selected, setSelected] = useState([]);
  const [holdExpiresAt, setHoldExpiresAt] = useState(null);
  const [now, setNow] = useState(Date.now());
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const wsRef = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    setSeats(null);
    setSelected([]);
    setHoldExpiresAt(null);
    api
      .seatMap(show.id)
      .then((data) => {
        if (cancelled) return;
        setSeats(data.seats);
        setPrices(data.prices);
      })
      .catch((e) => setError(e.message));

    const ws = new WebSocket(api.wsUrl(show.id));
    wsRef.current = ws;
    ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      if (msg.type === "seat:update") {
        setSeats((prev) => {
          if (!prev) return prev;
          const byId = new Map(msg.seats.map((s) => [s.seat_id, s.status]));
          return prev.map((s) => (byId.has(s.seat_id) ? { ...s, status: byId.get(s.seat_id) } : s));
        });
      }
    };

    return () => {
      cancelled = true;
      ws.close();
    };
  }, [show.id]);

  // release held seats if the user navigates away mid-hold
  useEffect(() => {
    return () => {
      if (holdExpiresAt && selected.length) {
        api.releaseSeats(show.id, selected).catch(() => {});
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!holdExpiresAt) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [holdExpiresAt]);

  const secondsLeft = holdExpiresAt
    ? Math.max(0, Math.round((parseServerDate(holdExpiresAt).getTime() - now) / 1000))
    : null;

  useEffect(() => {
    if (secondsLeft === 0) {
      setSelected([]);
      setHoldExpiresAt(null);
      setError("Your hold expired — seats were released back to the pool.");
    }
  }, [secondsLeft]);

  const rows = useMemo(() => {
    if (!seats) return [];
    const grouped = {};
    for (const s of seats) {
      grouped[s.row] = grouped[s.row] || [];
      grouped[s.row].push(s);
    }
    return Object.entries(grouped)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([row, list]) => [row, list.sort((a, b) => a.number - b.number)]);
  }, [seats]);

  const categoriesFull = useMemo(() => {
    if (!seats) return [];
    const byCat = {};
    for (const s of seats) {
      byCat[s.category] = byCat[s.category] || { total: 0, available: 0 };
      byCat[s.category].total += 1;
      if (s.status === "available") byCat[s.category].available += 1;
    }
    return Object.entries(byCat)
      .filter(([, v]) => v.available === 0)
      .map(([cat]) => cat);
  }, [seats]);

  async function toggleSeat(seat) {
    if (seat.status === "booked" || (seat.status === "held" && !selected.includes(seat.seat_id))) return;
    setError("");

    if (selected.includes(seat.seat_id)) {
      const rest = selected.filter((id) => id !== seat.seat_id);
      try {
        await api.releaseSeats(show.id, [seat.seat_id]);
        setSelected(rest);
        if (rest.length === 0) setHoldExpiresAt(null);
      } catch (e) {
        setError(e.message);
      }
      return;
    }

    try {
      setBusy(true);
      const res = await api.holdSeats(show.id, [seat.seat_id]);
      setSelected((prev) => [...prev, ...res.held_seat_ids]);
      setHoldExpiresAt(res.hold_expires_at);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function doCheckout() {
    setError("");
    setBusy(true);
    try {
      const booking = await api.checkout(show.id, selected);
      setSelected([]);
      setHoldExpiresAt(null);
      onBookingComplete?.(booking);
      navigate("/bookings");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function joinWaitlist(category) {
    setError("");
    try {
      await api.joinWaitlist(show.id, category);
      navigate("/waitlist");
    } catch (e) {
      setError(e.message);
    }
  }

  const total = useMemo(() => {
    if (!seats) return 0;
    const priceByCategory = Object.fromEntries(prices.map((p) => [p.category, Number(p.price)]));
    return selected.reduce((sum, id) => {
      const seat = seats.find((s) => s.seat_id === id);
      return sum + (seat ? priceByCategory[seat.category] || 0 : 0);
    }, 0);
  }, [selected, seats, prices]);

  if (error && !seats) return <div className="error-banner">{error}</div>;
  if (!seats) return <p className="hint">Loading seat map…</p>;

  return (
    <div>
      {error && <div className="error-banner">{error}</div>}

      {categoriesFull.length > 0 && (
        <div className="card" style={{ marginBottom: 20 }}>
          <strong style={{ fontSize: 13 }}>Sold out categories</strong>
          <div style={{ display: "flex", gap: 10, marginTop: 10, flexWrap: "wrap" }}>
            {categoriesFull.map((cat) => (
              <button key={cat} className="btn btn-ghost btn-sm" onClick={() => joinWaitlist(cat)}>
                Join waitlist — {cat}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="legend">
        {LEGEND.map((l) => (
          <span key={l.cls}>
            <i className={l.cls} />
            {l.label}
          </span>
        ))}
      </div>

      <div className="screen-arc" />

      <div className="seat-map">
        {rows.map(([row, list]) => (
          <div className="seat-row" key={row}>
            <span className="row-label">{row}</span>
            {list.map((seat) => {
              const isSelected = selected.includes(seat.seat_id);
              const cls =
                seat.status === "booked"
                  ? "seat-booked"
                  : seat.status === "held" && !isSelected
                  ? "seat-held-other"
                  : isSelected
                  ? "seat-selected"
                  : "seat-available";
              return (
                <button
                  key={seat.seat_id}
                  className={`seat ${cls}`}
                  title={`${row}${seat.number} · ${seat.category}`}
                  onClick={() => toggleSeat(seat)}
                  disabled={busy}
                >
                  {seat.number}
                </button>
              );
            })}
          </div>
        ))}
      </div>

      {selected.length > 0 && (
        <div className="checkout-bar">
          <div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 13 }}>
              {selected.length} seat{selected.length > 1 ? "s" : ""} selected · ₹{total.toFixed(2)}
            </div>
            {secondsLeft !== null && (
              <div className="hold-timer">
                Hold expires in {Math.floor(secondsLeft / 60)}:{String(secondsLeft % 60).padStart(2, "0")}
              </div>
            )}
          </div>
          <button className="btn btn-primary" onClick={doCheckout} disabled={busy}>
            {busy ? "Booking…" : "Confirm Booking"}
          </button>
        </div>
      )}
    </div>
  );
}