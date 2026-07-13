import { useEffect, useState } from "react";
import { api, type WatchlistItem } from "../api/client";
import ShareWiseCharts from "../components/ShareWiseCharts";
import { capBucketFor, displayTicker } from "../marketBuckets";

const WATCHLIST_LIMIT = 8;

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });

export default function WatchlistPage() {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    const load = () => api.watchlist().then(setWatchlist).catch(console.error);
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, []);

  const visible = expanded ? watchlist : watchlist.slice(0, WATCHLIST_LIMIT);
  const hasMore = watchlist.length > WATCHLIST_LIMIT;

  return (
    <div className="dashboard">
      <header className="page-header">
        <p className="eyebrow">Large, mid &amp; small cap NSE stocks</p>
        <h1>Watchlist</h1>
      </header>

      <ShareWiseCharts watchlist={watchlist} />

      <section className="panel watchlist-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Yahoo NSE symbols</p>
            <h2>Tracked Shares</h2>
          </div>
          <span className="market-chip">Moneycontrol prices</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Cap bucket</th>
              <th>Sector</th>
              <th className="numeric">Price</th>
              <th className="numeric">Alpha</th>
              <th className="numeric">Beta</th>
              <th className="numeric">Day change</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((w) => (
              <tr key={w.ticker}>
                <td className="ticker-cell">
                  <strong>{displayTicker(w.ticker)}</strong>
                  <span>{w.ticker}</span>
                </td>
                <td>
                  <span className={`cap-badge ${capBucketFor(w.ticker).toLowerCase().replace(" ", "-")}`}>
                    {capBucketFor(w.ticker)}
                  </span>
                </td>
                <td>{w.sector ?? "-"}</td>
                <td className="numeric">{w.price === null ? "-" : inr.format(w.price)}</td>
                <td className={`numeric ${w.alpha !== null && Number(w.alpha) >= 0 ? "pct-up" : w.alpha !== null ? "pct-down" : ""}`}>
                  {w.alpha === null ? "-" : `${w.alpha >= 0 ? "+" : ""}${w.alpha.toFixed(2)}%`}
                </td>
                <td className="numeric">{w.beta === null ? "-" : w.beta.toFixed(2)}</td>
                <td className={`numeric ${Number(w.pct_change) >= 0 ? "pct-up" : "pct-down"}`}>
                  {w.pct_change === null ? "-" : `${w.pct_change >= 0 ? "+" : ""}${w.pct_change.toFixed(2)}%`}
                </td>
              </tr>
            ))}
            {watchlist.length === 0 && (
              <tr>
                <td colSpan={7} className="empty-row">Importing Indian market data…</td>
              </tr>
            )}
          </tbody>
        </table>
        {hasMore && (
          <button className="show-more-btn" onClick={() => setExpanded((e) => !e)}>
            {expanded ? "Show less ▲" : `Show ${watchlist.length - WATCHLIST_LIMIT} more ▼`}
          </button>
        )}
      </section>
    </div>
  );
}
