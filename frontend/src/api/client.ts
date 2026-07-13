// VITE_API_BASE_URL (e.g. "https://backend-xyz.a.run.app") is required in
// any deployment where frontend and backend don't share a hostname+port —
// which is the normal case on Cloud Run/ECS/Azure Container Apps, where
// each service gets its own separate URL. Falls back to the old
// same-host-port-8000 assumption for local dev (`npm run dev` +
// `uvicorn ... --port 8000` on localhost, or docker-compose on one host).
const API_ROOT = import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname || "127.0.0.1"}:8000`;
export const API_BASE = `${API_ROOT}/api`;
const WS_BASE = `${API_ROOT.replace(/^http/, "ws")}/ws`;

export interface WatchlistItem {
  ticker: string;
  sector: string | null;
  price: number | null;
  pct_change: number | null;
  volume: number | null;
  fetched_at: string | null;
  alpha: number | null;
  beta: number | null;
}

export interface SectorPerf {
  sector: string;
  avg_pct_change: number;
  count: number;
  momentum_score: number;
  trend: "up" | "down" | "neutral";
}

export interface TrendingItem {
  ticker: string;
  pct_change: number;
  volume: number;
}

export interface MoverItem {
  ticker: string;
  symbol: string;
  name: string;
  price: number;
  pct_change: number;
  volume: number;
  sector: string | null;
  source?: string;
}

export interface MoversData {
  gainers: MoverItem[];
  losers: MoverItem[];
  source?: string;
}

export interface SentimentItem {
  ticker: string;
  avg_sentiment: number;
  sample_size: number;
}

export interface AlertItem {
  id: number;
  ticker: string | null;
  category: string;
  severity: string;
  message: string;
  reason: string | null;
  used_ai: boolean;
  created_at: string | null;
}

export interface NewsItem {
  id: number;
  ticker: string | null;
  source: string;
  title: string;
  url: string;
  sentiment: number | null;
  published_at: string | null;
  fetched_at: string | null;
}

export interface RecommendationItem {
  ticker: string;
  symbol: string;
  name: string;
  price: number | null;
  pct_change: number | null;
  sector: string | null;
  sentiment?: number;
  score?: number;
  reason: string;
  source_url?: string;
}

export interface RecommendationsData {
  buy: RecommendationItem[];
  sell: RecommendationItem[];
  source?: string;
}

export interface RecommendationPick {
  ticker: string;
  label: "Buy" | "Hold" | "Sell";
  confidence: number;
  score: number;
  price: number | null;
  pct_change: number | null;
  sector: string | null;
  sentiment: number;
  reason: string;
  ai_reason: string | null;
}

export interface RecommendationPicksData {
  picks: RecommendationPick[];
  computed_at: string | null;
}

export interface AgentStatusItem {
  name: string;
  label: string;
  active: boolean;
  state: "active" | "idle" | "not_active";
  last_run: string | null;
  // Real output counters — null/[] only for Sector Rotation, which has no
  // backing table of its own (see routes_agents.py).
  output_24h: number | null;
  history: number[];
  caption: string | null;
}

export interface IndexItem {
  name: string;
  last: number | null;
  change: number | null;
  pct_change: number | null;
}

export interface CorporateActionItem {
  id: number;
  symbol: string;
  company_name: string | null;
  action_type: string;
  ex_date: string | null;
  record_date: string | null;
  announcement_date: string | null;
  value: string | null;
  source_url: string | null;
  ai_reason: string | null;
}

export interface RegulatoryAnnouncementItem {
  id: number;
  symbol: string;
  company_name: string | null;
  category: string;
  subject: string;
  attachment_url: string | null;
  announcement_date: string | null;
  source_url: string | null;
  ai_reason: string | null;
}

export interface RiskScore {
  risk_score: number;
  risk_label: "Low" | "Moderate" | "High";
  india_vix: number | null;
  watchlist_volatility: number | null;
  advances: number | null;
  declines: number | null;
  breadth_ratio: number | null;
  volume_spike_count: number;
  computed_at: string;
}

export interface SocialPlatformSentiment {
  connected: boolean;
  score: number | null;
  sample_size: number;
}

export interface SocialSentimentData {
  overall_score: number | null;
  overall_label: "Bullish" | "Bearish" | "Neutral";
  platforms: {
    stocktwits: SocialPlatformSentiment;
    youtube: SocialPlatformSentiment;
  };
}

export interface MarketBriefing {
  headline: string | null;
  summary: string | null;
  anomalies: string[];
  agents_triggered: string[];
  ai_generated: boolean;
  computed_at: string | null;
  orchestrator_active: boolean;
  orchestrator_last_run: string | null;
}

export interface IndexSeriesPoint {
  t: string;
  c: number;
}

export interface EconomicEventItem {
  id: number;
  series_id: string;
  title: string;
  value: number | null;
  detail: string | null;
  release_date: string | null;
  importance: "high" | "medium" | "low";
  ai_reason: string | null;
  fetched_at: string;
}

export interface FiiDiiFlowPoint {
  trade_date: string;
  fii_net_cr: number | null;
  dii_net_cr: number | null;
  fii_buy_cr: number | null;
  fii_sell_cr: number | null;
  dii_buy_cr: number | null;
  dii_sell_cr: number | null;
}

export interface InstitutionalMentionItem {
  id: number;
  ticker: string;
  category: "FII" | "DII" | "FDI";
  title: string;
  url: string;
  sentiment: number | null;
  published_at: string | null;
  fetched_at: string;
}

export interface FiiDiiData {
  summary: string | null;
  summary_ai_generated: boolean;
  summary_date: string | null;
  flows: FiiDiiFlowPoint[];
  mentions: InstitutionalMentionItem[];
}

export interface YouTubeSentimentSummaryData {
  summary: string | null;
  ai_generated: boolean;
  computed_at: string | null;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`Request failed: ${path}`);
  return res.json();
}

export interface MutualFund {
  name: string;
  code: string;
  category: string;
  nav: number;
  nav_date: string;
  day_change: number;
  year_return: number | null;
}

export interface GoldRate {
  k24_per_gram_inr: number;
  k22_per_gram_inr: number;
  k24_per_10g_inr: number;
  k22_per_10g_inr: number;
  k24_day_change_inr: number;
  k22_day_change_inr: number;
  day_change_pct: number;
  usd_per_oz: number | null;
  usd_inr_rate: number | null;
  fetched_at: string;
}

export interface FDRate {
  bank: string;
  max_rate: number;
  tenure: string;
  type: string;
  note: string;
}

export interface IPOItem {
  company: string;
  open_date: string;
  close_date: string;
  price_band: string;
  issue_size: string;
  lot_size: string;
  status: string;
}

export interface GovernmentBond {
  name: string;
  maturity: string;
  coupon: string;
  yield_pct: number;
  price: number;
}

export interface CommodityItem {
  name: string;
  symbol: string;
  price: number;
  unit: string;
  change_pct: number;
}

export interface CurrencyItem {
  currency: string;
  name: string;
  rate_inr: number;
  change_pct: number;
}

export interface YouTubeInsightItem {
  id: number;
  channel: string;
  video_title: string;
  video_url: string;
  published_at: string | null;
  language: string;
  ticker: string;
  recommendation: string | null;
  topics: string[];
  tone: string;
  sentiment: number;
}

export const api = {
  watchlist: () => getJson<WatchlistItem[]>("/watchlist"),
  sectors: () => getJson<SectorPerf[]>("/sectors"),
  trending: () => getJson<TrendingItem[]>("/trending"),
  movers: () => getJson<MoversData>("/movers"),
  marketMovers: () => getJson<MoversData>("/market-movers"),
  sentimentHeatmap: () => getJson<SentimentItem[]>("/sentiment-heatmap"),
  alerts: () => getJson<AlertItem[]>("/alerts"),
  // Higher limit than the default 25: with 5 source feeds now (3 Indian +
  // 2 international), a same-run batch of Indian stories alone can fill a
  // small window and starve the international column entirely. 100 is the
  // backend's max allowed.
  news: () => getJson<NewsItem[]>("/news?limit=100"),
  recommendations: () => getJson<RecommendationPicksData>("/recommendations"),
  marketRecommendations: () => getJson<RecommendationsData>("/market-recommendations"),
  agentsStatus: () => getJson<AgentStatusItem[]>("/agents/status"),
  socialSentiment: () => getJson<SocialSentimentData>("/social-sentiment"),
  briefing: () => getJson<MarketBriefing>("/briefing"),
  indices: () => getJson<IndexItem[]>("/indices"),
  corporateActions: (limit = 50) => getJson<CorporateActionItem[]>(`/corporate-actions?limit=${limit}`),
  regulatoryAnnouncements: (limit = 50) => getJson<RegulatoryAnnouncementItem[]>(`/regulatory-announcements?limit=${limit}`),
  riskScore: () => getJson<RiskScore | null>("/risk-score"),
  economicEvents: (limit = 20) => getJson<EconomicEventItem[]>(`/economic-events?limit=${limit}`),
  fiiDii: () => getJson<FiiDiiData>("/fii-dii"),
  indexSeries: (index: string, range: string) =>
    getJson<IndexSeriesPoint[]>(`/index-series?index=${encodeURIComponent(index)}&range=${range}`),
  mutualFunds:  () => getJson<Record<string, MutualFund[]>>("/analytics/mutual-funds"),
  goldRate:     () => getJson<GoldRate | null>("/analytics/gold"),
  fdRates:      () => getJson<FDRate[]>("/analytics/fd-rates"),
  ipos:         () => getJson<IPOItem[]>("/analytics/ipos"),
  govBonds:     () => getJson<GovernmentBond[]>("/analytics/gov-bonds"),
  commodities:  () => getJson<CommodityItem[]>("/analytics/commodities"),
  currencies:   () => getJson<CurrencyItem[]>("/analytics/currencies"),
  priceSeries:  (ticker: string) => getJson<number[]>(`/price-series/${encodeURIComponent(ticker)}`),
  youtubeInsights: () => getJson<YouTubeInsightItem[]>("/youtube-insights"),
  youtubeSentimentSummary: () => getJson<YouTubeSentimentSummaryData>("/youtube-sentiment-summary"),
  analyticsStatus: () => getJson<{ refreshed_at: string | null }>("/analytics/status"),
  refreshAnalytics: async () => {
    const res = await fetch(`${API_BASE}/analytics/refresh`, { method: "POST" });
    if (!res.ok) throw new Error("Refresh failed");
    return res.json();
  },
};

export function connectAlertsSocket(onAlert: (alert: AlertItem) => void): () => void {
  const ws = new WebSocket(`${WS_BASE}/alerts`);
  ws.onmessage = (event) => {
    try {
      onAlert(JSON.parse(event.data));
    } catch {
      // ignore malformed payloads
    }
  };
  return () => ws.close();
}
