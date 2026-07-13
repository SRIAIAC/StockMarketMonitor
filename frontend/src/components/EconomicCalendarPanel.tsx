import { useEffect, useState } from "react";
import { api, type EconomicEventItem } from "../api/client";

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short" }).format(new Date(value));
}

const IMPORTANCE_CLASS: Record<string, string> = {
  high: "importance-dot-high",
  medium: "importance-dot-medium",
  low: "importance-dot-low",
};

export default function EconomicCalendarPanel({ limit = 8 }: { limit?: number }) {
  const [items, setItems] = useState<EconomicEventItem[]>([]);

  useEffect(() => {
    const load = () => api.economicEvents(limit).then(setItems).catch(() => {});
    load();
    const id = setInterval(load, 15 * 60_000);
    return () => clearInterval(id);
  }, [limit]);

  return (
    <div className="panel economic-calendar-panel">
      <div className="news-header">
        <div>
          <p className="eyebrow">India macro calendar</p>
          <div className="panel-title-row">
            <h2>Economic Calendar</h2>
            <span className="panel-ai-badge">AI</span>
          </div>
        </div>
      </div>

      {items.length === 0 && <p className="muted-row">No recent releases yet — check back shortly.</p>}
      <ul className="dated-list">
        {items.map((item) => (
          <li key={item.id} className="dated-list-row">
            <span className="dated-list-date">{formatDate(item.release_date)}</span>
            <div className="dated-list-body">
              <span className={`importance-dot ${IMPORTANCE_CLASS[item.importance] ?? ""}`} />
              <strong>{item.title}</strong>
              {item.value !== null && <span className="dated-list-value">{item.value}</span>}
              {item.detail && <span className="dated-list-subject">{item.detail}</span>}
              {item.ai_reason && (
                <p className="ai-reason-line">
                  <span className="ai-reason-badge">AI</span>
                  {item.ai_reason}
                </p>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
