import { useEffect, useState } from "react";
import { api, parseServerDate } from "../lib/api";

export default function Waitlist() {
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  function load() {
    api
      .myWaitlist()
      .then(setEntries)
      .catch((e) => setError(e.message));
  }

  async function claim(id) {
    setBusyId(id);
    setError("");
    try {
      await api.claimOffer(id);
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  function timeLeft(iso) {
    const ms = parseServerDate(iso).getTime() - Date.now();
    if (ms <= 0) return "expired";
    const m = Math.floor(ms / 60000);
    const s = Math.floor((ms % 60000) / 1000);
    return `${m}m ${s}s left`;
  }

  return (
    <div className="page">
      <h1 className="page-title">Waitlist</h1>
      <p className="page-sub">
        When a seat frees up in your category, it's offered to you here for a limited time.
      </p>

      {error && <div className="error-banner">{error}</div>}
      {!entries && !error && <p className="hint">Loading…</p>}

      {entries && entries.length === 0 && (
        <div className="empty-state">
          <h3>You're not waiting on anything</h3>
          <p>Join a waitlist from a sold-out category on any event page.</p>
        </div>
      )}

      {entries &&
        entries.map((e) => (
          <div className="waitlist-row" key={e.id}>
            <div>
              <strong>{e.category}</strong>
              <div className="hint">Joined {new Date(e.created_at).toLocaleDateString()}</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span className={`ticket-status status-${e.status === "fulfilled" ? "confirmed" : "cancelled"}`}>
                {e.status}
              </span>
              {e.status === "offered" && e.offer_expires_at && (
                <>
                  <span className="hold-timer">{timeLeft(e.offer_expires_at)}</span>
                  <button className="btn btn-primary btn-sm" onClick={() => claim(e.id)} disabled={busyId === e.id}>
                    {busyId === e.id ? "Claiming…" : "Claim seat"}
                  </button>
                </>
              )}
            </div>
          </div>
        ))}
    </div>
  );
}
