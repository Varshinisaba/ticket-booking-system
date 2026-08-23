import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../lib/AuthContext";

export default function Layout() {
  const { user, logout } = useAuth();

  return (
    <div className="app-shell">
      <header className="marquee-bar">
        <div className="marquee-inner">
          <Link to="/" className="brand">
            Box<span>Office</span>
          </Link>
          <nav className="nav-links">
            <NavLink to="/">Events</NavLink>
            {user && user.role === "customer" && (
              <>
                <NavLink to="/bookings">My Tickets</NavLink>
                <NavLink to="/waitlist">Waitlist</NavLink>
              </>
            )}
            {user && (user.role === "organiser" || user.role === "admin") && (
              <NavLink to="/organiser">Organiser</NavLink>
            )}
            {user ? (
              <>
                <span className="role-tag">{user.role}</span>
                <button className="btn btn-ghost btn-sm" onClick={logout}>
                  Log out
                </button>
              </>
            ) : (
              <>
                <NavLink to="/login">Log in</NavLink>
                <NavLink to="/register" className="btn btn-primary btn-sm">
                  Sign up
                </NavLink>
              </>
            )}
          </nav>
        </div>
      </header>
      <Outlet />
    </div>
  );
}
