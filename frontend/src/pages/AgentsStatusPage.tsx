import { useEffect, useState } from "react";
import { api, type AgentStatusItem } from "../api/client";
import AgentStatusRow, { STATE_LABEL } from "../components/AgentStatusRow";

function formatTime(value: string | null): string {
  if (!value) return "Not run yet this session";
  return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "medium", timeZone: "Asia/Kolkata" }).format(new Date(value));
}

const STATE_CLASS: Record<AgentStatusItem["state"], string> = {
  active: "pct-up",
  idle: "pct-neutral",
  not_active: "pct-down",
};

export default function AgentsStatusPage() {
  const [agents, setAgents] = useState<AgentStatusItem[]>([]);

  useEffect(() => {
    const load = () => api.agentsStatus().then(setAgents).catch(() => {});
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="dashboard">
      <header className="page-header">
        <p className="eyebrow">10 agents, run every 30 minutes</p>
        <h1>AI Agents Status</h1>
      </header>
      <AgentStatusRow />

      <section className="panel">
        <h2>Run Detail</h2>
        <table>
          <thead>
            <tr>
              <th>Agent</th>
              <th>Status</th>
              <th>Last run (IST)</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((a) => (
              <tr key={a.name}>
                <td>{a.label}</td>
                <td className={STATE_CLASS[a.state]}>{STATE_LABEL[a.state]}</td>
                <td>{formatTime(a.last_run)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
