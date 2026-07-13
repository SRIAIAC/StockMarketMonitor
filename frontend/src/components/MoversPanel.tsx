import { useEffect, useState } from "react";
import { api, type MoversData, type MoverItem } from "../api/client";

const SHOW_LIMIT = 5;

const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 2,
});

const vol = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });

function MoverRow({ item, type }: { item: MoverItem; type: "gainer" | "loser" }) {
  const isUp = type === "gainer";
  return (
    <li className={`mover-row ${isUp ? "mover-up" : "mover-down"}`}>
      <div className="mover-ticker">
        <strong>{item.symbol || item.ticker.replace(".NS", "")}</strong>
        <span className="mover-name">{item.name !== item.symbol ? item.name : (item.sector ?? "—")}</span>
      </div>
      <div className="mover-right">
        <span className="mover-price">{item.price ? inr.format(item.price) : "—"}</span>
        <span className={`mover-pct ${isUp ? "pct-up" : "pct-down"}`}>
          {isUp ? "▲" : "▼"} {Math.abs(item.pct_change).toFixed(2)}%
          {item.volume > 0 && (
            <span className="mover-vol"> · {vol.format(item.volume)}</span>
          )}
        </span>
      </div>
    </li>
  );
}

function MoverColumn({
  title,
  items,
  type,
  loading,
  eyebrow,
}: {
  title: string;
  items: MoverItem[];
  type: "gainer" | "loser";
  loading: boolean;
  eyebrow: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? items : items.slice(0, SHOW_LIMIT);
  const hasMore = items.length > SHOW_LIMIT;

  return (
    <div className="panel">
      <p className="eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      <ul className="mover-list">
        {visible.map((item) => (
          <MoverRow key={item.ticker} item={item} type={type} />
        ))}
        {loading && <li className="muted-row">Fetching market data…</li>}
        {!loading && items.length === 0 && (
          <li className="muted-row">Market data unavailable</li>
        )}
      </ul>
      {hasMore && (
        <button className="show-more-btn" onClick={() => setExpanded((e) => !e)}>
          {expanded ? "Show less ▲" : `Show ${items.length - SHOW_LIMIT} more ▼`}
        </button>
      )}
    </div>
  );
}

export default function MoversPanel() {
  const [data, setData] = useState<MoversData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.marketMovers()
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));

    const id = setInterval(() => {
      api.marketMovers().then(setData).catch(console.error);
    }, 5 * 60_000);
    return () => clearInterval(id);
  }, []);

  const sourceLabel = data?.source ?? "loading…";

  return (
    <div className="movers-grid">
      <MoverColumn
        title="Top Gainers"
        items={data?.gainers ?? []}
        type="gainer"
        loading={loading}
        eyebrow={`NSE market-wide · ${sourceLabel}`}
      />
      <MoverColumn
        title="Top Losers"
        items={data?.losers ?? []}
        type="loser"
        loading={loading}
        eyebrow={`NSE market-wide · ${sourceLabel}`}
      />
    </div>
  );
}
