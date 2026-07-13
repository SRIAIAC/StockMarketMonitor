import { useEffect, useState } from "react";
import { api, connectAlertsSocket, type AlertItem } from "../api/client";

const severityColor: Record<string, string> = {
  critical: "#d32f2f",
  warning: "#f59e0b",
  info: "#3b82f6",
};

function deduplicateByTickerPerDay(alerts: AlertItem[]): AlertItem[] {
  const key = (a: AlertItem) => {
    const day = a.created_at ? new Date(a.created_at).toDateString() : "unknown";
    // Category is part of the key: the backend dedupes alerts per
    // ticker+category+day, so a ticker can legitimately have both a
    // "market" and a "social" alert on the same day — keying on ticker+day
    // alone would let one silently overwrite the other once they're split
    // into separate panels.
    return `${a.ticker ?? "MARKET"}__${a.category}__${day}`;
  };
  const map = new Map<string, AlertItem>();
  for (const a of alerts) {
    const k = key(a);
    const existing = map.get(k);
    if (
      !existing ||
      new Date(a.created_at ?? 0).getTime() > new Date(existing.created_at ?? 0).getTime()
    ) {
      map.set(k, a);
    }
  }
  return [...map.values()].sort(
    (a, b) =>
      new Date(b.created_at ?? 0).getTime() - new Date(a.created_at ?? 0).getTime()
  );
}

interface AlertFeedProps {
  categories: string[];
  title: string;
  eyebrow: string;
}

export default function AlertFeed({ categories, title, eyebrow }: AlertFeedProps) {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);

  useEffect(() => {
    api.alerts().then((items) => setAlerts(deduplicateByTickerPerDay(items))).catch(console.error);

    const disconnect = connectAlertsSocket((incoming) => {
      setAlerts((prev) => deduplicateByTickerPerDay([incoming, ...prev]).slice(0, 100));
    });
    return disconnect;
  }, []);

  const visible = alerts.filter((a) => categories.includes(a.category));

  return (
    <div className="panel">
      <p className="eyebrow">{eyebrow}</p>
      <div className="panel-title-row">
        <h2>{title}</h2>
        <span className="panel-ai-badge">AI</span>
      </div>
      <ul className="alert-list">
        {visible.map((a) => (
          <li
            key={`${a.ticker ?? "MARKET"}__${a.created_at}`}
            style={{ borderLeftColor: severityColor[a.severity] || "#999" }}
          >
            <span className="alert-ticker">{a.ticker?.replace(".NS", "") ?? "MARKET"}</span>
            <span className="alert-message">{a.message}</span>
            {a.reason && <span className="alert-reason">{a.reason}</span>}
            {a.used_ai && <span className="alert-ai-badge">AI</span>}
          </li>
        ))}
        {visible.length === 0 && <li className="alert-empty">No alerts yet</li>}
      </ul>
    </div>
  );
}
