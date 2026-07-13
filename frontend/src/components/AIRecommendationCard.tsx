import { useEffect, useState } from "react";
import { api, type RecommendationPick, type RecommendationPicksData } from "../api/client";

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });

const LABEL_CLASS: Record<string, string> = {
  Buy: "rec-badge-buy",
  Hold: "rec-badge-hold",
  Sell: "rec-badge-sell",
};

function PickRow({ pick, rank }: { pick: RecommendationPick; rank: number }) {
  return (
    <div className="rec-row">
      <span className="rec-rank">#{rank}</span>
      <div className="rec-row-main">
        <div className="rec-row-top">
          <strong>{pick.ticker.replace(".NS", "")}</strong>
          <span className={`rec-badge ${LABEL_CLASS[pick.label] ?? ""}`}>{pick.label}</span>
          <span className="rec-confidence">{Math.round(pick.confidence)}%</span>
        </div>
        {pick.price !== null && (
          <div className="rec-row-price">
            {inr.format(pick.price)}
            {pick.pct_change !== null && (
              <span className={pick.pct_change >= 0 ? "pct-up" : "pct-down"}>
                {" "}
                {pick.pct_change >= 0 ? "+" : ""}
                {pick.pct_change.toFixed(2)}%
              </span>
            )}
          </div>
        )}
        <p className="rec-row-reason">
          {pick.ai_reason && <span className="ai-reason-badge">AI</span>}
          {pick.ai_reason || pick.reason}
        </p>
      </div>
    </div>
  );
}

export default function AIRecommendationCard({ limit = 5 }: { limit?: number }) {
  const [data, setData] = useState<RecommendationPicksData | null>(null);

  useEffect(() => {
    const load = () => api.recommendations().then(setData).catch(() => {});
    load();
    const id = setInterval(load, 5 * 60_000);
    return () => clearInterval(id);
  }, []);

  const picks = (data?.picks ?? []).slice(0, limit);

  return (
    <div className="panel ai-rec-panel">
      <div className="news-header">
        <div>
          <p className="eyebrow">Watchlist · agent-scored</p>
          <div className="panel-title-row">
            <h2>AI Recommendation</h2>
            <span className="panel-ai-badge">AI</span>
          </div>
        </div>
        <span className="market-chip">Top {limit} picks</span>
      </div>

      {picks.length === 0 && <p className="muted-row">Waiting for the recommendation agent's next run…</p>}
      {picks.map((p, i) => (
        <PickRow pick={p} rank={i + 1} key={p.ticker} />
      ))}

      <p className="signal-disclaimer">Confidence-scored from price momentum, sentiment, sector rotation, and risk. Not financial advice.</p>
    </div>
  );
}
