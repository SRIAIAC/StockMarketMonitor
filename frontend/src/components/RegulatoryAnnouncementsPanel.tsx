import { useEffect, useState } from "react";
import { api, type RegulatoryAnnouncementItem } from "../api/client";

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

export default function RegulatoryAnnouncementsPanel({ limit = 8 }: { limit?: number }) {
  const [items, setItems] = useState<RegulatoryAnnouncementItem[]>([]);

  useEffect(() => {
    const load = () => api.regulatoryAnnouncements(limit).then(setItems).catch(() => {});
    load();
    const id = setInterval(load, 10 * 60_000);
    return () => clearInterval(id);
  }, [limit]);

  return (
    <div className="panel regulatory-panel">
      <div className="news-header">
        <div>
          <p className="eyebrow">NSE regulatory announcements · not SEBI EDIFAR</p>
          <div className="panel-title-row">
            <h2>SEBI Filings</h2>
            <span className="panel-ai-badge">AI</span>
          </div>
        </div>
      </div>

      {items.length === 0 && <p className="muted-row">No announcements in the current window</p>}
      <ul className="dated-list">
        {items.map((item) => (
          <li key={item.id} className="dated-list-row">
            <span className="dated-list-date">{formatDateTime(item.announcement_date)}</span>
            <div className="dated-list-body">
              <strong>{item.company_name || item.symbol}</strong>
              <span className="action-chip action-chip-filing">{item.category}</span>
              <p className="dated-list-subject">{item.subject}</p>
              {item.ai_reason && (
                <p className="ai-reason-line">
                  <span className="ai-reason-badge">AI</span>
                  {item.ai_reason}
                </p>
              )}
              {item.attachment_url && (
                <a href={item.attachment_url} target="_blank" rel="noopener noreferrer" className="signal-source-link">
                  View filing →
                </a>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
