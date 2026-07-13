import { useEffect, useState, useRef } from "react";
import { api, type WatchlistItem, type CommodityItem, type CurrencyItem } from "../api/client";
import MoversPanel from "../components/MoversPanel";
import MarketOverviewChart from "../components/MarketOverviewChart";
import { CAP_BUCKETS } from "../marketBuckets";

function formatTime(value: string | null): string {
  if (!value) return "Waiting for first import";
  return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(new Date(value));
}

const COMMODITY_ICONS: Record<string, string> = { Gold: "🥇", Silver: "🥈", "Crude Oil": "🛢" };

function CommodityPanel({ items }: { items: CommodityItem[] }) {
  return (
    <div className="market-overview-card">
      <p className="eyebrow">COMEX · ICE futures</p>
      <h3 className="market-overview-title">Commodity Index</h3>
      <div className="market-ticker-list">
        {items.length === 0
          ? ["Gold", "Silver", "Crude Oil"].map((n) => (
              <div key={n} className="market-ticker-row market-ticker-skeleton">
                <span className="market-ticker-icon">{COMMODITY_ICONS[n]}</span>
                <div className="market-ticker-info">
                  <span className="market-ticker-name">{n}</span>
                  <span className="market-ticker-unit skeleton-bar" />
                </div>
                <div className="market-ticker-right">
                  <span className="skeleton-bar" style={{ width: 70 }} />
                  <span className="skeleton-bar" style={{ width: 48 }} />
                </div>
              </div>
            ))
          : items.map((c) => (
              <div key={c.name} className="market-ticker-row">
                <span className="market-ticker-icon">{COMMODITY_ICONS[c.name] ?? "📦"}</span>
                <div className="market-ticker-info">
                  <span className="market-ticker-name">{c.name}</span>
                  <span className="market-ticker-unit">{c.unit}</span>
                </div>
                <div className="market-ticker-right">
                  <span className="market-ticker-price">${c.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                  <span className={`market-ticker-chg ${c.change_pct >= 0 ? "pct-up" : "pct-down"}`}>
                    {c.change_pct >= 0 ? "▲" : "▼"} {Math.abs(c.change_pct).toFixed(2)}%
                  </span>
                </div>
              </div>
            ))}
      </div>
    </div>
  );
}

const CURRENCY_FLAGS: Record<string, string> = { USD: "🇺🇸", EUR: "🇪🇺", GBP: "🇬🇧", JPY: "🇯🇵" };
const CURRENCY_NAMES: Record<string, string> = { USD: "US Dollar", EUR: "Euro", GBP: "British Pound", JPY: "Japanese Yen" };

function CurrencyPanel({ items }: { items: CurrencyItem[] }) {
  const inr4 = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
  const placeholders = ["USD", "EUR", "GBP", "JPY"];
  return (
    <div className="market-overview-card">
      <p className="eyebrow">vs Indian Rupee</p>
      <h3 className="market-overview-title">Currency Rates</h3>
      <div className="market-ticker-list">
        {items.length === 0
          ? placeholders.map((code) => (
              <div key={code} className="market-ticker-row market-ticker-skeleton">
                <span className="market-ticker-icon">{CURRENCY_FLAGS[code]}</span>
                <div className="market-ticker-info">
                  <span className="market-ticker-name">{code}</span>
                  <span className="market-ticker-unit">{CURRENCY_NAMES[code]}</span>
                </div>
                <div className="market-ticker-right">
                  <span className="skeleton-bar" style={{ width: 70 }} />
                  <span className="skeleton-bar" style={{ width: 48 }} />
                </div>
              </div>
            ))
          : items.map((c) => (
              <div key={c.currency} className="market-ticker-row">
                <span className="market-ticker-icon">{CURRENCY_FLAGS[c.currency] ?? "💱"}</span>
                <div className="market-ticker-info">
                  <span className="market-ticker-name">{c.currency}</span>
                  <span className="market-ticker-unit">{c.name}</span>
                </div>
                <div className="market-ticker-right">
                  <span className="market-ticker-price">₹{inr4.format(c.rate_inr)}</span>
                  <span className={`market-ticker-chg ${c.change_pct >= 0 ? "pct-up" : "pct-down"}`}>
                    {c.change_pct >= 0 ? "▲" : "▼"} {Math.abs(c.change_pct).toFixed(2)}%
                  </span>
                </div>
              </div>
            ))}
      </div>
    </div>
  );
}

export default function LiveMarketPage() {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [commodities, setCommodities] = useState<CommodityItem[]>([]);
  const [currencies, setCurrencies] = useState<CurrencyItem[]>([]);
  const refreshedRef = useRef<string | null>(null);

  useEffect(() => {
    const load = () => api.watchlist().then(setWatchlist).catch(console.error);
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const load = () => {
      api.commodities().then(setCommodities).catch(console.error);
      api.currencies().then(setCurrencies).catch(console.error);
    };
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const check = async () => {
      try {
        const res = await api.analyticsStatus();
        const newVal = res.refreshed_at ?? null;
        if (refreshedRef.current === null) {
          refreshedRef.current = newVal;
        } else if (newVal && newVal !== refreshedRef.current) {
          refreshedRef.current = newVal;
          api.watchlist().then(setWatchlist).catch(console.error);
          api.commodities().then(setCommodities).catch(console.error);
          api.currencies().then(setCurrencies).catch(console.error);
        }
      } catch {
        // ignore
      }
    };
    check();
    const id = setInterval(check, 15_000);
    return () => clearInterval(id);
  }, []);

  const pricedWatchlist = watchlist.filter((w) => w.pct_change !== null);
  const gainers = pricedWatchlist.filter((w) => Number(w.pct_change) >= 0).length;
  const losers = pricedWatchlist.length - gainers;
  const bucketCounts = CAP_BUCKETS.map(({ bucket, tickers }) => ({
    bucket,
    count: watchlist.filter((item) => tickers.includes(item.ticker)).length || tickers.length,
  }));
  const lastUpdated = watchlist.map((w) => w.fetched_at).filter(Boolean).sort().at(-1) ?? null;

  return (
    <div className="dashboard">
      <header className="page-header">
        <p className="eyebrow">NSE large-cap monitor</p>
        <h1>Live Market</h1>
      </header>

      <section className="metric-strip" aria-label="Watchlist summary">
        <div>
          <span className="metric-label">Tracked shares</span>
          <strong>{watchlist.length || 15}</strong>
        </div>
        {bucketCounts.map((item) => (
          <div key={item.bucket}>
            <span className="metric-label">{item.bucket}</span>
            <strong>{item.count}</strong>
          </div>
        ))}
        <div>
          <span className="metric-label">Advancing</span>
          <strong className="pct-up">{gainers}</strong>
        </div>
        <div>
          <span className="metric-label">Declining</span>
          <strong className="pct-down">{losers}</strong>
        </div>
        <div>
          <span className="metric-label">Last import (IST)</span>
          <strong>{formatTime(lastUpdated)}</strong>
        </div>
      </section>

      <MarketOverviewChart />

      <div className="market-overview-row">
        <CommodityPanel items={commodities} />
        <CurrencyPanel items={currencies} />
      </div>

      <MoversPanel />
    </div>
  );
}
