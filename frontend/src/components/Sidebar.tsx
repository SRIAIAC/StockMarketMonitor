import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { api, type AgentStatusItem } from "../api/client";
import Icon, { type IconName } from "./Icon";

// `usesAI` marks nav items whose underlying agent actually calls Claude (or
// falls through to Ollama — see analysis/claude_client.py). Everything else
// in this list is pure rule-based/scraped, no LLM call ever. Kept in sync
// by hand with each agent's `claude_client.*` calls, not derived from the
// backend — update this list whenever a new AI touchpoint is added:
//   Overview          — OrchestratorAgent's briefing narration
//   Social Sentiment   — YouTubeAgent's sentiment roll-up summary
//   Corporate Actions — CorporateActionAgent's top-10 "why it matters"
//   SEBI Filings       — RegulatoryAnnouncementAgent's top-10 one-liner
//   Economic Calendar — EconCalendarAgent's top-10 one-liner
//   AI Recommendations — RecommendationAgent's one-line reasons + FiiDiiAgent's daily summary
//   Alerts             — AlertAgent's AI-escalated explanations
const NAV_ITEMS: { to: string; label: string; icon: IconName; end?: boolean; usesAI?: boolean }[] = [
  { to: "/", label: "Overview", icon: "overview", end: true, usesAI: true },
  { to: "/live-market", label: "Live Market", icon: "activity" },
  { to: "/news", label: "News Intelligence", icon: "news" },
  { to: "/social", label: "Social Sentiment", icon: "social", usesAI: true },
  { to: "/corporate-actions", label: "Corporate Actions", icon: "briefcase", usesAI: true },
  { to: "/sebi-filings", label: "SEBI Filings", icon: "file-text", usesAI: true },
  { to: "/economic-calendar", label: "Economic Calendar", icon: "calendar", usesAI: true },
  { to: "/sector-rotation", label: "Sector Rotation", icon: "rotate" },
  { to: "/risk-monitor", label: "Risk Monitor", icon: "shield" },
  { to: "/recommendations", label: "AI Recommendations", icon: "target", usesAI: true },
  { to: "/watchlist", label: "Watchlist", icon: "star" },
  { to: "/alerts", label: "Alerts", icon: "bell", usesAI: true },
];

const SECONDARY_NAV_ITEMS: { to: string; label: string; icon: IconName }[] = [
  { to: "/analytics", label: "Investment Alternatives", icon: "trending-up" },
  { to: "/calculators", label: "Calculators", icon: "calculator" },
];

const linkClass = ({ isActive }: { isActive: boolean }) =>
  "sidebar-link" + (isActive ? " sidebar-link-active" : "");

export default function Sidebar({ collapsed, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const [agents, setAgents] = useState<AgentStatusItem[]>([]);

  useEffect(() => {
    const load = () => api.agentsStatus().then(setAgents).catch(() => {});
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, []);

  // `state`, not the plain `active` boolean — an agent that ran fine but
  // produced nothing new this cycle is "idle", not "active", and this count
  // needs to agree with the dashboard cards and the /agents Run Detail
  // table rather than showing a different number for the same agent.
  const activeCount = agents.filter((a) => a.state === "active").length;
  const total = agents.length || 10;

  return (
    <aside className={"sidebar" + (collapsed ? " sidebar-collapsed" : "")}>
      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className={linkClass} onClick={onNavigate}>
            <Icon name={item.icon} />
            <span className="sidebar-link-label">{item.label}</span>
            {item.usesAI && <span className="sidebar-ai-badge">AI</span>}
          </NavLink>
        ))}
        <div className="sidebar-divider" />
        {SECONDARY_NAV_ITEMS.map((item) => (
          <NavLink key={item.to} to={item.to} className={linkClass} onClick={onNavigate}>
            <Icon name={item.icon} />
            <span className="sidebar-link-label">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-agent-status">
        <p className="sidebar-agent-status-title">AI AGENTS STATUS</p>
        <p className="sidebar-agent-status-count">
          {activeCount} / {total} <span>Active</span>
        </p>
        <div className="sidebar-agent-dots" aria-hidden="true">
          {(agents.length ? agents : Array.from({ length: 10 })).map((a, i) => (
            <span
              key={i}
              className={"sidebar-agent-dot" + (agents.length && (a as AgentStatusItem).state !== "active" ? " sidebar-agent-dot-off" : "")}
            />
          ))}
        </div>
        <p className="sidebar-agent-status-note">
          {activeCount === total ? "All agents are running" : `${total - activeCount} agent(s) need attention`}
        </p>
        <NavLink to="/agents" className="sidebar-view-details" onClick={onNavigate}>
          View Details
        </NavLink>
      </div>
    </aside>
  );
}
