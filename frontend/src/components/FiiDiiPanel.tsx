import { useEffect, useState } from "react";
import { api, type FiiDiiData } from "../api/client";

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short" }).format(new Date(value));
}

function formatCr(value: number | null): string {
  if (value === null || value === undefined) return "—";
  const sign = value >= 0 ? "+" : "";
  return `${sign}₹${value.toLocaleString("en-IN", { maximumFractionDigits: 0 })} Cr`;
}

const CATEGORY_CLASS: Record<string, string> = {
  FII: "action-chip-split",
  DII: "action-chip-dividend",
  FDI: "action-chip-bonus",
};

function sentimentColor(score: number | null): string {
  if (score === null || score === undefined) return "#9ca3af";
  if (score > 0.2) return "#16a34a";
  if (score < -0.2) return "#dc2626";
  return "#9ca3af";
}

export default function FiiDiiPanel() {
  const [data, setData] = useState<FiiDiiData | null>(null);

  useEffect(() => {
    const load = () => api.fiiDii().then(setData).catch(() => {});
    load();
    const id = setInterval(load, 15 * 60_000);
    return () => clearInterval(id);
  }, []);

  const flows = data?.flows ?? [];
  const mentions = data?.mentions ?? [];
  const latest = flows[flows.length - 1];
  const maxAbs = Math.max(1, ...flows.flatMap((f) => [Math.abs(f.fii_net_cr ?? 0), Math.abs(f.dii_net_cr ?? 0)]));

  return (
    <div className="panel fii-dii-panel">
      <div className="news-header">
        <div>
          <p className="eyebrow">NSE whole-market flow + news-derived per-stock signals · last 90 days</p>
          <div className="panel-title-row">
            <h2>FII / FDI / DII</h2>
            <span className="panel-ai-badge">AI</span>
          </div>
        </div>
      </div>

      {data?.summary && (
        <div className="ai-summary-box">
          {data.summary_ai_generated && <span className="ai-reason-badge">AI</span>}
          <p>{data.summary}</p>
        </div>
      )}

      <div className="fii-dii-flow-section">
        <h3 className="fii-dii-subhead">Market-wide Flow (NSE, real)</h3>
        {!latest && <p className="muted-row">No FII/DII flow data collected yet.</p>}
        {latest && (
          <>
            <div className="fii-dii-latest-row">
              <div>
                <span className="fii-dii-latest-label">FII net ({formatDate(latest.trade_date)})</span>
                <span className={"fii-dii-latest-value " + ((latest.fii_net_cr ?? 0) >= 0 ? "pct-up" : "pct-down")}>
                  {formatCr(latest.fii_net_cr)}
                </span>
              </div>
              <div>
                <span className="fii-dii-latest-label">DII net ({formatDate(latest.trade_date)})</span>
                <span className={"fii-dii-latest-value " + ((latest.dii_net_cr ?? 0) >= 0 ? "pct-up" : "pct-down")}>
                  {formatCr(latest.dii_net_cr)}
                </span>
              </div>
            </div>
            <div className="fii-dii-spark" aria-label="FII (top) vs DII (bottom) daily net flow">
              {flows.map((f, i) => (
                <div key={i} className="fii-dii-spark-col" title={`${formatDate(f.trade_date)} — FII ${formatCr(f.fii_net_cr)}, DII ${formatCr(f.dii_net_cr)}`}>
                  <span
                    className={"fii-dii-spark-bar " + ((f.fii_net_cr ?? 0) >= 0 ? "fii-dii-bar-up" : "fii-dii-bar-down")}
                    style={{ height: `${Math.max(6, (Math.abs(f.fii_net_cr ?? 0) / maxAbs) * 100)}%` }}
                  />
                  <span
                    className={"fii-dii-spark-bar " + ((f.dii_net_cr ?? 0) >= 0 ? "fii-dii-bar-up" : "fii-dii-bar-down")}
                    style={{ height: `${Math.max(6, (Math.abs(f.dii_net_cr ?? 0) / maxAbs) * 100)}%` }}
                  />
                </div>
              ))}
            </div>
            <p className="fii-dii-caption">
              {flows.length} of 90 days collected so far — accumulates one real reading per trading day.
            </p>
          </>
        )}
      </div>

      <div className="fii-dii-mentions-section">
        <h3 className="fii-dii-subhead">Per-Stock Mentions (news-derived, not confirmed transactions)</h3>
        {mentions.length === 0 && (
          <p className="muted-row">No watchlist stocks mentioned in FII/DII/FDI news this window yet.</p>
        )}
        <ul className="dated-list">
          {mentions.map((m) => (
            <li key={m.id} className="dated-list-row">
              <span className="dated-list-date">{formatDate(m.published_at)}</span>
              <div className="dated-list-body">
                <strong>{m.ticker.replace(".NS", "")}</strong>
                <span className={`action-chip ${CATEGORY_CLASS[m.category] ?? ""}`}>{m.category}</span>
                <span className="fii-dii-sentiment-dot" style={{ background: sentimentColor(m.sentiment) }} />
                <a className="dated-list-subject news-title" href={m.url} target="_blank" rel="noopener noreferrer">
                  {m.title}
                </a>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
