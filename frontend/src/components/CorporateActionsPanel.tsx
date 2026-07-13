import { useEffect, useState } from "react";
import { api, type CorporateActionItem } from "../api/client";

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short" }).format(new Date(value));
}

const TYPE_CLASS: Record<string, string> = {
  Dividend: "action-chip-dividend",
  Bonus: "action-chip-bonus",
  Split: "action-chip-split",
  Rights: "action-chip-rights",
  Buyback: "action-chip-buyback",
  AGM: "action-chip-agm",
};

export default function CorporateActionsPanel({ limit = 8 }: { limit?: number }) {
  const [items, setItems] = useState<CorporateActionItem[]>([]);

  useEffect(() => {
    const load = () => api.corporateActions(limit).then(setItems).catch(() => {});
    load();
    const id = setInterval(load, 10 * 60_000);
    return () => clearInterval(id);
  }, [limit]);

  return (
    <div className="panel corporate-actions-panel">
      <div className="news-header">
        <div>
          <p className="eyebrow">NSE · whole market</p>
          <div className="panel-title-row">
            <h2>Corporate Actions</h2>
            <span className="panel-ai-badge">AI</span>
          </div>
        </div>
      </div>

      {items.length === 0 && <p className="muted-row">No corporate actions in the current window</p>}
      <ul className="dated-list">
        {items.map((item) => (
          <li key={item.id} className="dated-list-row">
            <span className="dated-list-date">{formatDate(item.ex_date)}</span>
            <div className="dated-list-body">
              <strong>{item.company_name || item.symbol}</strong>
              <span className={`action-chip ${TYPE_CLASS[item.action_type] ?? ""}`}>{item.action_type}</span>
              {item.value && <span className="dated-list-value">{item.value}</span>}
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
