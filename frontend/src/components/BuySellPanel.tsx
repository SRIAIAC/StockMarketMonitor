import { useEffect, useState } from "react";
import { api, type RecommendationItem, type RecommendationsData } from "../api/client";

const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 2,
});

function SignalCard({
  item,
  type,
  rank,
}: {
  item: RecommendationItem;
  type: "buy" | "sell";
  rank: number;
}) {
  const isBuy = type === "buy";
  const price: number | null = item.price ?? null;
  const pct: number | null = item.pct_change ?? null;

  return (
    <div className={`signal-card ${isBuy ? "signal-buy" : "signal-sell"}`}>
      <div className="signal-rank">#{rank}</div>
      <div className="signal-body">
        <div className="signal-top">
          <strong className="signal-ticker">
            {item.symbol || item.ticker.replace(".NS", "")}
          </strong>
          <span className={`signal-badge ${isBuy ? "badge-buy" : "badge-sell"}`}>
            {isBuy ? "BUY" : "SELL"}
          </span>
        </div>

        {price !== null ? (
          <div className="signal-price">
            {inr.format(price)}
            {pct !== null && (
              <span className={pct >= 0 ? "pct-up" : "pct-down"}>
                {pct >= 0 ? " +" : " "}
                {pct.toFixed(2)}%
              </span>
            )}
          </div>
        ) : (
          <div className="signal-price" style={{ color: "var(--muted)" }}>Price unavailable</div>
        )}

        {item.sector && <div className="signal-sector">{item.sector}</div>}
        <div className="signal-reason">{item.reason}</div>

        {item.source_url && (
          <a
            href={item.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="signal-source-link"
          >
            View source →
          </a>
        )}
      </div>
    </div>
  );
}

export default function BuySellPanel() {
  const [data, setData] = useState<RecommendationsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.marketRecommendations()
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));

    const id = setInterval(() => {
      api.marketRecommendations().then(setData).catch(console.error);
    }, 10 * 60_000);
    return () => clearInterval(id);
  }, []);

  const sourceLabel = data?.source ?? "loading…";

  return (
    <section className="panel buysell-panel">
      <div className="news-header">
        <div>
          <p className="eyebrow">Web search · {sourceLabel}</p>
          <h2>Buy / Sell Recommendations</h2>
        </div>
        <span className="market-chip">NSE market-wide</span>
      </div>

      <div className="buysell-grid">
        <div className="buysell-col">
          <p className="buysell-col-label buysell-buy-label">▲ Buy Signals</p>
          {data?.buy.map((item, i) => (
            <SignalCard key={`${item.ticker}-${i}`} item={item} type="buy" rank={i + 1} />
          ))}
          {loading && <p className="muted-row">Searching web for recommendations…</p>}
          {!loading && data?.buy.length === 0 && (
            <p className="muted-row">No buy signals found</p>
          )}
        </div>

        <div className="buysell-col">
          <p className="buysell-col-label buysell-sell-label">▼ Sell Signals</p>
          {data?.sell.map((item, i) => (
            <SignalCard key={`${item.ticker}-${i}`} item={item} type="sell" rank={i + 1} />
          ))}
          {loading && <p className="muted-row">Searching web for recommendations…</p>}
          {!loading && data?.sell.length === 0 && (
            <p className="muted-row">No sell signals found</p>
          )}
        </div>
      </div>

      <p className="signal-disclaimer">
        Sourced from analyst articles via web search. Enriched with live NSE prices.
        Not financial advice.
      </p>
    </section>
  );
}
