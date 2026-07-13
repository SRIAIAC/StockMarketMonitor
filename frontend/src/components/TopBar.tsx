import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type IndexItem } from "../api/client";
import { isMarketOpen, marketStatusLabel } from "../marketStatus";
import { useTheme } from "../theme";
import Icon from "./Icon";
import RefreshButton from "./RefreshButton";

function formatTime(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Kolkata",
  }).format(new Date(value));
}

export default function TopBar({ onToggleSidebar }: { onToggleSidebar?: () => void }) {
  const [indices, setIndices] = useState<IndexItem[]>([]);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [theme, toggleTheme] = useTheme();

  useEffect(() => {
    const load = () => {
      api.indices().then(setIndices).catch(() => {});
      api.analyticsStatus().then((s) => setLastUpdated(s.refreshed_at)).catch(() => {});
    };
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, []);

  const open = isMarketOpen();

  return (
    <header className="topbar">
      <div className="topbar-left">
        <button className="sidebar-toggle" onClick={onToggleSidebar} aria-label="Toggle navigation">
          <Icon name="overview" size={18} />
        </button>
        <Link to="/" className="topbar-brand">
          <span className="topbar-brand-mark">ISM</span>
          <span className="topbar-brand-text">
            Indian Stock Market Watch
            <small>Market Intelligence Platform</small>
          </span>
        </Link>
      </div>

      <div className="topbar-indices">
        {indices.length === 0 && <span className="topbar-index-skeleton" />}
        {indices.map((idx) => (
          <div className="topbar-index" key={idx.name}>
            <span className="topbar-index-name">{idx.name}</span>
            <span className="topbar-index-value">
              {idx.last?.toLocaleString("en-IN", { maximumFractionDigits: 2 }) ?? "—"}
            </span>
            {idx.pct_change !== null && (
              <span className={idx.pct_change >= 0 ? "pct-up" : "pct-down"}>
                {idx.pct_change >= 0 ? "+" : ""}
                {idx.pct_change.toFixed(2)}%
              </span>
            )}
          </div>
        ))}
      </div>

      <div className="topbar-right">
        <div className="topbar-market-status">
          <span className={"status-dot" + (open ? "" : " status-dot-closed")} />
          <span className="topbar-market-status-text">{marketStatusLabel()}</span>
        </div>
        <div className="topbar-last-updated">
          <span>LAST UPDATED</span>
          <strong>{formatTime(lastUpdated)} IST</strong>
        </div>
        <button className="topbar-icon-btn" aria-label="Search">
          <Icon name="search" size={17} />
        </button>
        <button className="topbar-icon-btn" aria-label="Notifications">
          <Icon name="bell" size={17} />
        </button>
        <button className="topbar-icon-btn" aria-label="Toggle theme" onClick={toggleTheme}>
          <Icon name={theme === "dark" ? "sun" : "moon"} size={17} />
        </button>
        <RefreshButton />
        <div className="topbar-avatar" aria-label="Account">
          <Icon name="user" size={16} />
        </div>
      </div>
    </header>
  );
}
