import { useEffect, useState } from "react";
import { api, type NewsItem } from "../api/client";

function sentimentTag(score: number | null): { label: string; cls: string } {
  if (score === null) return { label: "Neutral", cls: "neutral" };
  if (score > 0.2) return { label: "Positive", cls: "positive" };
  if (score < -0.2) return { label: "Negative", cls: "negative" };
  return { label: "Neutral", cls: "neutral" };
}

function formatTime(value: string | null): string {
  if (!value) return "";
  return new Intl.DateTimeFormat("en-IN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" }).format(new Date(value));
}

function NewsList({ items }: { items: NewsItem[] }) {
  return (
    <ul className="news-list">
      {items.map((item) => {
        const { label, cls } = sentimentTag(item.sentiment);
        return (
          <li key={item.id} className="news-item">
            <div className="news-meta">
              <span className="news-time">{formatTime(item.published_at ?? item.fetched_at)}</span>
              {item.ticker && <span className="news-ticker">{item.ticker.replace(".NS", "")}</span>}
              <span className="news-source">{item.source}</span>
              <span className={`news-sentiment ${cls}`}>{label}</span>
            </div>
            <a href={item.url} target="_blank" rel="noopener noreferrer" className="news-title">
              {item.title}
            </a>
          </li>
        );
      })}
      {items.length === 0 && <li className="muted-row">No recent news</li>}
    </ul>
  );
}

export default function NewsPanel({ compact = false, limit }: { compact?: boolean; limit?: number }) {
  const [items, setItems] = useState<NewsItem[]>([]);

  useEffect(() => {
    api.news().then(setItems).catch(console.error);
    const id = setInterval(() => api.news().then(setItems).catch(console.error), 300_000);
    return () => clearInterval(id);
  }, []);

  if (compact) {
    const combined = [...items]
      .sort((a, b) => (b.published_at ?? b.fetched_at ?? "").localeCompare(a.published_at ?? a.fetched_at ?? ""))
      .slice(0, limit ?? 8);
    return (
      <section className="panel news-panel news-panel-compact">
        <div className="news-header">
          <div>
            <p className="eyebrow">Live headlines</p>
            <h2>News Intelligence</h2>
          </div>
        </div>
        <NewsList items={combined} />
      </section>
    );
  }

  const internationalItems = items.filter((item) => item.source.includes("International"));
  const indianItems = items.filter((item) => !item.source.includes("International"));

  return (
    <section className="panel news-panel">
      <div className="news-header">
        <div>
          <p className="eyebrow">Live headlines · 24 h</p>
          <h2>News Intelligence</h2>
        </div>
        <span className="market-chip">VADER scored</span>
      </div>
      <div className="news-columns">
        <div className="news-column">
          <h3 className="news-column-title">Indian News</h3>
          <NewsList items={indianItems} />
        </div>
        <div className="news-column">
          <h3 className="news-column-title">International News</h3>
          <NewsList items={internationalItems} />
        </div>
      </div>
    </section>
  );
}
