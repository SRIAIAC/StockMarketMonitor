import { useEffect, useState } from "react";
import { api, type SentimentItem } from "../api/client";

function sentimentColor(score: number): string {
  if (score > 0.2) return "#16a34a";
  if (score < -0.2) return "#dc2626";
  return "#9ca3af";
}

export default function SentimentHeatmap() {
  const [items, setItems] = useState<SentimentItem[]>([]);

  useEffect(() => {
    api.sentimentHeatmap().then(setItems).catch(console.error);
  }, []);

  return (
    <div className="panel">
      <p className="eyebrow">News and social</p>
      <h2>Sentiment Heatmap (24h)</h2>
      <div className="heatmap-grid">
        {items.map((s) => (
          <div key={s.ticker} className="heatmap-cell" style={{ backgroundColor: sentimentColor(s.avg_sentiment) }}>
            <div className="heatmap-ticker">{s.ticker.replace(".NS", "")}</div>
            <div className="heatmap-score">{s.avg_sentiment.toFixed(2)}</div>
          </div>
        ))}
        {items.length === 0 && <p className="muted-row">No India sentiment data yet</p>}
      </div>
    </div>
  );
}
