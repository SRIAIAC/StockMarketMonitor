import { useState } from "react";
import type { WatchlistItem } from "../api/client";
import { capBucketFor, displayTicker } from "../marketBuckets";

const SHOW_LIMIT = 5;

function scale(value: number, max: number): number {
  if (!max) return 0;
  return Math.max(4, Math.min(100, (value / max) * 100));
}

interface ShareWiseChartsProps {
  watchlist: WatchlistItem[];
}

export default function ShareWiseCharts({ watchlist }: ShareWiseChartsProps) {
  const [expanded, setExpanded] = useState(false);
  const priced = watchlist.filter((item) => item.pct_change !== null);
  const moveMax = Math.max(...priced.map((item) => Math.abs(Number(item.pct_change))), 0);
  const sortedByMove = [...priced].sort((a, b) => Math.abs(Number(b.pct_change)) - Math.abs(Number(a.pct_change)));
  const visibleItems = expanded ? sortedByMove : sortedByMove.slice(0, SHOW_LIMIT);
  const hasMore = sortedByMove.length > SHOW_LIMIT;

  return (
      <div className="panel chart-panel">
        <p className="eyebrow">Share-wise graph</p>
        <h2>Day Move by Share</h2>
        <div className="axis-chart move-chart">
          {visibleItems.map((item) => {
            const pctChange = Number(item.pct_change);
            const width = scale(Math.abs(pctChange), moveMax);
            const direction = pctChange >= 0 ? "positive" : "negative";

            return (
              <div className="axis-row" key={item.ticker}>
                <span className="axis-label">
                  {displayTicker(item.ticker)}
                  <small>{capBucketFor(item.ticker)}</small>
                </span>
                <div className="axis-track">
                  <span className="axis-zero" />
                  <span className={`axis-bar ${direction}`} style={{ width: `${width / 2}%` }} />
                </div>
                <strong className={pctChange >= 0 ? "pct-up" : "pct-down"}>
                  {pctChange >= 0 ? "+" : ""}
                  {pctChange.toFixed(2)}%
                </strong>
              </div>
            );
          })}
          {priced.length === 0 && <p className="muted-row">Waiting for share prices</p>}
        </div>
        {hasMore && (
          <button className="show-more-btn" onClick={() => setExpanded((e) => !e)}>
            {expanded ? "Show less ▲" : `Show ${sortedByMove.length - SHOW_LIMIT} more ▼`}
          </button>
        )}
      </div>
  );
}
