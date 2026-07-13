import { useEffect, useMemo, useRef, useState } from "react";
import Chart, { type ChartDataset } from "chart.js/auto";

// ── Types ─────────────────────────────────────────────────────────────────────
type Risk = "conservative" | "moderate" | "aggressive";
type Goal = "retirement" | "wealth" | "education" | "home";
type Holding = { name: string; price0: number; mu: number; sigma: number; beta: number; amount: number };

type Evaluation = {
  totalReturn: number;
  annVol: number;
  sharpe: number;
  maxDrawdown: number;
};

// Distribution of outcomes across many independent simulated paths of the
// same portfolio/settings — this is what makes the "expected" numbers stable
// from click to click, unlike any single simulated path.
type EnsembleStats = {
  mean: number;
  median: number;
  p5: number;
  p95: number;
  probLoss: number;
  paths: number;
};

interface Allocation {
  equity: number;
  debt: number;
  gold: number;
  cash: number;
}

interface Instrument {
  label: string;
  examples: string;
  color: string;
}

// ── Known share catalog for search-to-add ────────────────────────────────────
// beta is an illustrative sensitivity-to-NIFTY estimate, at the same static/
// assumed fidelity as mu and sigma below — not a live-fetched figure.
const STOCK_CATALOG: Holding[] = [
  { name:'Reliance Industries', price0:1304, mu:25.0, sigma:10.3, beta:1.00, amount:20000 },
  { name:'HDFC Bank', price0:796, mu:28.0, sigma:17.5, beta:0.90, amount:20000 },
  { name:'Bharti Airtel', price0:1901, mu:22.0, sigma:35.2, beta:0.75, amount:20000 },
  { name:'ICICI Bank', price0:1410, mu:21.0, sigma:33.3, beta:1.15, amount:20000 },
  { name:'State Bank of India', price0:1051, mu:14.0, sigma:34.4, beta:1.35, amount:20000 },
  { name:'LG Electronics India', price0:1584, mu:11.0, sigma:54.9, beta:1.10, amount:20000 },
  { name:'Lupin', price0:2352, mu:8.0, sigma:90.0, beta:0.55, amount:20000 },
  { name:'GMR Airports', price0:104, mu:43.0, sigma:59.7, beta:1.50, amount:20000 },
  { name:'Hero MotoCorp', price0:5500, mu:10.0, sigma:38.1, beta:0.85, amount:20000 },
  { name:'Mazagon Dock Shipbuilders', price0:2704, mu:5.0, sigma:90.0, beta:1.05, amount:20000 },
  { name:'AWL Agri Business', price0:220, mu:15.0, sigma:53.8, beta:0.70, amount:10000 },
  { name:'Sterlite Technologies', price0:593, mu:15.0, sigma:90.0, beta:1.30, amount:10000 },
  { name:'KIOCL', price0:405, mu:25.0, sigma:90.0, beta:1.20, amount:10000 },
  { name:'Sumitomo Chemical India', price0:441, mu:19.0, sigma:32.1, beta:0.80, amount:10000 },
  { name:'Asahi India Glass', price0:849, mu:24.0, sigma:46.5, beta:1.00, amount:10000 },
];

// Levenshtein edit distance, used to tolerate typos in the share search box
function levenshtein(a: string, b: string): number {
  const dp: number[][] = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = 0; i <= a.length; i += 1) dp[i][0] = i;
  for (let j = 0; j <= b.length; j += 1) dp[0][j] = j;
  for (let i = 1; i <= a.length; i += 1) {
    for (let j = 1; j <= b.length; j += 1) {
      dp[i][j] = a[i - 1] === b[j - 1]
        ? dp[i - 1][j - 1]
        : 1 + Math.min(dp[i - 1][j - 1], dp[i - 1][j], dp[i][j - 1]);
    }
  }
  return dp[a.length][b.length];
}

function fuzzyMatch(query: string, target: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return false;
  const t = target.toLowerCase();
  if (t.includes(q)) return true;
  const threshold = q.length <= 3 ? 1 : Math.floor(q.length / 3);
  return [t, ...t.split(/\s+/)].some(w => levenshtein(q, w) <= threshold);
}

// ── Shared RNG + Monte Carlo helpers ─────────────────────────────────────────
// Box-Muller standard normal draw. Deliberately unseeded — a stock price
// simulation that always produced the same "random" path wouldn't be a
// simulation. The ensemble below is what turns this raw randomness into a
// stable, reportable expected outcome.
function randn(): number {
  let u = 0;
  let v = 0;
  while (u === 0) u = Math.random();
  while (v === 0) v = Math.random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

// CAPM: expected return = risk-free + beta * (market return - risk-free).
// Alpha is how far a holding's own assumed return sits above/below that.
function capmAlpha(muPct: number, betaVal: number, rfPct: number, marketPct: number): number {
  return muPct - (rfPct + betaVal * (marketPct - rfPct));
}

// Runs many independent copies of the same single-common-factor GBM model
// used by the animated drill (see stepDay) and returns the distribution of
// total portfolio returns. A lone simulated path is essentially one dice
// roll; averaging hundreds of them converges to a stable expected value by
// the law of large numbers, which is what makes this safe to show as a
// standing "expected outcome" that doesn't visibly change every click.
function runMonteCarlo(holdings: Holding[], corrPct: number, days: number, paths: number): EnsembleStats | null {
  const total = holdings.reduce((s, h) => s + h.amount, 0);
  if (total <= 0 || holdings.length === 0 || days <= 0) return null;
  const dt = 1 / 252;
  const rho = Math.max(0, Math.min(1, corrPct / 100));
  const n = holdings.length;
  const mus = holdings.map(h => h.mu / 100);
  const sigmas = holdings.map(h => Math.max(0, h.sigma) / 100);
  const units = holdings.map(h => h.amount / h.price0);
  const returns: number[] = new Array(paths);
  for (let p = 0; p < paths; p += 1) {
    const prices = holdings.map(h => h.price0);
    for (let d = 0; d < days; d += 1) {
      const f = randn();
      for (let i = 0; i < n; i += 1) {
        const eps = randn();
        const z = Math.sqrt(rho) * f + Math.sqrt(1 - rho) * eps;
        prices[i] *= Math.exp((mus[i] - 0.5 * sigmas[i] * sigmas[i]) * dt + sigmas[i] * Math.sqrt(dt) * z);
      }
    }
    const finalValue = units.reduce((s, u, i) => s + u * prices[i], 0);
    returns[p] = (finalValue / total - 1) * 100;
  }
  returns.sort((a, b) => a - b);
  const mean = returns.reduce((s, v) => s + v, 0) / paths;
  const median = returns[Math.floor(paths / 2)];
  const p5 = returns[Math.floor(paths * 0.05)];
  const p95 = returns[Math.min(paths - 1, Math.floor(paths * 0.95))];
  const probLoss = (returns.filter(v => v < 0).length / paths) * 100;
  return { mean, median, p5, p95, probLoss, paths };
}

// ── Moneycontrol-style allocation algorithm ──────────────────────────────────
//  Base: Rule of 100 (equity = 100 - age)
//  Adjusted by investment horizon (+1.5% equity per year beyond 5y)
//  Adjusted by risk profile (±20%)
//  Gold fixed at 10%, cash at 5%
function calcAllocation(age: number, horizon: number, risk: Risk): Allocation {
  const riskMod: Record<Risk, number> = { conservative: -20, moderate: 0, aggressive: 20 };
  const maxCap: Record<Risk, number> = { conservative: 60, moderate: 75, aggressive: 90 };
  const horizonBonus = Math.max(0, (horizon - 5) * 1.5);
  const rawEquity = (100 - age) + horizonBonus + riskMod[risk];
  const equity = Math.round(Math.min(maxCap[risk], Math.max(10, rawEquity)));
  const gold = 10;
  const cash = 5;
  const debt = Math.max(5, 100 - equity - gold - cash);
  // Normalize to exactly 100
  const total = equity + debt + gold + cash;
  return {
    equity: Math.round(equity * 100 / total),
    debt: Math.round(debt * 100 / total),
    gold: Math.round(gold * 100 / total),
    cash: Math.round(cash * 100 / total),
  };
}

// ── Instruments per asset class ───────────────────────────────────────────────
const INSTRUMENTS: Record<keyof Allocation, Instrument> = {
  equity: { label: "Equity",        color: "#f59e0b", examples: "Large Cap MF · Index Fund · ELSS · Direct Stocks" },
  debt:   { label: "Debt",          color: "#3b82f6", examples: "PPF · NPS · Debt Mutual Fund · Fixed Deposit · G-Sec" },
  gold:   { label: "Gold",          color: "#10b981", examples: "Sovereign Gold Bond (SGB) · Gold ETF · MMTC Gold" },
  cash:   { label: "Liquid / Cash", color: "#8b5cf6", examples: "Liquid Mutual Fund · Savings Account · Flexi-FD" },
};

// ── Conic-gradient pie chart ──────────────────────────────────────────────────
function PieChart({ alloc }: { alloc: Allocation }) {
  const segments: [keyof Allocation, number][] = [
    ["equity", alloc.equity],
    ["debt",   alloc.debt],
    ["gold",   alloc.gold],
    ["cash",   alloc.cash],
  ];
  let cursor = 0;
  const parts = segments.map(([key, pct]) => {
    const color = INSTRUMENTS[key].color;
    const from = cursor;
    cursor += pct;
    return `${color} ${from}% ${cursor}%`;
  });
  const gradient = `conic-gradient(${parts.join(", ")})`;
  return (
    <div className="pie-wrap">
      <div className="pie-chart" style={{ background: gradient }} />
      <div className="pie-legend">
        {segments.map(([key, pct]) => (
          <div key={key} className="pie-legend-row">
            <span className="pie-dot" style={{ background: INSTRUMENTS[key].color }} />
            <span className="pie-legend-label">{INSTRUMENTS[key].label}</span>
            <span className="pie-legend-pct">{pct}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── INR formatter ─────────────────────────────────────────────────────────────
const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });

// ── Goal labels ───────────────────────────────────────────────────────────────
const GOAL_LABELS: Record<Goal, string> = {
  retirement: "Retirement",
  wealth:     "Wealth Creation",
  education:  "Child's Education",
  home:       "Home Purchase",
};

// ── Main Calculator ───────────────────────────────────────────────────────────
function AssetAllocationCalculator() {
  const [age,         setAge]         = useState(30);
  const [horizon,     setHorizon]     = useState(15);
  const [risk,        setRisk]        = useState<Risk>("moderate");
  const [goal,        setGoal]        = useState<Goal>("wealth");
  const [customSip,   setCustomSip]   = useState(16000);
  const [editAlloc,   setEditAlloc]   = useState<Allocation>(() => calcAllocation(30, 15, "moderate"));

  // When risk profile button is clicked, reset percentages to that profile's defaults
  function handleRiskChange(r: Risk) {
    setRisk(r);
    setEditAlloc(calcAllocation(age, horizon, r));
  }

  // Proportionally adjust the other three fields to keep total = 100
  function updateAlloc(key: keyof Allocation, raw: number) {
    const val = Math.max(0, Math.min(100, Math.round(raw)));
    const others = (Object.keys(editAlloc) as (keyof Allocation)[]).filter(k => k !== key);
    const otherSum = others.reduce((s, k) => s + editAlloc[k], 0);
    const rest = 100 - val;
    const next = { ...editAlloc, [key]: val } as Allocation;
    if (otherSum > 0) {
      let assigned = 0;
      others.forEach((k, i) => {
        if (i < others.length - 1) {
          const share = Math.round(editAlloc[k] / otherSum * rest);
          next[k] = Math.max(0, share);
          assigned += next[k];
        } else {
          next[k] = Math.max(0, rest - assigned);
        }
      });
    } else {
      const each = Math.floor(rest / 3);
      others.forEach((k, i) => { next[k] = i < 2 ? each : rest - each * 2; });
    }
    setEditAlloc(next);
  }

  const monthly = customSip;

  const monthlySplit: Record<keyof Allocation, number> = {
    equity: Math.round(monthly * editAlloc.equity / 100),
    debt:   Math.round(monthly * editAlloc.debt   / 100),
    gold:   Math.round(monthly * editAlloc.gold   / 100),
    cash:   Math.round(monthly * editAlloc.cash   / 100),
  };

  // Projected corpus using simple CAGR per asset class
  const CAGR: Record<keyof Allocation, number> = { equity: 0.12, debt: 0.07, gold: 0.08, cash: 0.055 };
  const blendedCAGR = (editAlloc.equity / 100) * CAGR.equity
                    + (editAlloc.debt   / 100) * CAGR.debt
                    + (editAlloc.gold   / 100) * CAGR.gold
                    + (editAlloc.cash   / 100) * CAGR.cash;
  const months = horizon * 12;
  const r = blendedCAGR / 12;
  const futureValueSIP = monthly * ((Math.pow(1 + r, months) - 1) / r) * (1 + r);
  const investedAmount = monthly * months;
  const growth = futureValueSIP - investedAmount;
  const totalCorpus = futureValueSIP;

  return (
    <div className="calc-card">
      <div className="calc-header">
        <h2 className="calc-title">Asset Allocation Calculator</h2>
        <p className="calc-subtitle">
          Based on Moneycontrol's methodology — Rule of 100 adjusted for risk profile &amp; time horizon
        </p>
      </div>

      <div className="calc-body">
        {/* ── Inputs ── */}
        <div className="calc-inputs">

          <div className="calc-field">
            <label className="calc-label">Your Age</label>
            <div className="calc-slider-row">
              <input type="range" min={18} max={70} value={age}
                onChange={e => setAge(+e.target.value)} className="calc-slider" />
              <span className="calc-value">{age} yrs</span>
            </div>
          </div>

          <div className="calc-field">
            <label className="calc-label">Investment Horizon</label>
            <div className="calc-slider-row">
              <input type="range" min={1} max={40} step={1} value={horizon}
                onChange={e => setHorizon(+e.target.value)} className="calc-slider" />
              <span className="calc-value">{horizon} yrs</span>
            </div>
          </div>

          <div className="calc-field">
            <label className="calc-label">Monthly SIP Amount</label>
            <div className="calc-input-row">
              <span className="calc-prefix">₹</span>
              <input type="number" value={customSip} min={500} step={500}
                onChange={e => setCustomSip(Math.max(0, +e.target.value))} className="calc-number" />
            </div>
            <p className="calc-sip-hint">Enter the amount you can invest each month</p>
          </div>

          <div className="calc-field">
            <label className="calc-label">Financial Goal</label>
            <select value={goal} onChange={e => setGoal(e.target.value as Goal)} className="calc-select">
              {(Object.keys(GOAL_LABELS) as Goal[]).map(g => (
                <option key={g} value={g}>{GOAL_LABELS[g]}</option>
              ))}
            </select>
          </div>

          <div className="calc-field">
            <label className="calc-label">Risk Profile</label>
            <div className="calc-risk-row">
              {(["conservative", "moderate", "aggressive"] as Risk[]).map(r => (
                <button key={r}
                  className={"calc-risk-btn" + (risk === r ? " calc-risk-active" : "")}
                  onClick={() => handleRiskChange(r)}>
                  {r.charAt(0).toUpperCase() + r.slice(1)}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* ── Results ── */}
        <div className="calc-results">
          <PieChart alloc={editAlloc} />

          <div className="calc-breakdown">
            <div className="calc-breakdown-header">
              <h3 className="calc-section-title">Recommended Allocation</h3>
              <button className="calc-reset-btn"
                onClick={() => setEditAlloc(calcAllocation(age, horizon, risk))}>
                Reset
              </button>
            </div>
            {(Object.keys(editAlloc) as (keyof Allocation)[]).map(key => (
              <div key={key} className="calc-asset-row">
                <div className="calc-asset-bar-wrap">
                  <div className="calc-asset-header">
                    <span className="calc-asset-name" style={{ color: INSTRUMENTS[key].color }}>
                      {INSTRUMENTS[key].label}
                    </span>
                    <div className="calc-alloc-input-wrap">
                      <input
                        type="number" min={0} max={100}
                        value={editAlloc[key]}
                        onChange={e => updateAlloc(key, +e.target.value)}
                        className="calc-alloc-input"
                      />
                      <span className="calc-alloc-pct">%</span>
                    </div>
                  </div>
                  <div className="calc-bar-bg">
                    <div className="calc-bar-fill"
                      style={{ width: `${editAlloc[key]}%`, background: INSTRUMENTS[key].color }} />
                  </div>
                  <div className="calc-asset-monthly">
                    {inr.format(monthlySplit[key])} / month &nbsp;·&nbsp;
                    <span className="calc-asset-instruments">{INSTRUMENTS[key].examples}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="calc-projection">
            <h3 className="calc-section-title">Projected Corpus in {horizon} years</h3>
            <div className="calc-projection-grid">
              <div className="calc-proj-cell">
                <span className="calc-proj-label">Blended CAGR</span>
                <strong className="calc-proj-value pct-up">{(blendedCAGR * 100).toFixed(1)}%</strong>
              </div>
              <div className="calc-proj-cell">
                <span className="calc-proj-label">Invested Amount ({inr.format(monthly)}/mo)</span>
                <strong className="calc-proj-value">{inr.format(Math.round(investedAmount))}</strong>
              </div>
              <div className="calc-proj-cell">
                <span className="calc-proj-label">Growth</span>
                <strong className="calc-proj-value pct-up">{inr.format(Math.round(growth))}</strong>
              </div>
              <div className="calc-proj-cell calc-proj-total">
                <span className="calc-proj-label">Total Estimated Corpus</span>
                <strong className="calc-proj-value gold-karat-price">{inr.format(Math.round(totalCorpus))}</strong>
              </div>
            </div>
            <p className="calc-disclaimer">
              Projections are illustrative. Equity returns assumed 12% CAGR, Debt 7%, Gold 8%, Liquid 5.5%.
              Actual returns will vary. Consult a SEBI-registered financial advisor before investing.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
function SharePortfolioCalculator() {
  const [holdings, setHoldings] = useState<Holding[]>(STOCK_CATALOG);
  const [name, setName] = useState("");
  const [price0, setPrice0] = useState("");
  const [mu, setMu] = useState("");
  const [sigma, setSigma] = useState("");
  const [beta, setBeta] = useState("");
  const [amount, setAmount] = useState("");
  const [corr, setCorr] = useState(35);
  const [days, setDays] = useState(100);
  const [rf, setRf] = useState(6.5);
  const [marketReturn, setMarketReturn] = useState(12);
  const [running, setRunning] = useState(false);
  const [paused, setPaused] = useState(false);
  const [, setStage] = useState(holdings.length > 0 ? 2 : 1);
  const [dayLabel, setDayLabel] = useState("");
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [showSuggestions, setShowSuggestions] = useState(false);

  const suggestions = useMemo(() => {
    if (!name.trim()) return [];
    return STOCK_CATALOG.filter(s => fuzzyMatch(name, s.name)).slice(0, 6);
  }, [name]);

  function selectSuggestion(entry: Holding) {
    setName(entry.name);
    setPrice0(String(entry.price0));
    setMu(String(entry.mu));
    setSigma(String(entry.sigma));
    setBeta(String(entry.beta));
    setShowSuggestions(false);
  }

  const chartRef = useRef<HTMLCanvasElement | null>(null);
  const chartInstance = useRef<Chart | null>(null);
  const sim = useRef({
    units: [] as number[],
    currentPrices: [] as number[],
    portfolioIndex: [] as number[],
    initialTotal: 0,
    day: 0,
    totalDays: 100,
    corr: 0.35,
    rf: 6.5,
    timer: 0,
  });

  useEffect(() => {
    return () => {
      window.clearInterval(sim.current.timer);
      chartInstance.current?.destroy();
    };
  }, []);

  const totalInvested = useMemo(
    () => holdings.reduce((sum, h) => sum + h.amount, 0),
    [holdings]
  );

  const weightedReturn = useMemo(
    () => (totalInvested > 0 ? holdings.reduce((sum, h) => sum + (h.amount / totalInvested) * h.mu, 0) : 0),
    [holdings, totalInvested]
  );

  const summary = useMemo(() => {
    const total = totalInvested;
    let sumWsig2 = 0;
    let sumWsig = 0;
    holdings.forEach((h) => {
      const w = total > 0 ? h.amount / total : 0;
      sumWsig2 += w * w * h.sigma * h.sigma;
      sumWsig += w * h.sigma;
    });
    const variance = (1 - corr / 100) * sumWsig2 + (corr / 100) * sumWsig * sumWsig;
    const portVol = Math.sqrt(Math.max(variance, 0));
    const sharpe = portVol > 0 ? (weightedReturn - rf) / portVol : 0;
    return { portVol, sharpe };
  }, [holdings, totalInvested, corr, rf, weightedReturn]);

  const portfolioBeta = useMemo(
    () => (totalInvested > 0 ? holdings.reduce((sum, h) => sum + (h.amount / totalInvested) * h.beta, 0) : 0),
    [holdings, totalInvested]
  );

  const portfolioAlpha = useMemo(
    () => capmAlpha(weightedReturn, portfolioBeta, rf, marketReturn),
    [weightedReturn, portfolioBeta, rf, marketReturn]
  );

  // Always-live statistical outlook, independent of the animated drill below —
  // this is what stays stable from click to click and answers "what should I
  // expect", as opposed to the single animated path which is one example run.
  const ensemble = useMemo(
    () => runMonteCarlo(holdings, corr, days, 150),
    [holdings, corr, days]
  );

  const tide = ['#2a78d6','#1baf7a','#eda100','#e34948','#4a3aa7','#e87ba4','#eb6834','#008300','#7a5195','#bc5090','#ef5675','#ffa600','#003f5c','#58508d','#ff764a'];
  const portfolioColor = '#8a8880';

  const fmtINR = (n: number) => `₹${Math.round(n).toLocaleString('en-IN')}`;

  const metricCard = (label: string, value: string) => (
    <div className="calc-metric-card">
      <p className="calc-metric-label">{label}</p>
      <p className="calc-metric-value">{value}</p>
    </div>
  );

  const initChart = () => {
    if (!chartRef.current) return;
    chartInstance.current?.destroy();
    const datasets: ChartDataset<'line'>[] = holdings.map((h, i) => ({
      label: h.name,
      data: [100],
      borderColor: tide[i % tide.length],
      backgroundColor: 'transparent',
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.15,
    }));
    datasets.push({
      label: 'Portfolio',
      data: [100],
      borderColor: portfolioColor,
      backgroundColor: 'transparent',
      borderWidth: 3,
      borderDash: [6, 3],
      pointRadius: 0,
      tension: 0.15,
    } as ChartDataset<'line'>);
    chartInstance.current = new Chart(chartRef.current, {
      type: 'line',
      data: {
        labels: [0],
        datasets,
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { title: { display: true, text: 'Trading day' }, grid: { display: false } },
          y: { title: { display: true, text: 'Index (start = 100)' } },
        },
      },
    });
  };

  const pushFrame = (day: number) => {
    const chart = chartInstance.current;
    if (!chart) return;
    chart.data.labels?.push(day);
    const currentPrices = sim.current.currentPrices;
    holdings.forEach((h, i) => {
      const value = 100 * currentPrices[i] / h.price0;
      chart.data.datasets[i].data.push(value);
    });
    const portVal = holdings.reduce((sum, _, i) => sum + sim.current.units[i] * currentPrices[i], 0);
    sim.current.portfolioIndex.push(100 * portVal / sim.current.initialTotal);
    chart.data.datasets[holdings.length].data.push(100 * portVal / sim.current.initialTotal);
    chart.update('none');
  };

  const computeEvaluation = () => {
    const series = sim.current.portfolioIndex;
    if (series.length < 2) {
      setEvaluation(null);
      return;
    }
    const totalReturn = (series[series.length - 1] / series[0] - 1) * 100;
    const rets = [] as number[];
    for (let i = 1; i < series.length; i += 1) {
      rets.push(series[i] / series[i - 1] - 1);
    }
    const mean = rets.reduce((sum, v) => sum + v, 0) / rets.length;
    const variance = rets.reduce((sum, v) => sum + (v - mean) * (v - mean), 0) / rets.length;
    const dailyVol = Math.sqrt(variance);
    const annVol = dailyVol * Math.sqrt(252) * 100;
    const years = series.length / 252;
    const annReturn = years > 0 ? (Math.pow(series[series.length - 1] / series[0], 1 / years) - 1) * 100 : 0;
    const sharpe = annVol > 0 ? (annReturn - rf) / annVol : 0;
    let peak = series[0];
    let maxDD = 0;
    series.forEach((v) => {
      peak = Math.max(peak, v);
      maxDD = Math.min(maxDD, (v - peak) / peak);
    });
    setEvaluation({
      totalReturn,
      annVol,
      sharpe,
      maxDrawdown: maxDD * 100,
    });
  };

  const stepDay = () => {
    const dt = 1 / 252;
    const f = randn();
    const rho = corr / 100;
    const currentPrices = sim.current.currentPrices;
    currentPrices.forEach((prev, i) => {
      const eps = randn();
      const z = Math.sqrt(rho) * f + Math.sqrt(1 - rho) * eps;
      const h = holdings[i];
      const mu = h.mu / 100;
      const sg = h.sigma / 100;
      currentPrices[i] = prev * Math.exp((mu - 0.5 * sg * sg) * dt + sg * Math.sqrt(dt) * z);
    });
    sim.current.day += 1;
    pushFrame(sim.current.day);
    setDayLabel(`Day ${sim.current.day} of ${sim.current.totalDays}`);
    if (sim.current.day >= sim.current.totalDays) {
      finishDrill();
    }
  };

  const startDrill = () => {
    if (holdings.length === 0) return;
    sim.current.corr = corr / 100;
    sim.current.totalDays = days;
    sim.current.rf = rf;
    sim.current.units = holdings.map((h) => h.amount / h.price0);
    sim.current.currentPrices = holdings.map((h) => h.price0);
    sim.current.initialTotal = totalInvested;
    sim.current.day = 0;
    sim.current.portfolioIndex = [100];
    setRunning(true);
    setPaused(false);
    setStage(3);
    setEvaluation(null);
    initChart();
    setDayLabel(`Day 0 of ${days}`);
    sim.current.timer = window.setInterval(stepDay, 70);
  };

  const pauseDrill = () => {
    window.clearInterval(sim.current.timer);
    setPaused(true);
    setRunning(false);
    const currentPrices = sim.current.currentPrices;
    setHoldings((prevHoldings) => prevHoldings.map((h, i) => ({
      ...h,
      amount: Math.round(sim.current.units[i] * currentPrices[i]),
      price0: currentPrices[i],
    })));
    setStage(4);
  };

  const resumeDrill = () => {
    sim.current.units = holdings.map((h) => h.amount / h.price0);
    setPaused(false);
    setRunning(true);
    setStage(3);
    sim.current.timer = window.setInterval(stepDay, 70);
  };

  const finishDrill = () => {
    window.clearInterval(sim.current.timer);
    setRunning(false);
    setPaused(false);
    setStage(5);
    computeEvaluation();
  };

  const resetDrill = () => {
    window.clearInterval(sim.current.timer);
    chartInstance.current?.destroy();
    sim.current = {
      units: [],
      currentPrices: [],
      portfolioIndex: [],
      initialTotal: 0,
      day: 0,
      totalDays: days,
      corr: corr / 100,
      rf,
      timer: 0,
    };
    setRunning(false);
    setPaused(false);
    setDayLabel("");
    setEvaluation(null);
    setStage(totalInvested > 0 ? 2 : 1);
  };

  const addHolding = (event: React.FormEvent) => {
    event.preventDefault();
    if (running && !paused) return;
    const parsedPrice = Number(price0);
    const parsedMu = Number(mu);
    const parsedSigma = Number(sigma);
    const parsedBeta = beta.trim() === "" ? 1 : Number(beta);
    const parsedAmount = Number(amount);
    if (!name.trim() || parsedPrice <= 0 || Number.isNaN(parsedMu) || Number.isNaN(parsedSigma) || parsedSigma < 0 || Number.isNaN(parsedBeta) || parsedAmount <= 0) {
      return;
    }
    setHoldings((prev) => [
      ...prev,
      { name: name.trim(), price0: parsedPrice, mu: parsedMu, sigma: parsedSigma, beta: parsedBeta, amount: parsedAmount },
    ]);
    setName("");
    setPrice0("");
    setMu("");
    setSigma("");
    setBeta("");
    setAmount("");
    setStage(2);
  };

  const removeHolding = (idx: number) => {
    if (running && !paused) return;
    setHoldings((prev) => {
      const next = prev.filter((_, i) => i !== idx);
      if (next.length === 0) setStage(1);
      return next;
    });
  };

  const updateAmount = (idx: number, value: number) => {
    if (running && !paused) return;
    setHoldings((prev) => prev.map((h, i) => i === idx ? { ...h, amount: value } : h));
  };

  const updatePrice = (idx: number, value: number) => {
    if (running && !paused) return;
    setHoldings((prev) => prev.map((h, i) => i === idx ? { ...h, price0: Math.max(0.01, value) } : h));
  };

  const updateMu = (idx: number, value: number) => {
    if (running && !paused) return;
    setHoldings((prev) => prev.map((h, i) => i === idx ? { ...h, mu: value } : h));
  };

  const updateSigma = (idx: number, value: number) => {
    if (running && !paused) return;
    setHoldings((prev) => prev.map((h, i) => i === idx ? { ...h, sigma: Math.max(0, value) } : h));
  };

  const updateBeta = (idx: number, value: number) => {
    if (running && !paused) return;
    setHoldings((prev) => prev.map((h, i) => i === idx ? { ...h, beta: value } : h));
  };

  // Editing weight rescales the holding to that share of the current total
  // invested, and proportionally redistributes the remainder across the rest.
  const updateWeight = (idx: number, rawPct: number) => {
    if (running && !paused) return;
    const total = totalInvested;
    if (total <= 0) return;
    const val = Math.max(0, Math.min(100, rawPct));
    setHoldings((prev) => {
      const amounts = prev.map(h => h.amount);
      const others = prev.map((_, i) => i).filter(i => i !== idx);
      const otherSum = others.reduce((s, i) => s + amounts[i], 0);
      const rest = total * (100 - val) / 100;
      const next = [...amounts];
      next[idx] = total * val / 100;
      if (otherSum > 0) {
        let assigned = 0;
        others.forEach((i, k) => {
          if (k < others.length - 1) {
            const share = (amounts[i] / otherSum) * rest;
            next[i] = Math.max(0, share);
            assigned += next[i];
          } else {
            next[i] = Math.max(0, rest - assigned);
          }
        });
      } else if (others.length > 0) {
        const each = rest / others.length;
        others.forEach((i) => { next[i] = each; });
      }
      return prev.map((h, i) => ({ ...h, amount: Math.round(next[i]) }));
    });
  };

  return (
    <div className="calc-card">
      <div className="calc-header">
        <h2 className="calc-title">Share Portfolio Drill</h2>
        <p className="calc-subtitle">
          Build a market-cap weighted share portfolio and simulate return, risk, and drawdown over a trading horizon.
        </p>
      </div>

      <div className="calc-body portfolio-body">
        <form className="portfolio-input-row" onSubmit={addHolding}>
          <div className="portfolio-suggest-wrap">
            <label htmlFor="pf-name">Share name</label>
            <input
              id="pf-name"
              value={name}
              onChange={(e) => { setName(e.target.value); setShowSuggestions(true); }}
              onFocus={() => setShowSuggestions(true)}
              onBlur={() => setShowSuggestions(false)}
              type="text"
              placeholder="Search e.g. Zomato"
              autoComplete="off"
            />
            {showSuggestions && suggestions.length > 0 && (
              <ul className="portfolio-suggest-list">
                {suggestions.map(s => (
                  <li key={s.name}>
                    <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => selectSuggestion(s)}>
                      <span className="portfolio-suggest-name">{s.name}</span>
                      <span className="portfolio-suggest-meta">₹{s.price0} · {s.mu.toFixed(1)}% exp · {s.sigma.toFixed(1)}% vol · β {s.beta.toFixed(2)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <label htmlFor="pf-price">Price</label>
            <input id="pf-price" value={price0} onChange={(e) => setPrice0(e.target.value)} type="number" min="1" placeholder="500" />
          </div>
          <div>
            <label htmlFor="pf-mu">Exp return %/yr</label>
            <input id="pf-mu" value={mu} onChange={(e) => setMu(e.target.value)} type="number" step="0.5" placeholder="12" />
          </div>
          <div>
            <label htmlFor="pf-sigma">Volatility %/yr</label>
            <input id="pf-sigma" value={sigma} onChange={(e) => setSigma(e.target.value)} type="number" step="0.5" min="0" placeholder="30" />
          </div>
          <div>
            <label htmlFor="pf-beta">Beta (β)</label>
            <input id="pf-beta" value={beta} onChange={(e) => setBeta(e.target.value)} type="number" step="0.05" placeholder="1.00" />
          </div>
          <div>
            <label htmlFor="pf-amount">Amount</label>
            <input id="pf-amount" value={amount} onChange={(e) => setAmount(e.target.value)} type="number" min="0" placeholder="20000" />
          </div>
          <button type="submit" disabled={running && !paused}>+ Add</button>
        </form>

        <div className="portfolio-table-wrap">
          {holdings.length === 0 ? (
            <p className="muted-row">No shares added yet.</p>
          ) : (
            <table className="portfolio-table">
              <thead>
                <tr>
                  <th>Share</th>
                  <th className="numeric">Price</th>
                  <th className="numeric">Exp. return</th>
                  <th className="numeric">Volatility</th>
                  <th className="numeric">Beta (β)</th>
                  <th className="numeric">Alpha (α)</th>
                  <th className="numeric">Amount</th>
                  <th className="numeric">Weight</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {holdings.map((h, idx) => {
                  const weight = totalInvested > 0 ? (h.amount / totalInvested) * 100 : 0;
                  const alpha = capmAlpha(h.mu, h.beta, rf, marketReturn);
                  return (
                    <tr key={`${h.name}-${idx}`}>
                      <td>{h.name}</td>
                      <td className="numeric">
                        <input
                          type="number"
                          value={h.price0}
                          min={0.01}
                          step="0.01"
                          onChange={(e) => updatePrice(idx, Number(e.target.value))}
                          disabled={running && !paused}
                          className="portfolio-amt-input"
                          aria-label={`${h.name} price`}
                        />
                      </td>
                      <td className="numeric">
                        <input
                          type="number"
                          value={h.mu}
                          step="0.1"
                          onChange={(e) => updateMu(idx, Number(e.target.value))}
                          disabled={running && !paused}
                          className="portfolio-amt-input"
                          aria-label={`${h.name} expected return percent per year`}
                        />
                      </td>
                      <td className="numeric">
                        <input
                          type="number"
                          value={h.sigma}
                          min={0}
                          step="0.1"
                          onChange={(e) => updateSigma(idx, Number(e.target.value))}
                          disabled={running && !paused}
                          className="portfolio-amt-input"
                          aria-label={`${h.name} volatility percent per year`}
                        />
                      </td>
                      <td className="numeric">
                        <input
                          type="number"
                          value={h.beta}
                          step="0.05"
                          onChange={(e) => updateBeta(idx, Number(e.target.value))}
                          disabled={running && !paused}
                          className="portfolio-amt-input"
                          aria-label={`${h.name} beta`}
                        />
                      </td>
                      <td className={"numeric" + (alpha >= 0 ? " pct-up" : " pct-down")}>
                        {alpha >= 0 ? "+" : ""}{alpha.toFixed(2)}%
                      </td>
                      <td className="numeric">
                        <input
                          type="number"
                          value={Math.round(h.amount)}
                          min={0}
                          onChange={(e) => updateAmount(idx, Number(e.target.value))}
                          disabled={running && !paused}
                          className="portfolio-amt-input"
                          aria-label={`${h.name} amount invested in rupees`}
                        />
                      </td>
                      <td className="numeric">
                        <input
                          type="number"
                          value={Number(weight.toFixed(1))}
                          min={0}
                          max={100}
                          step="0.1"
                          onChange={(e) => updateWeight(idx, Number(e.target.value))}
                          disabled={running && !paused}
                          className="portfolio-amt-input"
                          aria-label={`${h.name} weight percent of portfolio`}
                        />
                      </td>
                      <td className="numeric">
                        <button type="button" onClick={() => removeHolding(idx)} disabled={running && !paused} className="portfolio-remove-btn" aria-label={`Remove ${h.name} from portfolio`}>
                          ✕
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        <div className="summary-grid portfolio-summary-grid">
          {metricCard('Total invested', fmtINR(totalInvested))}
          {metricCard('Weighted exp. return', `${weightedReturn.toFixed(2)}%`)}
          {metricCard('Estimated portfolio risk', `${summary.portVol.toFixed(2)}%`)}
          {metricCard('Estimated Sharpe ratio', summary.sharpe.toFixed(2))}
          {metricCard('Portfolio beta (β)', portfolioBeta.toFixed(2))}
          {metricCard('Portfolio alpha (α, CAPM)', `${portfolioAlpha >= 0 ? '+' : ''}${portfolioAlpha.toFixed(2)}%`)}
        </div>

        {ensemble && (
          <div className="portfolio-outlook">
            <div className="portfolio-outlook-header">
              <h3 className="calc-section-title">Expected Outcome</h3>
              <p className="portfolio-outlook-note">
                Average of {ensemble.paths} simulated {days}-day scenarios at your current settings — this updates as you edit
                the portfolio but stays statistically stable from click to click, unlike a single simulated path.
              </p>
            </div>
            <div className="summary-grid portfolio-summary-grid">
              {metricCard('Expected return (mean)', `${ensemble.mean >= 0 ? '+' : ''}${ensemble.mean.toFixed(2)}%`)}
              {metricCard('Median return', `${ensemble.median >= 0 ? '+' : ''}${ensemble.median.toFixed(2)}%`)}
              {metricCard('Typical range (5th–95th pct.)', `${ensemble.p5.toFixed(1)}% to ${ensemble.p95.toFixed(1)}%`)}
              {metricCard('Chance of a loss', `${ensemble.probLoss.toFixed(0)}%`)}
            </div>
          </div>
        )}

        <div className="portfolio-controls">
          <div>
            <label htmlFor="pf-corr">Average correlation <span>{corr}%</span></label>
            <input id="pf-corr" type="range" min={0} max={90} step={5} value={corr} onChange={(e) => setCorr(Number(e.target.value))} />
          </div>
          <div>
            <label htmlFor="pf-days">Drill length (days) <span>{days}</span></label>
            <input id="pf-days" type="range" min={20} max={250} step={10} value={days} onChange={(e) => setDays(Number(e.target.value))} />
          </div>
          <div>
            <label htmlFor="pf-rf">Risk-free rate %/yr</label>
            <input id="pf-rf" type="number" step="0.5" value={rf} onChange={(e) => setRf(Number(e.target.value))} />
          </div>
          <div>
            <label htmlFor="pf-market">Market return assumption %/yr</label>
            <input id="pf-market" type="number" step="0.5" value={marketReturn} onChange={(e) => setMarketReturn(Number(e.target.value))} />
          </div>
        </div>

        <div className="portfolio-actions">
          <button type="button" onClick={startDrill} disabled={running}>▶ Run drill</button>
          <button type="button" onClick={pauseDrill} disabled={!running || paused}>⏸ Pause and rebalance</button>
          <button type="button" onClick={resumeDrill} disabled={!paused} style={{ display: paused ? 'inline-flex' : 'none' }}>▶ Apply and resume</button>
          <button type="button" onClick={resetDrill}>↻ Reset</button>
          <span className="day-counter" aria-live="polite">{dayLabel}</span>
        </div>

        <div className="portfolio-chart-wrap">
          <canvas ref={chartRef} role="img" aria-label="Line chart of simulated share prices and portfolio value" />
        </div>

        <div className="portfolio-legend">
          {holdings.map((h, i) => (
            <span key={`${h.name}-${i}`} className="portfolio-legend-item">
              <span className="legend-line" style={{ background: tide[i % tide.length] }} />
              {h.name}
            </span>
          ))}
          <span className="portfolio-legend-item">
            <span className="legend-line" style={{ background: portfolioColor, backgroundImage: 'repeating-linear-gradient(90deg, #8a8880 0 4px, transparent 4px 7px)' }} />
            Portfolio
          </span>
        </div>

        {evaluation && (
          <div className="portfolio-outlook">
            <div className="portfolio-outlook-header">
              <h3 className="calc-section-title">This Run's Result</h3>
              <p className="portfolio-outlook-note">
                One simulated path out of many possible outcomes — running the drill again will give a different result
                by design. Compare it against the Expected Outcome above for the statistically robust estimate.
              </p>
            </div>
            <div className="portfolio-eval-grid">
              {metricCard('Total return', `${evaluation.totalReturn >= 0 ? '+' : ''}${evaluation.totalReturn.toFixed(2)}%`)}
              {metricCard('Realized volatility', `${evaluation.annVol.toFixed(2)}%`)}
              {metricCard('Realized Sharpe', evaluation.sharpe.toFixed(2))}
              {metricCard('Max drawdown', `${evaluation.maxDrawdown.toFixed(2)}%`)}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function Calculators() {
  const [activeTab, setActiveTab] = useState<'allocation' | 'portfolio'>('allocation');

  return (
    <div className="analytics-page">
      <div className="analytics-body">
        <div className="calc-tabs">
          <button className={"calc-tab" + (activeTab === 'allocation' ? ' calc-tab-active' : '')} onClick={() => setActiveTab('allocation')}>
            Asset Allocation
          </button>
          <button className={"calc-tab" + (activeTab === 'portfolio' ? ' calc-tab-active' : '')} onClick={() => setActiveTab('portfolio')}>
            Share Portfolio Drill
          </button>
        </div>
        {activeTab === 'allocation' ? <AssetAllocationCalculator /> : <SharePortfolioCalculator />}
      </div>
    </div>
  );
}
