import { useEffect, useState } from "react";
import { api, type MutualFund, type GoldRate, type FDRate, type IPOItem, type GovernmentBond } from "../api/client";

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });

// ── Mutual Funds ─────────────────────────────────────────────────────────────

function FundCard({ fund }: { fund: MutualFund }) {
  return (
    <div className="fund-card">
      <div className="fund-name">{fund.name}</div>
      <div className="fund-nav-row">
        <span className="fund-nav">NAV ₹{fund.nav.toFixed(4)}</span>
        <span className={`fund-change ${fund.day_change >= 0 ? "pct-up" : "pct-down"}`}>
          {fund.day_change >= 0 ? "+" : ""}{fund.day_change.toFixed(2)}% today
        </span>
      </div>
      {fund.year_return !== null && (
        <div className={`fund-return ${fund.year_return >= 0 ? "pct-up" : "pct-down"}`}>
          1Y return: {fund.year_return >= 0 ? "+" : ""}{fund.year_return.toFixed(2)}%
        </div>
      )}
      <div className="fund-date">NAV as of {fund.nav_date}</div>
    </div>
  );
}

function MutualFundsPanel() {
  const [groups, setGroups] = useState<Record<string, MutualFund[]>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.mutualFunds()
      .then(setGroups)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const categories = Object.keys(groups);

  return (
    <div className="panel analytics-panel">
      <p className="eyebrow">AMFI · mfapi.in · daily NAV</p>
      <h2>Top Mutual Funds by Category</h2>
      {loading && <p className="muted-row">Loading NAV data…</p>}
      {!loading && categories.length === 0 && <p className="muted-row">NAV data unavailable</p>}
      {categories.map((cat) => (
        <div key={cat} className="fund-category">
          <h3 className="fund-category-title">{cat}</h3>
          <div className="fund-grid">
            {groups[cat].map((f) => <FundCard key={f.code} fund={f} />)}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Gold Rates ───────────────────────────────────────────────────────────────

function GoldPanel() {
  const [gold, setGold] = useState<GoldRate | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.goldRate()
      .then(setGold)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const changeBadge = (chg: number) => (
    <span className={`gold-change-badge ${chg >= 0 ? "pct-up" : "pct-down"}`}>
      {chg >= 0 ? "▲" : "▼"} {inr.format(Math.abs(chg))} today
    </span>
  );

  return (
    <div className="panel analytics-panel gold-panel">
      <p className="eyebrow">goodreturns.in · IBJA rates · updated daily</p>
      <h2>Gold Rate Today</h2>
      {loading && <p className="muted-row">Fetching gold price…</p>}
      {!loading && !gold && <p className="muted-row">Gold data unavailable</p>}
      {gold && (
        <div className="gold-body">
          <div className="gold-karat-grid">
            <div className="gold-karat-card">
              <div className="gold-karat-label">24K (99.9% pure)</div>
              <div className="gold-karat-price">{inr.format(gold.k24_per_10g_inr)}</div>
              <div className="gold-karat-sub">per 10 grams</div>
              <div className="gold-karat-gram">{inr.format(gold.k24_per_gram_inr)} / gram</div>
              {changeBadge(gold.k24_day_change_inr)}
            </div>
            <div className="gold-karat-card">
              <div className="gold-karat-label">22K (91.6% pure)</div>
              <div className="gold-karat-price">{inr.format(gold.k22_per_10g_inr)}</div>
              <div className="gold-karat-sub">per 10 grams</div>
              <div className="gold-karat-gram">{inr.format(gold.k22_per_gram_inr)} / gram</div>
              {changeBadge(gold.k22_day_change_inr)}
            </div>
          </div>
          {gold.usd_per_oz !== null && (
            <div className="gold-meta-grid">
              <div className="gold-meta-cell">
                <span className="gold-meta-label">COMEX (USD/oz)</span>
                <strong>${gold.usd_per_oz.toFixed(2)}</strong>
              </div>
              {gold.usd_inr_rate !== null && (
                <div className="gold-meta-cell">
                  <span className="gold-meta-label">USD / INR</span>
                  <strong>₹{gold.usd_inr_rate.toFixed(2)}</strong>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── FD Rates ─────────────────────────────────────────────────────────────────

function FDRatesPanel() {
  const [rates, setRates] = useState<FDRate[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.fdRates()
      .then(setRates)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="panel analytics-panel">
      <p className="eyebrow">Top 5 by highest general-public rate</p>
      <h2>Fixed Deposit Rates</h2>
      {loading && <p className="muted-row">Loading FD rates…</p>}
      {!loading && rates.length === 0 && <p className="muted-row">FD data unavailable</p>}
      {rates.length > 0 && (
        <table className="fd-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Bank</th>
              <th>Type</th>
              <th className="numeric">Max Rate</th>
              <th>Best Tenure</th>
            </tr>
          </thead>
          <tbody>
            {rates.map((r, i) => (
              <tr key={r.bank}>
                <td className="fd-rank">{i + 1}</td>
                <td className="fd-bank">{r.bank}</td>
                <td><span className="fd-type-badge">{r.type}</span></td>
                <td className="numeric">
                  <strong className="fd-rate pct-up">{r.max_rate.toFixed(2)}%</strong>
                  <span className="fd-note"> p.a.</span>
                </td>
                <td className="fd-tenure">{r.tenure}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="fd-disclaimer">
        Rates are indicative for general public. Senior citizens get 0.25–0.50% extra.
        Verify with the bank before investing.
      </p>
    </div>
  );
}

function GovBondsPanel() {
  const [bonds, setBonds] = useState<GovernmentBond[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.govBonds()
      .then(setBonds)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="panel analytics-panel" style={{ marginTop: 18 }}>
      <p className="eyebrow">Top 5 government securities · indicative prices</p>
      <h2>Government Bonds</h2>
      {loading && <p className="muted-row">Loading bonds data…</p>}
      {!loading && bonds.length === 0 && <p className="muted-row">Government bond data unavailable</p>}
      {bonds.length > 0 && (
        <table className="bond-table">
          <thead>
            <tr>
              <th>Bond</th>
              <th>Maturity</th>
              <th className="numeric">Coupon</th>
              <th className="numeric">Yield</th>
              <th className="numeric">Price</th>
            </tr>
          </thead>
          <tbody>
            {bonds.map((bond, i) => (
              <tr key={`${bond.name}-${i}`}>
                <td>{bond.name}</td>
                <td>{bond.maturity}</td>
                <td className="numeric">{bond.coupon}</td>
                <td className="numeric pct-up">{bond.yield_pct.toFixed(2)}%</td>
                <td className="numeric">{bond.price.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="fd-disclaimer">
        Bond prices are indicative and may vary with auction updates. Confirm yields with the RBI or trading platform.
      </p>
    </div>
  );
}

// ── IPOs ─────────────────────────────────────────────────────────────────────

function statusClass(status: string): string {
  const s = status.toLowerCase();
  if (s === "open") return "ipo-status-open";
  if (s === "upcoming") return "ipo-status-upcoming";
  return "ipo-status-closed";
}

function IPOsPanel() {
  const [ipos, setIpos] = useState<IPOItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.ipos()
      .then(setIpos)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="panel analytics-panel" style={{ marginTop: 18 }}>
      <p className="eyebrow">Moneycontrol · next 6 months · updated daily</p>
      <h2>Upcoming IPOs</h2>
      {loading && <p className="muted-row">Fetching IPO data…</p>}
      {!loading && ipos.length === 0 && (
        <p className="muted-row">No upcoming IPOs found — NSE data may be unavailable outside market hours</p>
      )}
      {ipos.length > 0 && (
        <table className="ipo-table">
          <thead>
            <tr>
              <th>Company</th>
              <th>Status</th>
              <th>Open Date</th>
              <th>Close Date</th>
              <th>Price Band</th>
              <th>Issue Size</th>
              <th>Lot Size</th>
            </tr>
          </thead>
          <tbody>
            {ipos.map((ipo, i) => (
              <tr key={i}>
                <td className="ipo-company">{ipo.company}</td>
                <td>
                  <span className={`ipo-status-badge ${statusClass(ipo.status)}`}>
                    {ipo.status}
                  </span>
                </td>
                <td>{ipo.open_date}</td>
                <td>{ipo.close_date}</td>
                <td>{ipo.price_band || "—"}</td>
                <td>{ipo.issue_size || "—"}</td>
                <td>{ipo.lot_size || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function Analytics() {
  return (
    <div className="analytics-page">
      <div className="analytics-topbar">
        <h1 className="analytics-title">Investment Alternatives</h1>
      </div>

      <div className="analytics-body">
        <div className="analytics-top-row">
          <GoldPanel />
          <FDRatesPanel />
        </div>
        <MutualFundsPanel />
        <GovBondsPanel />
        <IPOsPanel />
      </div>
    </div>
  );
}
