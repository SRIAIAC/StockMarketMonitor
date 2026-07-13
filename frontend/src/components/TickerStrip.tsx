import { useEffect, useState } from "react";
import { api, type MoversData } from "../api/client";

export default function TickerStrip() {
  const [data, setData] = useState<MoversData | null>(null);

  useEffect(() => {
    const load = () => api.marketMovers().then(setData).catch(() => {});
    load();
    const id = setInterval(load, 5 * 60_000);
    return () => clearInterval(id);
  }, []);

  const gainers = data?.gainers ?? [];
  const losers = data?.losers ?? [];
  if (gainers.length === 0 && losers.length === 0) return null;

  return (
    <div className="ticker-strip" role="marquee" aria-label="Top gainers and losers">
      <div className="ticker-strip-track">
        {[0, 1].map((rep) => (
          <div className="ticker-strip-group" key={rep} aria-hidden={rep === 1}>
            <span className="ticker-strip-label ticker-strip-label-up">TOP GAINERS</span>
            {gainers.map((g) => (
              <span className="ticker-strip-item pct-up" key={`g-${rep}-${g.ticker}`}>
                {g.symbol || g.ticker.replace(".NS", "")} +{g.pct_change.toFixed(2)}%
              </span>
            ))}
            <span className="ticker-strip-label ticker-strip-label-down">TOP LOSERS</span>
            {losers.map((l) => (
              <span className="ticker-strip-item pct-down" key={`l-${rep}-${l.ticker}`}>
                {l.symbol || l.ticker.replace(".NS", "")} {l.pct_change.toFixed(2)}%
              </span>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
