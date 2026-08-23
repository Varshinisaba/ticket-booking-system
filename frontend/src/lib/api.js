const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Backend sends naive UTC timestamps (no "Z"/offset). Browsers parse those
// as LOCAL time, which silently breaks any hold/offer countdown for anyone
// not in UTC. Treat any offset-less ISO string as UTC.
export function parseServerDate(iso) {
  if (!iso) return null;
  const hasOffset = /Z$|[+-]\d\d:\d\d$/.test(iso);
  return new Date(hasOffset ? iso : `${iso}Z`);
}

function authHeaders() {
  const token = localStorage.getItem("tbs_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function handle(res) {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* no json body */
    }
    const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

function get(path) {
  return fetch(`${BASE}${path}`, { headers: { ...authHeaders() } }).then(handle);
}

function send(method, path, body) {
  return fetch(`${BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  }).then(handle);
}

export const api = {
  base: BASE,
  get,
  post: (path, body) => send("POST", path, body),

  // auth
  register: (payload) => send("POST", "/auth/register", payload),
  login: (email, password) => {
    const form = new URLSearchParams();
    form.set("username", email);
    form.set("password", password);
    return fetch(`${BASE}/auth/login`, { method: "POST", body: form }).then(handle);
  },
  me: () => get("/auth/me"),

  // venues
  listVenues: () => get("/venues/"),
  createVenue: (payload) => send("POST", "/venues/", payload),

  // events
  listEvents: () => get("/events/"),
  getEvent: (id) => get(`/events/${id}`),
  createEvent: (payload) => send("POST", "/events/", payload),
  createShow: (eventId, payload) => send("POST", `/events/${eventId}/shows`, payload),
  eventSummary: (eventId) => get(`/events/${eventId}/summary`),

  // seat map / holds
  seatMap: (showId) => get(`/shows/${showId}/seatmap`),
  holdSeats: (showId, seatIds) => send("POST", `/shows/${showId}/hold`, { seat_ids: seatIds }),
  releaseSeats: (showId, seatIds) => send("POST", `/shows/${showId}/hold/release`, { seat_ids: seatIds }),
  wsUrl: (showId) => `${BASE.replace(/^http/, "ws")}/shows/${showId}/ws`,

  // bookings
  checkout: (showId, seatIds) => send("POST", "/bookings/checkout", { show_id: showId, seat_ids: seatIds }),
  history: () => get("/bookings/history"),
  cancelBooking: (id) => send("POST", `/bookings/${id}/cancel`),

  // waitlist
  joinWaitlist: (showId, category) => send("POST", `/waitlist/shows/${showId}/join`, { category }),
  myWaitlist: () => get("/waitlist/my"),
  claimOffer: (entryId) => send("POST", `/waitlist/${entryId}/claim`),
};
