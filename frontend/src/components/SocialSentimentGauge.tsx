import { useEffect, useState } from "react";
import { api, type SocialSentimentData } from "../api/client";

// Semicircular gauge, 180deg arc from angle 180 (left) to 0 (right).
function GaugeArc({ score }: { score: number | null }) {
  const r = 70;
  const cx = 90;
  const cy = 82;
  const angleFor = (pct: number) => 180 - (pct / 100) * 180;
  const point = (angleDeg: number) => {
    const rad = (angleDeg * Math.PI) / 180;
    return [cx + r * Math.cos(rad), cy - r * Math.sin(rad)];
  };
  const [x1, y1] = point(180);
  const [x2, y2] = point(0);
  const needleAngle = angleFor(score ?? 50);
  const [nx, ny] = point(needleAngle);

  const color = score === null ? "var(--muted)" : score > 55 ? "var(--success)" : score < 45 ? "var(--danger)" : "var(--muted)";

  return (
    <svg viewBox="0 0 180 100" className="sentiment-gauge-svg" role="img" aria-label="Social sentiment gauge">
      <path d={`M ${x1} ${y1} A ${r} ${r} 0 0 1 ${x2} ${y2}`} className="sentiment-gauge-track" />
      {score !== null && (
        <path
          d={`M ${x1} ${y1} A ${r} ${r} 0 0 1 ${nx} ${ny}`}
          stroke={color}
          strokeWidth={10}
          strokeLinecap="round"
          fill="none"
        />
      )}
      <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="var(--text-h)" strokeWidth={2} />
      <circle cx={cx} cy={cy} r={4} fill="var(--text-h)" />
    </svg>
  );
}

function PlatformBar({ label, score, connected }: { label: string; score: number | null; connected: boolean }) {
  return (
    <div className="sentiment-platform-row">
      <span className="sentiment-platform-label">{label}</span>
      {connected && score !== null ? (
        <>
          <div className="sentiment-platform-track">
            <span className="sentiment-platform-fill" style={{ width: `${score}%` }} />
          </div>
          <span className="sentiment-platform-score">{Math.round(score)}</span>
        </>
      ) : (
        <span className="sentiment-platform-disconnected">
          {connected ? "No data yet" : "Not connected"}
        </span>
      )}
    </div>
  );
}

export default function SocialSentimentGauge() {
  const [data, setData] = useState<SocialSentimentData | null>(null);

  useEffect(() => {
    const load = () => api.socialSentiment().then(setData).catch(() => {});
    load();
    const id = setInterval(load, 5 * 60_000);
    return () => clearInterval(id);
  }, []);

  const platforms = data?.platforms;

  return (
    <div className="panel sentiment-gauge-panel">
      <p className="eyebrow">StockTwits · YouTube</p>
      <h2>Social Sentiment</h2>

      <div className="sentiment-gauge-head">
        <span className={"sentiment-gauge-label " + (data?.overall_label === "Bullish" ? "pct-up" : data?.overall_label === "Bearish" ? "pct-down" : "")}>
          {data?.overall_label ?? "—"}
        </span>
        <span className="sentiment-gauge-score">
          {data?.overall_score !== null && data?.overall_score !== undefined ? Math.round(data.overall_score) : "—"}
          <small>/100</small>
        </span>
      </div>

      <GaugeArc score={data?.overall_score ?? null} />

      <div className="sentiment-platforms">
        <PlatformBar label="StockTwits" score={platforms?.stocktwits.score ?? null} connected={platforms?.stocktwits.connected ?? true} />
        <PlatformBar label="YouTube" score={platforms?.youtube.score ?? null} connected={platforms?.youtube.connected ?? true} />
      </div>
    </div>
  );
}
