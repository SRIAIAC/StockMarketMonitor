import { useEffect, useRef, useState } from "react";
import Chart from "chart.js/auto";
import { api, type IndexSeriesPoint } from "../api/client";

const INDICES = ["NIFTY 50", "SENSEX", "NIFTY BANK"];
const RANGES = ["1D", "1W", "1M", "3M", "6M", "1Y"];

export default function MarketOverviewChart() {
  const [index, setIndex] = useState(INDICES[0]);
  const [range, setRange] = useState("1D");
  const [points, setPoints] = useState<IndexSeriesPoint[] | null>(null);
  const [loading, setLoading] = useState(true);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartInstance = useRef<Chart | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .indexSeries(index, range)
      .then((p) => !cancelled && setPoints(p))
      .catch(() => !cancelled && setPoints([]))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [index, range]);

  useEffect(() => () => chartInstance.current?.destroy(), []);

  useEffect(() => {
    if (!canvasRef.current || !points || points.length < 2) {
      chartInstance.current?.destroy();
      chartInstance.current = null;
      return;
    }
    chartInstance.current?.destroy();

    const up = points[points.length - 1].c >= points[0].c;
    const lineColor = up ? "#34d399" : "#f87171";

    chartInstance.current = new Chart(canvasRef.current, {
      type: "line",
      data: {
        labels: points.map((p) =>
          range === "1D"
            ? new Date(p.t).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" })
            : new Date(p.t).toLocaleDateString("en-IN", { day: "2-digit", month: "short" })
        ),
        datasets: [
          {
            data: points.map((p) => p.c),
            borderColor: lineColor,
            backgroundColor: (ctx) => {
              const { chartArea, ctx: c } = ctx.chart;
              if (!chartArea) return "transparent";
              const gradient = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
              gradient.addColorStop(0, up ? "rgba(52,211,153,0.25)" : "rgba(248,113,113,0.25)");
              gradient.addColorStop(1, "rgba(0,0,0,0)");
              return gradient;
            },
            fill: true,
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.25,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 250 },
        plugins: { legend: { display: false }, tooltip: { mode: "index", intersect: false } },
        scales: {
          x: { ticks: { maxTicksLimit: 7, color: "var(--muted)" }, grid: { display: false } },
          y: { ticks: { color: "var(--muted)" }, grid: { color: "rgba(127,140,150,0.15)" } },
        },
      },
    });
  }, [points, range]);

  const first = points?.[0]?.c;
  const last = points && points.length ? points[points.length - 1].c : undefined;
  const changePct = first && last ? ((last - first) / first) * 100 : null;

  return (
    <div className="panel market-overview-chart-panel">
      <div className="market-overview-chart-head">
        <div className="market-overview-tabs">
          {INDICES.map((i) => (
            <button
              key={i}
              className={"market-overview-tab" + (i === index ? " market-overview-tab-active" : "")}
              onClick={() => setIndex(i)}
            >
              {i}
            </button>
          ))}
        </div>
        {last !== undefined && (
          <div className="market-overview-chart-value">
            <strong>{last.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</strong>
            {changePct !== null && (
              <span className={changePct >= 0 ? "pct-up" : "pct-down"}>
                {changePct >= 0 ? "+" : ""}
                {changePct.toFixed(2)}%
              </span>
            )}
          </div>
        )}
      </div>

      <div className="market-overview-chart-canvas">
        {loading && <p className="muted-row">Loading {index} chart…</p>}
        {!loading && (!points || points.length < 2) && (
          <p className="muted-row">
            {range === "1D"
              ? "Live intraday series unavailable right now (only populated during NSE trading hours)."
              : "Historical series unavailable right now — source may be rate-limited."}
          </p>
        )}
        <canvas ref={canvasRef} role="img" aria-label={`${index} price chart, ${range} range`} />
      </div>

      <div className="market-overview-ranges">
        {RANGES.map((r) => (
          <button
            key={r}
            className={"market-overview-range" + (r === range ? " market-overview-range-active" : "")}
            onClick={() => setRange(r)}
          >
            {r}
          </button>
        ))}
      </div>
    </div>
  );
}
