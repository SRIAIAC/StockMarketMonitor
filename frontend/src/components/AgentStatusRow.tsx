import { useEffect, useState } from "react";
import { api, type AgentStatusItem } from "../api/client";
import Icon, { type IconName } from "./Icon";

const AGENT_META: Record<string, { icon: IconName; description: string; accent: number }> = {
  market: { icon: "activity", description: "Prices, volumes, circuit breakers", accent: 0 },
  news: { icon: "news", description: "News sentiment across Indian sources", accent: 1 },
  social: { icon: "social", description: "StockTwits & YouTube market sentiment", accent: 2 },
  corporate_action: { icon: "briefcase", description: "Dividends, splits, bonuses, earnings", accent: 3 },
  regulatory_announcement: { icon: "file-text", description: "NSE regulatory & compliance filings", accent: 4 },
  econ_calendar: { icon: "calendar", description: "Macro releases: CPI, GDP, rates", accent: 5 },
  sector_rotation: { icon: "rotate", description: "Sector momentum & rotation trend", accent: 6 },
  risk: { icon: "shield", description: "Volatility & liquidity risk score", accent: 7 },
  recommendation: { icon: "target", description: "AI-scored Buy/Hold/Sell insight", accent: 8 },
  alert: { icon: "bell", description: "Rule-based threshold alerts", accent: 9 },
};

// Exported so every view of agent status (dashboard cards, the sidebar
// mini-panel, the Run Detail table on /agents) renders the exact same
// label for the exact same `state` — a prior version had the Run Detail
// table deriving its own Active/Idle text from the boolean `active` field
// instead of `state`, which could disagree with the cards above it for an
// agent that ran fine but produced no new output this cycle (state="idle"
// but active=true).
export const STATE_LABEL: Record<AgentStatusItem["state"], string> = {
  active: "Active",
  idle: "Idle",
  not_active: "Not active",
};

const EMPTY_AGENT: Pick<AgentStatusItem, "active" | "state" | "last_run" | "output_24h" | "history" | "caption"> = {
  active: false,
  state: "not_active",
  last_run: null,
  output_24h: null,
  history: [],
  caption: null,
};

// Real per-bucket counts, normalized against that agent's own peak bucket —
// standard sparkline scaling. A flat 6% floor keeps zero-count buckets
// visible as a real "nothing happened here" bar instead of disappearing,
// which would look identical to missing data.
function barHeights(history: number[]): number[] {
  const max = Math.max(1, ...history);
  return history.map((v) => (v === 0 ? 6 : Math.max(10, Math.round((v / max) * 100))));
}

export default function AgentStatusRow() {
  const [agents, setAgents] = useState<AgentStatusItem[]>([]);

  useEffect(() => {
    const load = () => api.agentsStatus().then(setAgents).catch(() => {});
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, []);

  const rows = agents.length
    ? agents
    : Object.keys(AGENT_META).map((name) => ({ name, label: name, ...EMPTY_AGENT }));

  return (
    <section className="agent-card-row" aria-label="AI agent status">
      {rows.map((a) => {
        const meta = AGENT_META[a.name] ?? { icon: "overview" as IconName, description: "", accent: 0 };
        return (
          <div className={`agent-card agent-card-accent-${meta.accent % 10}`} key={a.name}>
            <div className="agent-card-head">
              <Icon name={meta.icon} size={16} />
              <span className="agent-card-title">{a.label}</span>
            </div>
            <p className="agent-card-desc">{meta.description}</p>
            <span className={`agent-card-pill agent-card-pill-${a.state}`}>
              <Icon name="dot" size={8} /> {STATE_LABEL[a.state]}
            </span>
            {a.history.length > 0 ? (
              <>
                <div className="agent-card-spark" role="img" aria-label={a.caption ?? undefined}>
                  {barHeights(a.history).map((h, i) => (
                    <span key={i} style={{ height: `${h}%` }} />
                  ))}
                </div>
                <p className="agent-card-caption">{a.caption}</p>
              </>
            ) : (
              <p className="agent-card-caption agent-card-caption-muted">
                Live on view — no stored history
              </p>
            )}
          </div>
        );
      })}
    </section>
  );
}
