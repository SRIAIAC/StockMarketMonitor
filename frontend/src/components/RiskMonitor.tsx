import { useEffect, useState } from "react";
import { api, type RiskScore } from "../api/client";

const LABEL_COLOR: Record<string, string> = {
  Low: "var(--success)",
  Moderate: "#f59e0b",
  High: "var(--danger)",
};

function RadialGauge({ score, label }: { score: number; label: string }) {
  const r = 52;
  const circumference = 2 * Math.PI * r;
  const filled = (score / 100) * circumference;
  const color = LABEL_COLOR[label] ?? "var(--muted)";

  return (
    <svg viewBox="0 0 130 130" className="risk-gauge-svg" role="img" aria-label={`Risk score ${score} out of 100, ${label}`}>
      <circle cx="65" cy="65" r={r} className="risk-gauge-track" />
      <circle
        cx="65"
        cy="65"
        r={r}
        stroke={color}
        strokeWidth={12}
        strokeLinecap="round"
        fill="none"
        strokeDasharray={`${filled} ${circumference}`}
        transform="rotate(-90 65 65)"
      />
      <text x="65" y="60" textAnchor="middle" className="risk-gauge-value">
        {Math.round(score)}
      </text>
      <text x="65" y="80" textAnchor="middle" className="risk-gauge-max">
        / 100
      </text>
    </svg>
  );
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="risk-stat-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default function RiskMonitor() {
  const [risk, setRisk] = useState<RiskScore | null>(null);

  useEffect(() => {
    const load = () => api.riskScore().then(setRisk).catch(() => {});
    load();
    const id = setInterval(load, 5 * 60_000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="panel risk-monitor-panel">
      <div className="news-header">
        <div>
          <p className="eyebrow">Volatility & liquidity</p>
          <h2>Risk Monitor</h2>
        </div>
      </div>

      {!risk ? (
        <p className="muted-row">Waiting for the risk agent's next run…</p>
      ) : (
        <>
          <div className="risk-gauge-head">
            <RadialGauge score={risk.risk_score} label={risk.risk_label} />
            <div>
              <p className="risk-gauge-title">RISK SCORE</p>
              <p className="risk-gauge-label" style={{ color: LABEL_COLOR[risk.risk_label] }}>
                {risk.risk_label}
              </p>
            </div>
          </div>

          <div className="risk-stats">
            <StatRow label="Volatility Index (India VIX)" value={risk.india_vix !== null ? risk.india_vix.toFixed(2) : "—"} />
            <StatRow
              label="Market Breadth"
              value={
                risk.advances !== null && risk.declines !== null
                  ? `${(risk.breadth_ratio! * 100).toFixed(0)}% adv`
                  : "—"
              }
            />
            <StatRow label="Watchlist Volatility" value={risk.watchlist_volatility !== null ? `${risk.watchlist_volatility.toFixed(2)}%` : "—"} />
            <StatRow label="Unusual Activity" value={`${risk.volume_spike_count} alert${risk.volume_spike_count === 1 ? "" : "s"}`} />
          </div>
        </>
      )}
    </div>
  );
}
