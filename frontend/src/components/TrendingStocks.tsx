import { useEffect, useState } from "react";
import { api, type TrendingItem } from "../api/client";

export default function TrendingStocks() {
  const [items, setItems] = useState<TrendingItem[]>([]);

  useEffect(() => {
    api.trending().then(setItems).catch(console.error);
  }, []);

  return (
    <div className="panel">
      <p className="eyebrow">NSE movers</p>
      <h2>Trending Shares</h2>
      <ul className="bar-list">
        {items.map((t) => (
          <li key={t.ticker}>
            <span className="bar-label">{t.ticker.replace(".NS", "")}</span>
            <span className={t.pct_change >= 0 ? "pct-up" : "pct-down"}>
              {t.pct_change >= 0 ? "+" : ""}
              {t.pct_change.toFixed(2)}%
            </span>
          </li>
        ))}
        {items.length === 0 && <li className="muted-row">Waiting for market movement</li>}
      </ul>
    </div>
  );
}
