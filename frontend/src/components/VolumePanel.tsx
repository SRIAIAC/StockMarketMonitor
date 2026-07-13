import { useState } from "react";
import { type WatchlistItem } from "../api/client";

const SHOW_LIMIT = 5;

const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 2,
});

const vol = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });

export default function VolumePanel({ watchlist }: { watchlist: WatchlistItem[] }) {
  const [expanded, setExpanded] = useState(false);

  const sorted = [...watchlist]
    .filter((w) => w.volume !== null && w.volume > 0)
    .sort((a, b) => (b.volume ?? 0) - (a.volume ?? 0));

  const visible = expanded ? sorted : sorted.slice(0, SHOW_LIMIT);
  const hasMore = sorted.length > SHOW_LIMIT;

  return (
    <div className="panel">
      <p className="eyebrow">Watchlist · by traded volume</p>
      <h2>Volume by Share</h2>
      <ul className="mover-list">
        {visible.map((w) => {
          const sym = w.ticker.replace(".NS", "");
          const pct = w.pct_change;
          return (
            <li key={w.ticker} className={`mover-row ${(pct ?? 0) >= 0 ? "mover-up" : "mover-down"}`}>
              <div className="mover-ticker">
                <strong>{sym}</strong>
                <span className="mover-name">{w.sector ?? "—"}</span>
              </div>
              <div className="mover-right">
                <span className="mover-price">
                  {w.price !== null ? inr.format(w.price) : "—"}
                </span>
                <span className={`mover-pct ${(pct ?? 0) >= 0 ? "pct-up" : "pct-down"}`}>
                  {w.volume !== null ? vol.format(w.volume) : "—"} shares
                  {pct !== null && (
                    <span style={{ marginLeft: 6, opacity: 0.75 }}>
                      {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
                    </span>
                  )}
                </span>
              </div>
            </li>
          );
        })}
        {sorted.length === 0 && (
          <li className="muted-row">Volume data loading…</li>
        )}
      </ul>
      {hasMore && (
        <button className="show-more-btn" onClick={() => setExpanded((e) => !e)}>
          {expanded ? "Show less ▲" : `Show ${sorted.length - SHOW_LIMIT} more ▼`}
        </button>
      )}
    </div>
  );
}
