import { useEffect, useState } from "react";
import { api, type YouTubeInsightItem, type YouTubeSentimentSummaryData } from "../api/client";
import { displayTicker } from "../marketBuckets";

const SHOW_LIMIT = 5;

const RECOMMENDATION_COLOR: Record<string, string> = {
  BUY: "#16a34a",
  SELL: "#dc2626",
  HOLD: "#6b7280",
};

const TONE_COLOR: Record<string, string> = {
  Bullish: "#16a34a",
  Bearish: "#dc2626",
  Neutral: "#6b7280",
};

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const diffMs = Date.now() - new Date(iso).getTime();
  const days = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (days <= 0) return "today";
  if (days === 1) return "1 day ago";
  return `${days} days ago`;
}

export default function YouTubeSentiment() {
  const [insights, setInsights] = useState<YouTubeInsightItem[]>([]);
  const [summary, setSummary] = useState<YouTubeSentimentSummaryData | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    const load = () => {
      api.youtubeInsights().then(setInsights).catch(console.error);
      api.youtubeSentimentSummary().then(setSummary).catch(console.error);
    };
    load();
    const id = setInterval(load, 5 * 60_000);
    return () => clearInterval(id);
  }, []);

  const visible = expanded ? insights : insights.slice(0, SHOW_LIMIT);
  const hasMore = insights.length > SHOW_LIMIT;

  return (
    <div className="panel">
      <p className="eyebrow">CA Rachana Ranade &middot; SOIC &middot; Groww &middot; Zerodha Varsity &middot; ET Now &middot; CNBC-TV18</p>
      <div className="panel-title-row">
        <h2>YouTube Analyst Sentiment</h2>
        <span className="panel-ai-badge">AI</span>
      </div>
      {summary?.summary && (
        <div className="ai-summary-box">
          {summary.ai_generated && <span className="ai-reason-badge">AI</span>}
          <p>{summary.summary}</p>
        </div>
      )}
      <ul className="alert-list">
        {visible.map((item) => (
          <li key={item.id} style={{ borderLeftColor: TONE_COLOR[item.tone] || "#999" }}>
            <span className="alert-ticker">{displayTicker(item.ticker)}</span>
            <span className="alert-message">
              <a href={item.video_url} target="_blank" rel="noreferrer">
                {item.video_title}
              </a>
              <small className="yt-meta">
                {item.channel} &middot; {timeAgo(item.published_at)}
                {item.language !== "en" && " · best-effort (non-English transcript)"}
              </small>
            </span>
            {item.topics.length > 0 && (
              <span className="alert-reason">{item.topics.join(" · ")}</span>
            )}
            <span className="yt-badges">
              {item.recommendation && (
                <span
                  className="yt-badge"
                  style={{ background: RECOMMENDATION_COLOR[item.recommendation] || "#6b7280" }}
                >
                  {item.recommendation}
                </span>
              )}
              <span className="yt-badge" style={{ background: TONE_COLOR[item.tone] || "#6b7280" }}>
                {item.tone}
              </span>
            </span>
          </li>
        ))}
        {visible.length === 0 && <li className="alert-empty">No YouTube insights yet</li>}
      </ul>
      {hasMore && (
        <button className="show-more-btn" onClick={() => setExpanded((e) => !e)}>
          {expanded ? "Show less ▲" : `Show ${insights.length - SHOW_LIMIT} more ▼`}
        </button>
      )}
    </div>
  );
}
