import { useEffect, useState } from "react";
import { api, type MarketBriefing } from "../api/client";
import Icon from "./Icon";

function formatTime(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-IN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" }).format(new Date(value));
}

const AGENT_LABELS: Record<string, string> = {
  news: "News",
  social: "Social",
  alert: "Alerts",
  risk: "Risk",
  recommendation: "Recommendations",
};

export default function MarketBriefingPanel() {
  const [data, setData] = useState<MarketBriefing | null>(null);

  useEffect(() => {
    const load = () => api.briefing().then(setData).catch(() => {});
    load();
    const id = setInterval(load, 2 * 60_000);
    return () => clearInterval(id);
  }, []);

  const hasAnomalies = (data?.anomalies.length ?? 0) > 0;

  return (
    <div className="panel briefing-panel">
      <div className="news-header">
        <div>
          <p className="eyebrow">Orchestrator · synthesized across every agent</p>
          <h2>Market Briefing</h2>
        </div>
        <div className="briefing-meta">
          <span className={"briefing-source-chip" + (data?.ai_generated ? " briefing-source-ai" : "")}>
            {data?.ai_generated ? "AI-written" : "Rule-based"}
          </span>
          <span className="briefing-time">{formatTime(data?.computed_at ?? null)} IST</span>
        </div>
      </div>

      {!data || !data.summary ? (
        <p className="muted-row">Waiting for the orchestrator's next run…</p>
      ) : (
        <>
          <h3 className="briefing-headline">{data.headline}</h3>
          <p className="briefing-summary">{data.summary}</p>

          {hasAnomalies ? (
            <div className="briefing-anomalies">
              {data.anomalies.map((a, i) => (
                <div className="briefing-anomaly-row" key={i}>
                  <Icon name="bell" size={13} />
                  <span>{a}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="briefing-anomaly-row briefing-anomaly-clear">
              <Icon name="dot" size={8} />
              <span>No anomalies detected this cycle — conditions are within normal range.</span>
            </div>
          )}

          {data.agents_triggered.length > 0 && (
            <div className="briefing-triggered">
              <span className="briefing-triggered-label">Re-triggered off-cycle:</span>
              {data.agents_triggered.map((a) => (
                <span className="chip" key={a}>{AGENT_LABELS[a] ?? a}</span>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
