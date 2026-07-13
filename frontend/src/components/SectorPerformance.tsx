import { useEffect, useState } from "react";
import { api, type SectorPerf } from "../api/client";
import Icon from "./Icon";

const SHOW_LIMIT = 5;

const TREND_ICON = { up: "arrow-up", down: "arrow-down", neutral: "minus" } as const;
const TREND_CLASS = { up: "pct-up", down: "pct-down", neutral: "" } as const;

export default function SectorPerformance({ compact = true }: { compact?: boolean }) {
  const [sectors, setSectors] = useState<SectorPerf[]>([]);
  const [expanded, setExpanded] = useState(!compact);

  useEffect(() => {
    const load = () => api.sectors().then(setSectors).catch(console.error);
    load();
    const id = setInterval(load, 5 * 60_000);
    return () => clearInterval(id);
  }, []);

  const sortedSectors = [...sectors].sort((a, b) => b.momentum_score - a.momentum_score);
  const showLimit = compact ? SHOW_LIMIT : sortedSectors.length;
  const visibleSectors = expanded ? sortedSectors : sortedSectors.slice(0, showLimit);
  const hasMore = compact && sortedSectors.length > showLimit;

  return (
    <div className="panel chart-panel sector-rotation-panel">
      <p className="eyebrow">India breadth · NSE sectoral indices</p>
      <h2>Sector Rotation (Momentum)</h2>
      {visibleSectors.length === 0 ? (
        <p className="muted-row">Waiting for sector data</p>
      ) : (
        <table className="sector-rotation-table">
          <thead>
            <tr>
              <th>Sector</th>
              <th>Momentum</th>
              <th>Trend</th>
            </tr>
          </thead>
          <tbody>
            {visibleSectors.map((s) => (
              <tr key={s.sector}>
                <td>
                  {s.sector}
                  <small>{s.count} {s.count === 1 ? "company" : "companies"}</small>
                </td>
                <td>
                  <div className="momentum-bar-track">
                    <span className="momentum-bar-fill" style={{ width: `${s.momentum_score}%` }} />
                  </div>
                  <span className="momentum-bar-value">{Math.round(s.momentum_score)}</span>
                </td>
                <td className={TREND_CLASS[s.trend]}>
                  <Icon name={TREND_ICON[s.trend]} size={14} /> {s.trend}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {hasMore && (
        <button className="show-more-btn" onClick={() => setExpanded((e) => !e)}>
          {expanded ? "Show less ▲" : `Show ${sortedSectors.length - showLimit} more ▼`}
        </button>
      )}
    </div>
  );
}
