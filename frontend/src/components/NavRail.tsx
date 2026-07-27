import { NavLink } from "react-router-dom";
import { useAuthStore } from "../store/authStore";

const ITEMS = [
  { to: "/", label: "Чат", icon: "💬", end: true },
  { to: "/memory", label: "Память", icon: "🧠" },
  { to: "/characters", label: "Персонажи", icon: "🎭" },
  { to: "/timeline", label: "Таймлайн", icon: "🕓" },
  { to: "/search", label: "Поиск", icon: "🔎" },
  { to: "/prompt-inspector", label: "Инспектор", icon: "🧾" },
  { to: "/settings", label: "Настройки", icon: "⚙️" },
];

export default function NavRail() {
  const logout = useAuthStore((s) => s.logout);

  return (
    <nav className="nav-rail">
      <div className="nav-rail-brand">RP</div>
      <div className="nav-rail-items">
        {ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => `nav-rail-item ${isActive ? "active" : ""}`}
            title={item.label}
          >
            <span className="nav-rail-icon">{item.icon}</span>
            <span className="nav-rail-label">{item.label}</span>
          </NavLink>
        ))}
      </div>
      <button className="nav-rail-item nav-rail-logout" title="Выйти" onClick={() => logout()}>
        <span className="nav-rail-icon">⏻</span>
        <span className="nav-rail-label">Выйти</span>
      </button>
    </nav>
  );
}
