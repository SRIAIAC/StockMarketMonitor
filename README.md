# Stock Market Monitor

A full-stack web application for tracking Indian NSE stocks in real time, with 10 background AI agents (live market, news, social, corporate actions, regulatory filings, economic calendar, sector rotation, risk, and confidence-scored recommendations), a dark-themed sidebar dashboard, investment alternatives, and financial calculators.

For a system-level view (architecture diagrams, deployment topology, the
AI fallback ladder, key design tradeoffs) see **[ARCHITECTURE.md](ARCHITECTURE.md)**.
This file is the detailed step-by-step implementation walkthrough.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Project Structure](#2-project-structure)
3. [Backend — Step by Step](#3-backend--step-by-step)
   - [Step 1 — App Entry Point](#step-1--app-entry-point-mainpy)
   - [Step 2 — Database Models](#step-2--database-models-modelspy)
   - [Step 3 — Configuration](#step-3--configuration-configpy)
   - [Step 4 — Data Collection Agents](#step-4--data-collection-agents)
   - [Step 5 — AI Signal Analysis](#step-5--ai-signal-analysis)
   - [Step 6 — Scheduler](#step-6--scheduler-schedulerpy)
   - [Step 7 — REST API Routes](#step-7--rest-api-routes)
   - [Step 8 — WebSocket Live Feed](#step-8--websocket-live-feed)
   - [Step 9 — Analytics Data](#step-9--analytics-data-analytics_datapy)
   - [Step 10 — Web Data Cache](#step-10--web-data-cache-web_datapy)
3. [Agent Roster (10 agents)](#agent-roster-10-agents)
4. [Frontend — Step by Step](#4-frontend--step-by-step)
   - [Step 11 — App Shell, Sidebar & Topbar](#step-11--app-shell-sidebar--topbar-apptsx-sidebartsx-topbartsx)
   - [Step 12 — API Client](#step-12--api-client-apiclientts)
   - [Step 13 — Overview Page (Dashboard)](#step-13--overview-page-dashboardtsx)
   - [Step 13b — Secondary Sidebar Pages](#step-13b--secondary-sidebar-pages)
   - [Step 14 — Investment Alternatives Page](#step-14--investment-alternatives-page-analyticstsx)
   - [Step 15 — Calculators Page](#step-15--calculators-page-calculatorstsx)
   - [Step 16 — Components](#step-16--components)
5. [Data Flow](#5-data-flow)
6. [Tools & Libraries Used](#6-tools--libraries-used)
7. [LLMs Used — Where and Why](#7-llms-used--where-and-why)
8. [Setup & Running](#8-setup--running)
9. [Environment Variables](#9-environment-variables)
10. [Deploying to GCP](#10-deploying-to-gcp)
11. [CI/CD](#11-cicd)

---

## 1. Architecture Overview

```
┌───────────────────────────────────────────────────────────┐
│                     React Frontend                        │
│  Sidebar (14 nav items) + Topbar (indices, status, theme) │
│  Overview · Live Market · News · Social · Corp. Actions · │
│  SEBI Filings · Econ Calendar · Sector Rotation · Risk ·  │
│  Recommendations · Watchlist · Alerts · Analytics ·       │
│  Calculators              (Vite + TypeScript, dark-first) │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP REST + WebSocket
┌──────────────────────────▼──────────────────────────────┐
│                    FastAPI Backend                       │
│   /api/* routes  (10+ route modules)   /ws/alerts        │
├───────────────────────────────────────────────────────────┤
│                       APScheduler                         │
│  Market/News/Social/Econ/CorpAction/Regulatory/Risk/      │
│    Recommendation/Alert: every 30 minutes                 │
│  YouTube: every 3 hours · Orchestrator: every 15 minutes  │
│  + daily cron sweep at 9:15 AM & 3:45 PM IST               │
├───────────────────────────────────────────────────────────┤
│                     10 Agents (BaseAgent)                 │
│  Market · News · Social · CorporateAction ·                │
│  RegulatoryAnnouncement · EconCalendar · Risk ·             │
│  Recommendation · YouTube · Alert                          │
│  (Insider Trading deliberately excluded — no free NSE/BSE  │
│   insider-disclosure API exists; see agents/README.md)     │
├───────────────────────────────────────────────────────────┤
│           OrchestratorAgent (meta-agent, 11th)             │
│  Reads every agent above → analysis/anomaly_rules.py       │
│  decides (rule-based) which agents to re-trigger off-cycle │
│  → Claude narrates the result into a Market Briefing       │
│  Not one of the 10 roster cards — see agent roster below   │
├───────────────────────────────────────────────────────────┤
│                  External Data Sources                    │
│  Moneycontrol · yfinance · Google News RSS · StockTwits    │
│  NSE India (allIndices, sector indices, corporate actions, │
│  corporate announcements, chart-databyindex, movers) ·     │
│  goodreturns.in · mfapi.in · FRED · YouTube RSS + captions  │
├───────────────────────────────────────────────────────────┤
│              AI Layer (Anthropic Claude)                  │
│  Haiku — fast triage + recommendation reasons              │
│  Sonnet — deep market analysis + chat                      │
│  (no key configured → rule-based fallback runs everywhere) │
├───────────────────────────────────────────────────────────┤
│                     SQLite Database                       │
│  Price · NewsItem · SocialPost · YouTubeInsight ·          │
│  EconomicEvent · CorporateAction · RegulatoryAnnouncement · │
│  RiskSnapshot · Recommendation · Alert · MarketBriefing     │
└───────────────────────────────────────────────────────────┘
```

**Design principle carried through every layer:** routes never call an
external API directly — an agent fetches, normalizes, and stores first;
routes only read what's already in the database (or a short-lived
in-memory cache). This keeps requests fast even when a data source is
slow, rate-limited, or down, and it's why every new agent added in this
round follows the same `BaseAgent.run()` → `run_safe()` → scheduled job
pattern as the original five.

---

## 2. Project Structure

```
StockMarketMonitor/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── config.py            # Environment settings (Pydantic)
│   │   ├── models.py            # SQLAlchemy database models (10 tables)
│   │   ├── db.py                # DB engine, session, init + column migration
│   │   ├── scheduler.py         # APScheduler job definitions (10 agents)
│   │   ├── agents/
│   │   │   ├── base.py                     # BaseAgent, run_safe(), in-process liveness tracking
│   │   │   ├── market_agent.py             # Live NSE price fetcher
│   │   │   ├── news_agent.py               # Google News RSS parser
│   │   │   ├── social_agent.py             # StockTwits data collector
│   │   │   ├── econ_calendar_agent.py      # RBI/macro events + importance tagging
│   │   │   ├── youtube_agent.py            # YouTube finance-channel transcript ingester
│   │   │   ├── corporate_action_agent.py   # NEW — dividends/splits/bonuses/buybacks (whole market)
│   │   │   ├── regulatory_announcement_agent.py  # NEW — NSE regulatory/compliance disclosures
│   │   │   ├── risk_agent.py               # NEW — composite volatility/liquidity risk score
│   │   │   ├── recommendation_agent.py     # NEW — Buy/Hold/Sell + confidence score
│   │   │   ├── orchestrator_agent.py       # NEW — meta-agent: anomaly-triggered re-runs + LLM briefing
│   │   │   ├── fii_dii_agent.py             # NEW — real whole-market FII/DII flow + news-derived per-stock mentions
│   │   │   ├── alert_agent.py              # Rule-based + AI alerts
│   │   │   └── README.md                   # Per-agent data source / design notes
│   │   ├── analysis/
│   │   │   ├── rules.py           # Deterministic alert thresholds
│   │   │   ├── anomaly_rules.py   # NEW — cross-agent anomaly detection + agent-trigger mapping
│   │   │   ├── claude_client.py   # Claude API wrapper — Claude → Ollama → rule-based 3-tier fallback (§7)
│   │   │   ├── ollama_client.py   # NEW — local Ollama chat completion, tier 2 of the fallback ladder
│   │   │   ├── sentiment.py       # VADER sentiment scoring
│   │   │   └── youtube_analysis.py # Company/recommendation/topic/tone extraction
│   │   └── api/
│   │       ├── routes_dashboard.py   # /watchlist, /movers, /news, /recommendations, /youtube-insights ...
│   │       ├── routes_alerts.py      # /alerts (today-only, IST)
│   │       ├── routes_market.py      # /market-movers, /sectors (+momentum), /indices data, /index-series
│   │       ├── routes_agents.py      # NEW — /agents/status, /indices, /social-sentiment, /briefing,
│   │       │                         #       /corporate-actions, /regulatory-announcements,
│   │       │                         #       /risk-score, /economic-events
│   │       ├── nse_client.py         # NEW — shared NSE cookie-warm session helper
│   │       ├── routes_analytics.py   # /analytics/* delegator
│   │       ├── analytics_data.py     # MF, gold, FD, IPO scrapers
│   │       ├── web_data.py           # Real-time in-memory cache
│   │       ├── ws.py                 # WebSocket /ws/alerts
│   │       └── routes_chat.py        # Conversational AI chat
│   ├── .env                     # API keys & watchlist
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── index.html                # Pre-paint theme script (avoids flash of wrong theme)
│   ├── src/
│   │   ├── App.tsx               # Router + Sidebar/Topbar shell
│   │   ├── main.tsx              # React 19 bootstrap
│   │   ├── App.css               # Global + page + shell styles
│   │   ├── index.css             # Theme tokens (dark-first + light override + chrome tokens)
│   │   ├── theme.ts               # NEW — dark/light toggle hook (localStorage-backed)
│   │   ├── marketStatus.ts        # NEW — real NSE session open/closed calculation
│   │   ├── marketBuckets.ts       # Cap-bucket classification helpers
│   │   ├── api/
│   │   │   └── client.ts         # Typed fetch client + interfaces (10 new endpoints)
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx           # Overview — agent-status row + grid of live panels
│   │   │   ├── LiveMarketPage.tsx      # NEW — chart, commodities/currencies, movers
│   │   │   ├── NewsPage.tsx            # NEW — full News Intelligence
│   │   │   ├── SocialPage.tsx          # NEW — sentiment gauge + heatmap + YouTube
│   │   │   ├── CorporateActionsPage.tsx # NEW
│   │   │   ├── SebiFilingsPage.tsx      # NEW — labeled honestly as NSE regulatory feed
│   │   │   ├── EconomicCalendarPage.tsx # NEW
│   │   │   ├── SectorRotationPage.tsx   # NEW
│   │   │   ├── RiskMonitorPage.tsx      # NEW
│   │   │   ├── RecommendationsPage.tsx  # NEW — agent picks + web-scraped market signals
│   │   │   ├── WatchlistPage.tsx        # NEW
│   │   │   ├── AlertsPage.tsx           # NEW
│   │   │   ├── AgentsStatusPage.tsx     # NEW — full agent roster + run detail table
│   │   │   ├── Analytics.tsx     # Investment Alternatives
│   │   │   └── Calculators.tsx   # Asset Allocation + Share Portfolio Drill
│   │   └── components/
│   │       ├── Sidebar.tsx             # NEW — 14-item nav + live AI-agents-status mini panel
│   │       ├── TopBar.tsx              # NEW — brand, indices, market status, theme toggle
│   │       ├── Icon.tsx                # NEW — hand-rolled inline-SVG icon set
│   │       ├── MarketBriefingPanel.tsx # NEW — orchestrator's LLM briefing + anomalies + re-triggered agents
│   │       ├── AgentStatusRow.tsx      # NEW — 10 agent-status cards with sparklines
│   │       ├── MarketOverviewChart.tsx # NEW — chart.js index chart, 1D-1Y range toggle
│   │       ├── SocialSentimentGauge.tsx # NEW — hand-rolled SVG semicircle gauge
│   │       ├── AIRecommendationCard.tsx # NEW — ranked Buy/Hold/Sell picks
│   │       ├── RiskMonitor.tsx          # NEW — hand-rolled SVG radial risk gauge
│   │       ├── CorporateActionsPanel.tsx      # NEW
│   │       ├── RegulatoryAnnouncementsPanel.tsx # NEW
│   │       ├── EconomicCalendarPanel.tsx      # NEW
│   │       ├── FiiDiiPanel.tsx          # NEW — real flow chart + news-derived per-stock mentions + AI daily summary
│   │       ├── TickerStrip.tsx          # NEW — bottom-pinned scrolling gainers/losers
│   │       ├── AlertFeed.tsx    # parameterized: Market Alerts / Social Media Alerts
│   │       ├── MoversPanel.tsx
│   │       ├── BuySellPanel.tsx # web-scraped, whole-market signals (secondary source)
│   │       ├── NewsPanel.tsx    # compact (Overview) or split Indian/International (full page)
│   │       ├── SectorPerformance.tsx  # momentum bar + trend arrow table
│   │       ├── SentimentHeatmap.tsx
│   │       ├── TrendingStocks.tsx
│   │       ├── VolumePanel.tsx
│   │       ├── ShareWiseCharts.tsx
│   │       ├── YouTubeSentiment.tsx   # YouTube analyst sentiment panel
│   │       ├── RefreshButton.tsx      # now lives in TopBar
│   │       └── ChatBot.tsx
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
├── EXPERIMENTS.md               # Running change/test log (newest entries first)
└── docker-compose.yml
```

---

## 3. Backend — Step by Step

### Step 1 — App Entry Point (`main.py`)

**What it does:** Creates the FastAPI application, initialises the SQLite database (including a small defensive column-migration step), starts the background scheduler, and registers all API routers.

**Key code flow:**
```python
app = FastAPI(title="Stock Market Monitor")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins)

@app.on_event("startup")
async def startup():
    init_db()          # creates all tables if missing, adds missing columns to existing ones
    start_scheduler()  # kicks off APScheduler
    trigger_immediate_refresh()  # runs every agent once in the background, don't wait for the first interval

# Routers registered:
app.include_router(routes_dashboard.router)  # /api/watchlist, /movers, /news, /recommendations ...
app.include_router(routes_alerts.router)     # /api/alerts
app.include_router(routes_analytics.router)  # /api/analytics/*
app.include_router(routes_market.router)     # /api/market-movers, /sectors, /index-series ...
app.include_router(routes_agents.router)     # /api/agents/status, /indices, /social-sentiment ...
app.include_router(routes_chat.router)       # /api/chat
app.include_router(ws.router)                # /ws/alerts
```

**Tools used:** FastAPI, Uvicorn, SQLAlchemy, APScheduler

---

### Step 2 — Database Models (`models.py`)

**What it does:** Defines the SQLite schema using SQLAlchemy ORM. Each agent writes to its own table; routes read from them (never live-computing against an external API on request).

| Model | Key Columns | Written by |
|-------|-------------|------------|
| `Price` | ticker, sector, price, prev_close, pct_change, volume, avg_volume, fetched_at | MarketAgent |
| `NewsItem` | ticker, source, title, url, sentiment, published_at, fetched_at | NewsAgent |
| `SocialPost` | ticker, source, title, url, score, sentiment, fetched_at | SocialAgent |
| `EconomicEvent` | series_id, title, value, release_date, **importance**, fetched_at | EconCalendarAgent |
| `YouTubeInsight` | channel, video_id, video_title, video_url, published_at, language, ticker, recommendation, topics, tone, sentiment, fetched_at | YouTubeAgent |
| `CorporateAction` *(new)* | symbol, company_name, action_type, ex_date, record_date, announcement_date, value, raw_subject, source_url, fetched_at | CorporateActionAgent |
| `RegulatoryAnnouncement` *(new)* | symbol, company_name, category, subject, attachment_url, announcement_date, source_url, fetched_at | RegulatoryAnnouncementAgent |
| `RiskSnapshot` *(new)* | risk_score, risk_label, india_vix, watchlist_volatility, advances, declines, breadth_ratio, volume_spike_count, computed_at | RiskAgent |
| `Recommendation` *(new)* | ticker, label, confidence, score, price, pct_change, sector, sentiment, reason, ai_reason, computed_at | RecommendationAgent (full-replace per run) |
| `Alert` | ticker, category, severity, message, source_used_ai, created_at | AlertAgent |
| `MarketBriefing` | headline, summary, anomalies (JSON), agents_triggered (JSON), ai_generated, computed_at | OrchestratorAgent (append-only) |
| `FiiDiiFlow` *(new)* | trade_date (unique), fii_buy/sell/net_cr, dii_buy/sell/net_cr, fetched_at | FiiDiiAgent — real NSE data, one row/trading day |
| `InstitutionalMention` *(new)* | ticker, category (FII/DII/FDI), title, url, sentiment, published_at | FiiDiiAgent — news-derived, not a confirmed transaction |
| `FiiDiiSummary` *(new)* | trade_date (unique), summary, ai_generated, computed_at | FiiDiiAgent — one AI summary/trading day |
| `YouTubeSentimentSummary` *(new)* | summary, ai_generated, computed_at | YouTubeAgent — one AI roll-up/3h run, not per video |

A `YouTubeInsight` row with `ticker IS NULL` is a "processed, no company
mentions found" marker — it stops the agent from re-fetching that video's
transcript on every cycle, and is filtered out of `/api/youtube-insights`.

`RegulatoryAnnouncement` is deliberately **not** modeled as "SEBI filings"
internally — see [Agent Roster](#agent-roster-10-agents) below for why.

**Tools used:** SQLAlchemy, SQLite

---

### Step 3 — Configuration (`config.py`)

**What it does:** Reads environment variables via Pydantic Settings. All sensitive values (API keys, watchlist) live in `.env`.

```python
class Settings(BaseSettings):
    watchlist: list[str]        # 15 NSE tickers (e.g. RELIANCE.NS)
    anthropic_api_key: str      # Claude API
    newsapi_key: str            # NewsAPI.org
    fred_api_key: str           # Economic data
    database_url: str           # SQLite path
    allowed_origins: str        # CORS allowlist — includes 5173-5175/5190 dev-port fallbacks
    price_poll_minutes: int = 15
```

**Tools used:** Pydantic Settings, python-dotenv

---

### Step 4 — Data Collection Agents

All agents inherit from `BaseAgent` (`agents/base.py`), which provides a
`run_safe()` wrapper that catches and logs exceptions without crashing the
scheduler, and tracks each agent's last-run time and success/failure
in-process — this is what powers the real (not hardcoded) `/api/agents/status`
liveness check.

See the full per-agent table (data source, table written, notable design
decisions) in [`backend/app/agents/README.md`](backend/app/agents/README.md).
Summary:

#### 4a — MarketAgent (`market_agent.py`)

**What it does:** Fetches live NSE stock prices every 30 minutes.

- **Primary source:** Moneycontrol's internal price API (`httpx` GET with browser headers)
- **Fallback:** `yfinance` (Yahoo Finance) if Moneycontrol blocks
- Stores one `Price` row per ticker with: price, % change, volume, 52-week high/low, sector

**Tools used:** httpx, yfinance, SQLAlchemy

---

#### 4b — NewsAgent (`news_agent.py`)

**What it does:** Parses Google News RSS feeds for each watchlist ticker plus general Indian market news.

- Builds RSS URLs: `https://news.google.com/rss/search?q={ticker}+NSE+stock&hl=en-IN`
- Extracts: title, source, URL, publication time
- Scores each headline sentiment (positive / negative / neutral)
- Deduplicates by URL before storing `NewsItem` records

**Tools used:** feedparser, SQLAlchemy, sentiment.py

---

#### 4c — SocialAgent (`social_agent.py`)

**What it does:** Pulls recent posts per watchlist ticker from StockTwits' public stream API — no API key required.

- One request per ticker to `api.stocktwits.com/api/2/streams/symbol/{ticker}.json`
  (`.NS` → `.NSE` suffix swap; StockTwits' own convention)
- Each post already arrives tagged to its exact ticker — no fuzzy text
  matching needed (unlike NewsAgent, which has to infer a ticker from the
  headline)
- Scores sentiment on post text with VADER
- Stores `SocialPost` records with like-count as score and VADER sentiment
- Uses `urllib.request`, not `httpx` — StockTwits sits behind Cloudflare,
  which blocks `httpx`'s TLS fingerprint (403) but lets `urllib` through

**Tools used:** urllib (stdlib), SQLAlchemy

> The product's Social Sentiment gauge (`/api/social-sentiment`) blends
> StockTwits + YouTube only — X/Twitter and Reddit have no free/keyless API
> integrated, so they're omitted from the panel entirely rather than shown
> as a permanent "Not connected" row or fabricated.

---

#### 4d — YouTubeAgent (`youtube_agent.py`)

**What it does:** Polls 6 Indian finance YouTube channels for new videos and runs rule-based sentiment/company extraction over their transcripts — no YouTube Data API key, no audio download, no Whisper/ffmpeg.

- **Channels** (pinned by channel ID, not `@handle` — handles get squatted/redirected, e.g. `@CNBCTV18Live` resolves to an unrelated channel): CA Rachana Ranade, SOIC, Groww, Zerodha Varsity, ET Now, CNBC-TV18
- **Discovery:** each channel's public RSS feed (`youtube.com/feeds/videos.xml?channel_id=...`), fetched via `httpx` with a real browser User-Agent and a 3-retry backoff — YouTube's feed endpoint is flaky under repeated polling and rejects `feedparser`'s own bare (near-empty User-Agent) request for some channels
- **Transcript:** YouTube's own captions via `youtube-transcript-api`, English preferred, Hindi as fallback (several channels are Hindi/Hinglish)
- **Extraction** (`analysis/youtube_analysis.py`, all rule-based since no `ANTHROPIC_API_KEY` is required):
  - Company mentions — a ~60-ticker gazetteer of spoken/written name variants (e.g. "Bajaj Auto" vs "Bajaj Finance" vs "Bajaj Finserv")
  - Recommendation — BUY/SELL/HOLD keyword counting across the transcript
  - Topics — a keyword taxonomy (Earnings, IPO, Buyback, RBI Policy, FII/DII Flows, Technical Analysis, Mutual Funds, Global Markets)
  - Tone — VADER sentiment, bucketed Bullish/Bearish/Neutral
- **Rate-limit handling:** paces transcript fetches 3s apart, caps at 2 new videos/channel/run, and aborts the whole run immediately if YouTube's transcript API returns `RequestBlocked` — retrying more videos while already blocked only prolongs the block
- Videos with no company mentions get a `ticker=NULL` marker row so they aren't re-fetched every cycle

**Tools used:** httpx, feedparser, youtube-transcript-api, VADER, SQLAlchemy

---

#### 4e — EconCalendarAgent (`econ_calendar_agent.py`)

**What it does:** Scrapes Trading Economics' public India calendar page
(`tradingeconomics.com/india/calendar`) for real India macro releases — CPI/
WPI, GDP, IIP, PMI (mfg/services/composite), RBI rate decisions, trade
balance, forex reserves, M3 money supply, and whatever else India releases
the page is currently tracking (no static series allowlist). Each event is
tagged with an `importance` (high/medium) used by the Economic Calendar
panel's colored-dot indicator, plus an AI one-liner (`ai_reason`) on the top
10 items explaining why the release matters.

- **No API key required** — this was previously FRED-based (US-only data, a
  structural mismatch for an India-first app) and was fully rewritten to
  scrape real India data instead; no `FRED_API_KEY` setting exists anymore
- Upserts by `(series_id, release_date)` — a row initially stored with only
  a forecast gets `value`/`detail` updated in place once the real print
  releases, rather than creating a duplicate row
- Runs on a 3-hour interval (not 30 minutes) — it's a page scrape against a
  third-party site, and macro releases don't happen more often than that

**Tools used:** httpx, BeautifulSoup4, lxml, SQLAlchemy, claude_client.py

---

#### 4f — CorporateActionAgent (`corporate_action_agent.py`) — *new*

**What it does:** Whole-market (not just the watchlist) dividends, bonuses, splits, rights issues, buybacks, and AGMs, from NSE's own public corporate-actions feed.

- `GET nseindia.com/api/corporates-corporateActions?index=equities` via the shared `nse_client.nse_get()` session helper
- Classifies `action_type` from NSE's free-text `subject` field by keyword match
- Bounded to a rolling ~30-days-back / 60-days-forward window by `ex_date` so the table doesn't grow unbounded
- Deduped on `(symbol, ex_date, raw_subject)`

**Tools used:** httpx (via `nse_client`), SQLAlchemy

---

#### 4g — RegulatoryAnnouncementAgent (`regulatory_announcement_agent.py`) — *new*

**What it does:** Whole-market NSE regulatory/compliance disclosures (board meetings, credit ratings, investor presentations, LODR compliance, etc.).

> **Naming honesty:** this is **not** a SEBI EDIFAR filings feed — there is
> no free public API for SEBI's own filing system, the same gap that led to
> the old `InsiderAgent` being removed entirely rather than left as a
> permanent no-op (see §4 note below and `agents/README.md`). This is NSE's
> own disclosure feed, the closest free/keyless real substitute. The
> frontend labels it "SEBI Filings" as the sidebar item name (matching the
> product spec) but its panel copy says "NSE Regulatory Announcements ·
> not SEBI EDIFAR" so the distinction is never hidden from the user.

- `GET nseindia.com/api/corporate-announcements?index=equities`
- **Explicitly filters out** any item matching insider-trading/SAST keywords ("Insider Trading", "SAST", "Regulation 29", "Regulation 31", "Regulation 7(2)", "Substantial Acquisition") before storage — never surfaced, even though NSE's raw feed technically carries some adjacent categories
- Deduped on `attachment_url` where present, else a composite key

**Tools used:** httpx (via `nse_client`), SQLAlchemy

---

#### 4h — RiskAgent (`risk_agent.py`) — *new*

**What it does:** Computes a single 0–100 market risk score with a Low/Moderate/High label, entirely from data already collected elsewhere — no new external dependency.

```python
risk_score = clamp(0, 100,
    0.40 * norm(india_vix) +
    0.25 * norm(market_breadth) +      # skew toward declines raises risk
    0.20 * norm(watchlist_volatility) +
    0.15 * norm(volume_spike_ratio)
)
```

- India VIX and whole-market advances/declines come from the same NSE
  `allIndices` payload `routes_market.py` already calls for sector breadth
- Watchlist volatility (cross-sectional stdev of latest `pct_change`) and
  volume-spike count come from the app's own `Price` history
  (`rules.VOLUME_SPIKE_RATIO`, reused rather than a new constant)
- Weights/normalization ranges are a starting point, flagged in the module
  docstring as needing recalibration once real score history accrues — same
  spirit as `rules.py`'s already-tuned threshold constants

**Tools used:** httpx (via `nse_client`), SQLAlchemy, statistics (stdlib)

---

#### 4i — RecommendationAgent (`recommendation_agent.py`) — *new*

**What it does:** Buy/Hold/Sell recommendation + confidence % per watchlist ticker (kept watchlist-scoped — richest per-ticker price/sentiment data — rather than widened to the whole market).

```python
raw_score = (pct_change / 5.0) * 0.5       # price momentum
          + sentiment * 0.3                 # news + social, last 24h
          + min(vol_ratio - 1, 1.5) * 0.2    # volume vs average
          + sector_momentum_term * 0.15      # from routes_market's extended /api/sectors
score = raw_score * (1 - risk_penalty)       # dampened by the latest RiskSnapshot

label = "Buy" if score >= 0.5 else "Sell" if score <= -0.5 else "Hold"
confidence = 50 + min(abs(score), 1.0) * 49  # never claims false 100% certainty
```

- AI one-line reasons (`claude_client.recommend_reason()`) are only
  requested for the top-5 ranked picks actually displayed, to bound Claude
  spend — same "never raise, rule-based fallback" convention as the
  existing triage function
- Full-replaces the `Recommendation` table each run (no history needed for
  this panel, unlike `RiskSnapshot`)
- `/api/recommendations` is now a pure DB read of this agent's latest run,
  not a live per-request computation

**Tools used:** SQLAlchemy, claude_client.py

---

#### 4j — OrchestratorAgent (`orchestrator_agent.py`) — *new, meta-agent*

**What it does:** Reads every other agent's latest output and does two
things — decides (rule-based) whether specific agents should re-run
off-cycle, and asks Claude to narrate the current cross-agent state into a
short market briefing. Not one of the 10 agent-roster cards — it's an
orchestrator *over* those 10, not an 11th data source.

```python
anomalies = [
    detect_price_anomaly(...),      # single ticker moved >5% → re-run News, Social, Alert
    detect_risk_spike(...),         # RiskSnapshot jumped >=15pts → re-run Recommendation, Alert
    detect_sentiment_cliff(...),    # market-wide sentiment < -0.4 → re-run Social, Alert
    detect_sector_shock(...),       # sector momentum >=85 or <=15 → re-run Recommendation
    detect_alert_burst(...),        # >=3 warning/critical alerts in 15 min → re-run Recommendation, Risk
]
triggered = merge_triggered_agents(anomalies)   # union + dedupe
for name in triggered:
    AGENT_CLASSES[name]().run_safe()             # only these — never a full run_all_agents() sweep

headline, summary = claude_client.generate_briefing(context, has_anomalies=bool(anomalies))
```

**Design note (deliberate, same split as AlertAgent):** the *decision* of
which agents to re-trigger is entirely rule-based (`analysis/anomaly_rules.py`)
— never left to the LLM. Claude's only role is narrating already-decided
facts into prose, exactly why `rules.py` decides alert severity before
`claude_client.py` is ever called. This keeps the consequential action
(spending extra scrape/API budget on an off-cycle run) fast, free,
deterministic, and testable.

- Runs on its own **15-minute interval**, independent of the other agents'
  30-minute cadence, so it can react to anomalies *between* full sweeps —
  plus once more at the tail of `run_all_agents()`
- `claude_client.generate_briefing()` uses Haiku by default, escalates to
  Sonnet only when an anomaly was actually detected this cycle (same
  Haiku→Sonnet gating as `triage_and_explain`)
- No API key configured → falls back to a deterministic templated
  headline/summary built from the same structured facts, never a blank panel
- Writes one `MarketBriefing` row per run (append-only); `GET /api/briefing`
  reads the latest

**Tools used:** SQLAlchemy, claude_client.py, anomaly_rules.py

---

#### 4k — AlertAgent (`alert_agent.py`)

**What it does:** The core intelligence layer. Reads the last 60 minutes of rows from `Price`, `NewsItem`, and `SocialPost`, applies rule thresholds, and calls Claude AI only for signals flagged `needs_ai`.

**How it works:**
```
For each row fetched in the last 60 minutes:
  1. Pass to rules.py → returns Signal(severity, needs_ai) or None
  2. Dedupe: skip if an Alert already exists for this ticker+category+day
  3. If needs_ai == False: store Alert with the raw rule-generated message
  4. If needs_ai == True:
       call claude_client.triage_and_explain()
       → Haiku triage, escalated to Sonnet if flagged high-impact
       → falls back to the raw rule message if no ANTHROPIC_API_KEY is set
  5. Store Alert (severity: info / warning / critical)
  6. Broadcast to WebSocket /ws/alerts
```

**Tools used:** SQLAlchemy, claude_client.py, rules.py

> **Removed, stays removed:** an `InsiderAgent` previously queried SEC EDGAR
> (Form 4 filings) for the NSE tickers in `settings.tickers`. EDGAR only
> covers US SEC filers, so Indian NSE-listed companies never appeared there
> regardless of uptime, and there's no equivalent free public API for
> NSE/BSE insider-trading disclosures — the agent, its table, and the
> `insider` alert category were removed entirely rather than left running
> as a permanent no-op. This is a deliberate, standing product decision:
> **no Insider Trading agent, route, or panel** exists anywhere in this
> codebase, including the sidebar nav.

---

### Step 5 — AI Signal Analysis

#### `rules.py` — Deterministic Thresholds

Rule-based filters that run before any AI call to avoid unnecessary API costs:

| Signal | Threshold | Severity |
|--------|-----------|----------|
| Price move | ≥ 3% intraday | warning |
| Price move + volume spike | ≥ 3% intraday and volume ≥ 2× average | critical → needs_ai |
| News sentiment crash | VADER sentiment ≤ −0.5 | warning → needs_ai |
| StockTwits spike | score (likes) ≥ 1 | info |
| StockTwits high spike | score (likes) ≥ 2 | info → needs_ai |

`VOLUME_SPIKE_RATIO` (2.0×) is also reused by `RiskAgent` for its
volume-spike-count term, rather than defining a second constant.

#### `claude_client.py` — Claude API Wrapper

**What it does:** A cost-aware, two-tier wrapper around the Anthropic Python SDK.

```python
def triage_and_explain(ticker, category, reason) -> tuple[str, bool]:
    """Every needs_ai alert signal. Haiku first; Sonnet only if Haiku
    itself flags HIGH_IMPACT: yes. Falls back to the raw rule reason with
    no API key configured."""

def recommend_reason(ticker, label, rule_reason) -> str | None:
    """One-line gloss on a RecommendationAgent pick — only called for the
    top-5 displayed picks. Returns None (never raises) on any failure;
    callers fall back to the deterministic rule_reason."""
```

**In-memory cache:** identical prompts (hashed) within the process lifetime return the cached explanation, avoiding duplicate charges for repeated/near-identical signals.

**LLMs used:**
- `claude-haiku-4-5-20251001` — every `needs_ai` alert signal, and every top-5 recommendation reason
- `claude-sonnet-4-6` — only the alert subset Haiku itself flags `HIGH_IMPACT: yes`, plus ChatBot

---

### Step 6 — Scheduler (`scheduler.py`)

**What it does:** Uses APScheduler to run most agents on a 30-minute
interval; YouTube/EconCalendar/FiiDii on a slower 3-hour interval (page
scrapes / once-daily-changing data don't need to be polled every 30
minutes); the Orchestrator on its own faster 15-minute interval; plus two
daily cron jobs timed to Indian market open and close.

```python
scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

# Every 30 minutes
scheduler.add_job(_market_agent.run_safe,          "interval", minutes=30, id="market_30m")
scheduler.add_job(_news_agent.run_safe,             "interval", minutes=30, id="news_30m")
scheduler.add_job(_social_agent.run_safe,           "interval", minutes=30, id="social_30m")
scheduler.add_job(_corp_action_agent.run_safe,      "interval", minutes=30, id="corp_action_30m")
scheduler.add_job(_regulatory_agent.run_safe,       "interval", minutes=30, id="regulatory_30m")
scheduler.add_job(_risk_agent.run_safe,             "interval", minutes=30, id="risk_30m")
scheduler.add_job(_recommendation_agent.run_safe,   "interval", minutes=30, id="recommendation_30m")
scheduler.add_job(_alert_agent.run_safe,            "interval", minutes=30, id="alert_30m")
scheduler.add_job(_web_refresh,                     "interval", minutes=30, id="web_30m")
scheduler.add_job(_analytics_refresh,               "interval", minutes=30, id="analytics_30m")

# Every 3 hours — YouTube channels post far less often; EconCalendar is a
# page scrape (be a good citizen); FII/DII flow only changes once/trading-day
scheduler.add_job(_youtube_agent.run_safe,  "interval", minutes=180, id="youtube_180m")
scheduler.add_job(_econ_agent.run_safe,     "interval", minutes=180, id="econ_180m")
scheduler.add_job(_fii_dii_agent.run_safe,  "interval", minutes=180, id="fii_dii_180m")

# Every 15 minutes — faster than the other agents, so it can react to
# anomalies between full sweeps
scheduler.add_job(_orchestrator_agent.run_safe, "interval", minutes=15, id="orchestrator_15m")

# Daily IST cron — market open / close sweeps (run_all_agents, all 10 + orchestrator, in sequence)
scheduler.add_job(..., "cron", hour=9,  minute=15, timezone="Asia/Kolkata")
scheduler.add_job(..., "cron", hour=15, minute=45, timezone="Asia/Kolkata")
```

`run_all_agents()`'s sequential order matters at the tail end: Risk and
Recommendation both read other agents' freshly-written rows (prices,
sentiment, sector data), so they run after Market/News/Social/EconCalendar
and just before Recommendation, which also reads the Risk snapshot.

> **Note (found live, not by inspection alone):** `/api/agents/status`'s
> staleness check (`routes_agents.py`) originally used one flat
> `stale_after_minutes=90` for every agent — correct for the 30-minute
> agents, but it wrongly marked `econ_calendar` `not_active` for the second
> half of every 3-hour cycle. `econ_calendar` now gets a 200-minute
> staleness window (`stale_after = 200 if key == "econ_calendar" else 90`)
> to match its real cadence. See `EXPERIMENTS.md` (2026-07-13) for how this
> was found.

**Tools used:** APScheduler, pytz / zoneinfo

---

### Step 7 — REST API Routes

#### `routes_dashboard.py`

| Endpoint | Returns | Source |
|----------|---------|--------|
| `GET /api/watchlist` | Latest price per ticker, plus per-ticker `alpha`/`beta` | Price table |
| `GET /api/trending` | Top movers by abs % | Price table |
| `GET /api/movers` | Top 5 gainers + losers | Price or web_data |
| `GET /api/sentiment-heatmap` | Ticker → avg sentiment | NewsItem table |
| `GET /api/news` | Recent articles (Indian + International feeds) | NewsItem table |
| `GET /api/recommendations` | `{picks: [...], computed_at}` — Buy/Hold/Sell + confidence | Recommendation table (agent-computed) |
| `GET /api/youtube-insights` | Recent YouTube company mentions | YouTubeInsight table |

#### `routes_market.py`

| Endpoint | Returns | Source |
|----------|---------|--------|
| `GET /api/market-movers` | Whole-market top 5 gainers + losers | NSE live API / NIFTY 50 fallback |
| `GET /api/sectors` | Avg % change, momentum_score (0-100), trend (up/down/neutral), company count per sector | NSE sectoral indices, blended today + 30-day change |
| `GET /api/market-recommendations` | Web-scraped buy/sell picks (separate from the agent-scored pipeline) | Google News RSS + DuckDuckGo + yfinance enrichment |
| `GET /api/price-series/{ticker}` | Recent close prices for one watchlist ticker | Price table / yfinance fallback |
| `GET /api/index-series` | `[{t, c}]` for a headline index over a 1D–1Y range | NSE live intraday (1D) / yfinance history (longer ranges) — empty list if unavailable, never fabricated |

#### `routes_agents.py` — *new*

| Endpoint | Returns | Source |
|----------|---------|--------|
| `GET /api/agents/status` | `[{name, label, active, last_run}]` for all 10 agents | `agents/base.py` in-process liveness tracking (real staleness check, not hardcoded) |
| `GET /api/indices` | NIFTY 50 / NIFTY BANK (NSE) / SENSEX (yfinance fallback) | NSE allIndices + yfinance `^BSESN` |
| `GET /api/social-sentiment` | Overall Bullish/Bearish score + per-platform breakdown | SocialPost + YouTubeInsight (StockTwits + YouTube real; X/Reddit `connected: false`) |
| `GET /api/corporate-actions` | Upcoming/recent whole-market corporate actions | CorporateAction table |
| `GET /api/regulatory-announcements` | Whole-market NSE regulatory disclosures | RegulatoryAnnouncement table |
| `GET /api/risk-score` | Latest composite risk snapshot | RiskSnapshot table |
| `GET /api/economic-events` | Macro releases with importance tag | EconomicEvent table |
| `GET /api/briefing` | `{headline, summary, anomalies[], agents_triggered[], ai_generated, computed_at, orchestrator_active, orchestrator_last_run}` | MarketBriefing table (OrchestratorAgent) |
| `GET /api/fii-dii` | Real whole-market daily FII/DII net flow (₹ Cr, ~90 days accumulated) + news-derived per-stock FII/FDI/DII mentions (90-day window) + an AI daily summary | FiiDiiFlow + InstitutionalMention + FiiDiiSummary tables (FiiDiiAgent) |

#### `routes_alerts.py`

```
GET /api/alerts
```

Filters to **today's alerts only** using IST-based date conversion, and
builds each alert's "reason" text by parsing the percentage out of the
alert's own stored `message` (not a freshly re-fetched live price).

#### `routes_analytics.py` → delegates to `analytics_data.py`

| Endpoint | Returns |
|----------|---------|
| `GET /api/analytics/mutual-funds` | NAV + 1-year return per fund (9 funds, 3 categories) |
| `GET /api/analytics/gold` | 24K & 22K rates per gram and per 10g (IBJA via goodreturns.in) |
| `GET /api/analytics/fd-rates` | Fixed deposit rates from major banks |
| `GET /api/analytics/ipos` | Currently-open IPOs (Moneycontrol) merged with upcoming/current NSE IPOs |
| `GET /api/analytics/gov-bonds` | Top 5 government securities — static reference data |
| `GET /api/analytics/commodities` | Gold/Silver/Crude spot prices | yfinance |
| `GET /api/analytics/currencies` | INR exchange rates (USD/EUR/GBP/JPY) | yfinance |
| `POST /api/analytics/refresh` | Force-refreshes the analytics cache | — |

**Tools used:** FastAPI, SQLAlchemy, httpx

---

### Step 8 — WebSocket Live Feed (`ws.py`)

**What it does:** Maintains a persistent WebSocket connection at `/ws/alerts`. When AlertAgent creates a new `Alert`, it broadcasts it immediately to all connected frontend clients.

**Tools used:** FastAPI WebSockets, asyncio

---

### Step 9 — Analytics Data (`analytics_data.py`)

**What it does:** Fetches investment alternative data (mutual funds via mfapi.in, gold via goodreturns.in scraping, IPOs via Moneycontrol + NSE) from public sources. Unchanged by this round of work — see inline docstrings for scraping details.

**Tools used:** httpx, BeautifulSoup4, lxml, mfapi.in, goodreturns.in

---

### Step 10 — Web Data Cache (`web_data.py`)

**What it does:** Keeps a real-time in-memory dictionary of the most recent fetch for all data types — the fallback when the SQLite DB is empty (e.g. cold start before the first scheduler run). Refreshed every 30 minutes by `scheduler.py`.

**Tools used:** threading.Thread, httpx

---

## Agent Roster (10 agents)

| # | Agent | Frontend nav label | Status |
|---|-------|---------------------|--------|
| 1 | MarketAgent | Live Market | Implemented since v1 |
| 2 | NewsAgent | News Intelligence | Implemented since v1 |
| 3 | SocialAgent | Social Sentiment | StockTwits + YouTube real; X/Reddit omitted (no free API) |
| 4 | CorporateActionAgent | Corporate Actions | New — whole-market NSE corporate actions |
| — | *(Insider Trading)* | *(deliberately absent)* | Never built — no free NSE/BSE insider-disclosure API exists |
| 5 | RegulatoryAnnouncementAgent | SEBI Filings | New — NSE regulatory feed, honestly labeled (not literal SEBI EDIFAR) |
| 6 | EconCalendarAgent | Economic Calendar | Implemented since v1 |
| 7 | *(sector momentum, no standalone agent)* | Sector Rotation | Computed inline in `routes_market.py`'s extended `/api/sectors` |
| 8 | RiskAgent | Risk Monitor | New — composite volatility/liquidity score |
| 9 | RecommendationAgent | AI Recommendations | New — Buy/Hold/Sell + confidence, replaces the old inline composite |
| 10 | AlertAgent | Alerts | Implemented since v1 |
| — | YouTubeAgent | *(feeds the Social Sentiment page)* | Implemented since v1 |
| — | **OrchestratorAgent** | *(the Market Briefing panel, top of Overview)* | New — meta-agent over the 10 above, not an 11th roster card; see §4j |

The product spec's 10 agents map exactly to the 10 cards on the Overview
page's agent-status row (Market/News/Social/CorporateAction/Regulatory/
EconCalendar/SectorRotation/Risk/Recommendation/Alert) — Insider Trading is
intentionally not one of them, and neither is OrchestratorAgent (it
synthesizes and directs the 10 above, rather than being a data source
alongside them).

---

## 4. Frontend — Step by Step

### Step 11 — App Shell, Sidebar & Topbar (`App.tsx`, `Sidebar.tsx`, `TopBar.tsx`)

**What it does:** Replaces the old single top-nav-bar shell with a fixed left sidebar (14 nav items + a live "AI Agents Status" mini-panel) and a sticky top bar (brand, live index chips, market-open/closed status, last-updated time, search/notification/theme-toggle icons, refresh button, avatar).

```tsx
<BrowserRouter>
  <div className="app-shell">
    <TopBar onToggleSidebar={...} />
    <div className="app-body">
      <Sidebar collapsed={...} onNavigate={...} />
      <main className="app-main">
        <Routes>
          <Route path="/" element={<Dashboard />} />               {/* Overview */}
          <Route path="/live-market" element={<LiveMarketPage />} />
          <Route path="/news" element={<NewsPage />} />
          <Route path="/social" element={<SocialPage />} />
          <Route path="/corporate-actions" element={<CorporateActionsPage />} />
          <Route path="/sebi-filings" element={<SebiFilingsPage />} />
          <Route path="/economic-calendar" element={<EconomicCalendarPage />} />
          <Route path="/sector-rotation" element={<SectorRotationPage />} />
          <Route path="/risk-monitor" element={<RiskMonitorPage />} />
          <Route path="/recommendations" element={<RecommendationsPage />} />
          <Route path="/watchlist" element={<WatchlistPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/agents" element={<AgentsStatusPage />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/calculators" element={<Calculators />} />
        </Routes>
      </main>
    </div>
    <TickerStrip />
  </div>
  <ChatBot />
</BrowserRouter>
```

**Theme system:** dark is the default (`index.css`), with an explicit
toggle (`theme.ts`) persisted to `localStorage` and applied synchronously
by an inline script in `index.html` before first paint (avoids a
flash-of-wrong-theme). The sidebar/topbar chrome stays dark in *both* app
themes — a deliberate brand-consistency choice — so it uses its own
`--chrome-*` CSS tokens rather than the theme-flipping `--text-h`/`--muted`
ones (fixing a real bug where light mode made the topbar title invisible;
see `EXPERIMENTS.md`).

Below 960px, the sidebar becomes an off-canvas slide-in panel (hamburger
toggle in the topbar, dimmed scrim behind it) rather than a fixed column.

**Tools used:** React 19, React Router 7, TypeScript 6

---

### Step 12 — API Client (`api/client.ts`)

**What it does:** Single source of truth for all backend communication. Exports typed interfaces and an `api` object with one method per endpoint — including the 7 new endpoints added this round (`agentsStatus`, `indices`, `socialSentiment`, `corporateActions`, `regulatoryAnnouncements`, `riskScore`, `economicEvents`, `indexSeries`) and the reshaped `recommendations` (now `{picks, computed_at}`).

```typescript
export const api = {
  watchlist:    () => getJson<WatchlistItem[]>("/watchlist"),
  agentsStatus: () => getJson<AgentStatusItem[]>("/agents/status"),
  indices:      () => getJson<IndexItem[]>("/indices"),
  socialSentiment: () => getJson<SocialSentimentData>("/social-sentiment"),
  riskScore:    () => getJson<RiskScore | null>("/risk-score"),
  recommendations: () => getJson<RecommendationPicksData>("/recommendations"),
  indexSeries:  (index, range) => getJson<IndexSeriesPoint[]>(`/index-series?index=${index}&range=${range}`),
  ...
};
```

**Tools used:** Fetch API (native browser), TypeScript interfaces, WebSocket API

---

### Step 13 — Overview Page (`Dashboard.tsx`)

**What it does:** The new default route (`/`) — a card-grid Overview page assembled from live panel components, all polling their own endpoints independently.

```tsx
export default function Dashboard() {
  return (
    <div className="dashboard overview-page">
      <MarketBriefingPanel />                     {/* orchestrator's LLM briefing + anomalies */}
      <AgentStatusRow />                          {/* 10 real agent-status cards */}
      <div className="overview-grid overview-grid-top">
        <MarketOverviewChart />                    {/* chart.js, index tabs + 1D-1Y range */}
        <NewsPanel compact limit={8} />
        <SocialSentimentGauge />
      </div>
      <AIRecommendationCard limit={5} />
      <div className="overview-grid overview-grid-bottom">
        <SectorPerformance compact />
        <RiskMonitor />
        <CorporateActionsPanel limit={6} />
        <EconomicCalendarPanel limit={6} />
      </div>
    </div>
  );
}
```

A bottom-pinned `TickerStrip` (gainers/losers) is mounted once at the app
shell level, visible on every page.

**Tools used:** React 19 (useState, useEffect), chart.js, Fetch API, WebSocket

---

### Step 13b — Secondary Sidebar Pages

The remaining 12 sidebar nav items each route to a thin page that hosts
the same panel components full-width/expanded, rather than duplicating
markup:

| Page | Route | Renders |
|------|-------|---------|
| `LiveMarketPage.tsx` | `/live-market` | `MarketOverviewChart` + metric strip + commodity/currency panels + `MoversPanel` |
| `NewsPage.tsx` | `/news` | Full two-column `NewsPanel` |
| `SocialPage.tsx` | `/social` | `SocialSentimentGauge` + `SentimentHeatmap` + `YouTubeSentiment` |
| `CorporateActionsPage.tsx` | `/corporate-actions` | Expanded `CorporateActionsPanel` |
| `SebiFilingsPage.tsx` | `/sebi-filings` | Expanded `RegulatoryAnnouncementsPanel`, with an explicit "not SEBI EDIFAR" note |
| `EconomicCalendarPage.tsx` | `/economic-calendar` | Expanded `EconomicCalendarPanel` |
| `SectorRotationPage.tsx` | `/sector-rotation` | Full (non-compact) `SectorPerformance` |
| `RiskMonitorPage.tsx` | `/risk-monitor` | `RiskMonitor` |
| `RecommendationsPage.tsx` | `/recommendations` | `AIRecommendationCard` (expanded) + `FiiDiiPanel` (real flow + news-derived mentions) + `BuySellPanel` (web-scraped, market-wide signals) |
| `WatchlistPage.tsx` | `/watchlist` | `ShareWiseCharts` + the full watchlist table |
| `AlertsPage.tsx` | `/alerts` | Both `AlertFeed` panels |
| `AgentsStatusPage.tsx` | `/agents` | `AgentStatusRow` + a per-agent run-detail table (linked from the sidebar's "View Details" button) |

---

### Step 14 — Investment Alternatives Page (`Analytics.tsx`)

Unchanged in content this round — its redundant `.analytics-topbar` "←
Back to Dashboard" button was removed since the Sidebar now covers that
navigation for every page.

**Sections:** Gold Rate Panel · Top Mutual Funds by Category · Fixed
Deposit Rates · IPO Tracker.

**Tools used:** React 19, `Intl.NumberFormat` (INR formatting)

---

### Step 15 — Calculators Page (`Calculators.tsx`)

Two fully client-side calculators — no backend calls, all computation runs
in the browser.

**Asset Allocation Calculator:** Rule-of-100 equity/debt/gold/cash split
(age, horizon, risk profile, goal), editable percentages that proportionally
rebalance the rest, and a projected SIP corpus via a blended-CAGR future
value formula.

**Share Portfolio Drill:** builds a multi-stock portfolio and simulates it
forward via correlated Geometric Brownian Motion (a single common factor
`z = √ρ·f + √(1-ρ)·ε` blends each stock's idiosyncratic draw with a shared
market shock, `ρ` = the correlation slider). Each holding carries **Alpha
and Beta** alongside price/expected-return/volatility — Beta is a per-stock
input (defaults from a static catalog), Alpha is derived live via CAPM
(`α = μ − (rf + β×(market − rf))`), shown per-row and as portfolio-level
weighted metrics next to Sharpe/volatility.

Because a single simulated GBM path is inherently a different random draw
every time it's run (the literal complaint that prompted this rework — see
`EXPERIMENTS.md`), the panel now runs an **always-live 150-path Monte Carlo
ensemble** (`runMonteCarlo()`) alongside the animated single-path drill,
reporting mean/median/5th–95th-percentile range/chance-of-loss — by the law
of large numbers this stays statistically stable between clicks even though
any one path doesn't. The animated drill result is explicitly relabeled
"This Run's Result — one simulated path" rather than presented as *the*
answer. Accessibility: every table input has a distinguishing `aria-label`
(previously only the column header conveyed meaning), form labels use
`htmlFor`/`id` pairing, and the day counter is `aria-live="polite"`.

**Tools used:** React 19 (useState/useMemo), TypeScript, chart.js, CSS `conic-gradient`

---

### Step 16 — Components

| Component | What it does | Key technique |
|-----------|-------------|---------------|
| `Sidebar.tsx` | 14-item nav + live "AI Agents Status" mini-panel (count, dot row, note, View Details link) | `api.agentsStatus()`, `NavLink` active-state |
| `TopBar.tsx` | Brand, live index chips, market status pill, last-updated time, search/bell/theme icons, refresh, avatar | `api.indices()`, `marketStatus.ts`, `theme.ts` |
| `Icon.tsx` | ~24-glyph hand-rolled inline-SVG icon set (stroke-based, `currentColor`) | No icon library dependency |
| `MarketBriefingPanel.tsx` | Orchestrator's headline + summary, amber anomaly rows, "re-triggered off-cycle" agent chips | `api.briefing()` |
| `AgentStatusRow.tsx` | 10 agent cards: title, description, Active/Idle pill, decorative sparkline | `api.agentsStatus()`, per-card accent color |
| `MarketOverviewChart.tsx` | Index tabs (NIFTY 50/SENSEX/NIFTY BANK) + 1D-1Y range toggle, honest "unavailable" state | `chart.js`, `api.indexSeries()` |
| `SocialSentimentGauge.tsx` | Overall Bullish/Bearish + score/100 semicircle gauge, per-platform bars | Hand-rolled SVG arc, `api.socialSentiment()` |
| `AIRecommendationCard.tsx` | Ranked #1-N picks, Buy/Hold/Sell badge, confidence %, reason | `api.recommendations()` |
| `RiskMonitor.tsx` | Radial risk-score gauge + VIX/breadth/volatility/unusual-activity stat rows | Hand-rolled SVG circle, `api.riskScore()` |
| `CorporateActionsPanel.tsx` | Date-stamped list: company, action-type chip, value | `api.corporateActions()` |
| `RegulatoryAnnouncementsPanel.tsx` | Date-stamped list: company, category chip, subject, filing link | `api.regulatoryAnnouncements()` |
| `EconomicCalendarPanel.tsx` | Date-stamped list with importance-colored dot | `api.economicEvents()` |
| `FiiDiiPanel.tsx` | AI daily summary + real FII/DII flow bar chart + news-derived per-stock mention list (sentiment-dotted) | `api.fiiDii()` |
| `TickerStrip.tsx` | Bottom-pinned auto-scrolling gainers/losers ticker | CSS keyframe animation, `api.marketMovers()` |
| `AlertFeed.tsx` | Alert cards, severity-colored; parameterized by category | WebSocket via `connectAlertsSocket()` + `api.alerts()` |
| `MoversPanel.tsx` | Top 5 gainers & losers table, polls every 5 min | `api.marketMovers()`, colour-coded % change |
| `BuySellPanel.tsx` | Web-scraped buy/sell signal cards (secondary source, `/recommendations` page) | `api.marketRecommendations()` |
| `NewsPanel.tsx` | Compact single-feed (Overview) or split Indian/International columns (full page) | `api.news()` + sentiment tag |
| `SectorPerformance.tsx` | Momentum bar + trend arrow table, show more/less | `api.sectors()` |
| `SentimentHeatmap.tsx` | Colour-coded ticker grid | CSS `background-color` from sentiment |
| `TrendingStocks.tsx` | Ranked list of biggest movers | `api.trending()` |
| `ShareWiseCharts.tsx` | Day Move by Share — diverging bar chart per ticker | `.axis-row` pattern |
| `VolumePanel.tsx` | Volume relative to average | Comparison bar widths |
| `YouTubeSentiment.tsx` | YouTube Analyst Sentiment panel | `api.youtubeInsights()` |
| `RefreshButton.tsx` | Manual full-refresh trigger, now lives in `TopBar` | `api.refreshAnalytics()` |
| `ChatBot.tsx` | AI Q&A interface on every page | `routes_chat.py` → Claude Sonnet |

---

## 5. Data Flow

```
Every 30 min (APScheduler)
     │
     ├─► MarketAgent ──────────► Moneycontrol / yfinance ────► Price table
     ├─► NewsAgent ────────────► Google News RSS (Indian+Intl) ► NewsItem table
     ├─► SocialAgent ──────────► StockTwits API ──────────────► SocialPost table
     ├─► EconCalendarAgent ────► FRED ────────────────────────► EconomicEvent table
     ├─► CorporateActionAgent ─► NSE corporate-actions ────────► CorporateAction table
     ├─► RegulatoryAnnouncementAgent ► NSE corporate-announcements ► RegulatoryAnnouncement table
     ├─► RiskAgent ─────────────► NSE allIndices + own Price history ► RiskSnapshot table
     ├─► RecommendationAgent ───► Price + sentiment + sector + risk ► Recommendation table
     │        (reads the above 4 tables + latest RiskSnapshot)
     └─► AlertAgent (reads last 60 min of Price/NewsItem/SocialPost)
              │
              ├─► rules.py ──► needs_ai=False ──► Alert table directly
              └─► rules.py ──► needs_ai=True
                        └─► claude_client.py
                                 ├─► Haiku triage
                                 └─► Sonnet deep-dive (if flagged high-impact)
                                          └─► Alert table + WebSocket broadcast

Every 3 h (APScheduler)
     └─► YouTubeAgent ──► 6 channels' RSS + captions ──► rule-based extraction ──► YouTubeInsight table

Every 15 min (independent of the 30-min agent cadence) + tail of every full sweep
     └─► OrchestratorAgent (reads Price/sentiment/RiskSnapshot/sectors/Alert/Recommendation)
              │
              ├─► analysis/anomaly_rules.py — 5 threshold detectors decide
              │        (rule-based, never the LLM) which agents, if any, to
              │        re-trigger off-cycle right now
              │        └─► e.g. a >5% price move ──► News.run_safe() + Social.run_safe() + Alert.run_safe()
              └─► claude_client.generate_briefing() — Haiku, or Sonnet if an
                       anomaly fired — narrates the (already-decided) facts
                       into a headline + summary
                       └─► MarketBriefing table (no key/call failure →
                           deterministic templated fallback, never blank)

User opens browser (Sidebar + Topbar shell, dark theme by default)
     │
     └─► Frontend polls /api/* (interval varies per panel: 30s / 60s / 2-5 min)
              ├─► /watchlist, /agents/status, /indices, /sectors, /recommendations,
              │   /risk-score, /social-sentiment, /corporate-actions,
              │   /regulatory-announcements, /economic-events, /index-series, /briefing
              │        → all pure DB reads (or cached NSE/yfinance calls), never
              │          a blocking external call on the request path
              ├─► /alerts               → Alert table (today only, IST-filtered)
              ├─► /youtube-insights     → YouTubeInsight table (ticker IS NOT NULL)
              └─► /ws/alerts            → WebSocket live stream
```

---

## 6. Tools & Libraries Used

### Backend (Python)

| Tool | Purpose |
|------|---------|
| **FastAPI** | REST API framework + WebSocket support |
| **Uvicorn** | ASGI server to run FastAPI |
| **SQLAlchemy** | ORM for SQLite; 10 database models |
| **APScheduler** | Background scheduling (30-min intervals for 9 of 10 agents, 3h for YouTube, + IST cron) |
| **httpx** | Async/sync HTTP client for scraping & API calls, incl. the shared NSE session helper (`nse_client.py`) |
| **yfinance** | Yahoo Finance fallback for NSE stock prices, commodities, currencies, SENSEX, longer-range index history |
| **feedparser** | Google News + YouTube channel RSS feed parsing |
| **youtube-transcript-api** | Fetches YouTube's own captions |
| **vaderSentiment** | Rule-based sentiment scoring (news, social posts, YouTube transcripts) |
| **BeautifulSoup4 / lxml** | HTML parsing (goodreturns.in, Moneycontrol IPO) |
| **anthropic** | Official Python SDK for Claude API |
| **pydantic-settings** | Environment variable management via .env |
| **pytest** | Unit testing |

### Frontend (TypeScript / React)

| Tool | Version | Purpose |
|------|---------|---------|
| **React** | 19.2.7 | UI framework (Concurrent Mode, hooks) |
| **React Router** | 7.18.1 | Client-side routing (14 nav routes) |
| **TypeScript** | 6.0.2 | Static typing for all components and API interfaces |
| **chart.js** | 4.4.1 | Market Overview index chart (already used by Calculators' Monte-Carlo chart) |
| **Vite** | 8.1.0 | Dev server with HMR + production build bundler |
| **Oxlint** | 1.69.0 | Fast Rust-based linter |

No new frontend/backend dependencies were added for the redesign — the
sidebar/topbar shell, icon set, gauges, and charts are all hand-rolled on
top of libraries already in the project.

### External Data Sources

| Source | Data | Access method |
|--------|------|---------------|
| **Moneycontrol** | Live NSE prices, IPO listings | httpx scraping (browser headers) |
| **NSE India** | Sector indices + momentum, movers, corporate actions, regulatory announcements, headline indices, live intraday index series, IPOs | httpx via `nse_client.py`'s shared cookie-warm session |
| **yfinance** | NSE prices (fallback), commodities, currencies, SENSEX, longer-range index history | Python library — frequently blocked/rate-limited in some environments; honest "unavailable" fallback used throughout |
| **Google News RSS** | Financial headlines (Indian + International feeds) | feedparser |
| **StockTwits API** | Social sentiment | urllib (public, no key needed) |
| **YouTube RSS + captions** | 6 Indian finance channels' new videos + transcripts | httpx (feed) + youtube-transcript-api |
| **goodreturns.in** | Gold rates (IBJA daily retail rates) | httpx + BeautifulSoup |
| **mfapi.in** | Mutual fund NAV history | httpx JSON |
| **FRED API** | Macro / economic calendar events | httpx REST (no-ops if `FRED_API_KEY` unset) |

---

## 7. LLMs Used — Where and Why

Every AI-touched field in the app — alert explanations, recommendation
reasons, the Orchestrator briefing, corporate-action/regulatory/econ-calendar
one-liners, the YouTube sentiment summary, the FII/DII daily summary, and
the ChatBot — goes through the same **three-tier fallback ladder**, not
just a single Claude call:

```
1. Claude (Haiku, escalating to Sonnet for high-impact/anomaly cases)
       │  skipped entirely if ANTHROPIC_API_KEY is unset
       ▼
2. Local Ollama (via ollama_client.py, http://localhost:11434)
       │  tried whenever Claude is unset or its call fails;
       │  skipped if `ollama serve` isn't reachable or the model isn't pulled
       ▼
3. Deterministic rule-based / templated text
       (never raises, never a blank panel)
```

`claude_client.py`'s five functions (`triage_and_explain`,
`recommend_reason`, `generate_briefing`, `explain_relevance`,
`summarize_context`) all share one `_ollama_fallback()` helper for tier 2,
and `routes_chat.py` implements the same ladder directly for the ChatBot.
**No `ANTHROPIC_API_KEY` is configured by default** in this repo, so out of
the box every one of these runs on tier 2 (if a local Ollama server is
running) or tier 3. Company/recommendation/topic/tone extraction for the
YouTube panel, the Risk/Recommendation composite scores, and — critically —
**which agents OrchestratorAgent re-triggers** are all rule-based/
deterministic by design (no LLM call, and no LLM *decision*, involved at
all, regardless of tier).

### Tier 1 — `claude-haiku-4-5-20251001` — Fast Triage, Reasons & Briefings

**Used for:** every alert signal `rules.py` flags `needs_ai=True`, the
one-line reason on each of the top-5 displayed `RecommendationAgent` picks,
the routine (no-anomaly) `OrchestratorAgent` market briefing, the
corporate-action/regulatory/econ-calendar one-liners (bounded to the top 10
items per panel), and the YouTube/FII-DII narrative summaries.

**Why Haiku:** sub-second response time, very low cost per call.

---

### Tier 1 (escalated) — `claude-sonnet-4-6` — Deep Analysis & Chat

**Used for:** only the alert subset Haiku itself flags `HIGH_IMPACT: yes`,
the `OrchestratorAgent` briefing *only* on cycles where a rule-based
anomaly actually fired (richer analysis when there's more to explain), and
every ChatBot conversation turn.

---

### Tier 2 — Local Ollama (`ollama_client.py`, model: `llama3.2` by default)

**Used for:** the exact same call sites as tier 1, as a free fallback when
no Anthropic key is configured (or a Claude call fails) — requires
`ollama serve` running locally with `OLLAMA_MODEL` pulled
(`OLLAMA_BASE_URL`/`OLLAMA_MODEL` in `.env`, see §9). Two Ollama-specific
tuning notes baked into `ollama_client.py`: `num_ctx` is explicitly raised
to 8192 (Ollama's 2048 default silently truncates most of the DB-grounded
system prompt otherwise), and temperature is kept near-zero to stay
extractive rather than creative when reading back real numbers. Genuinely
answers with real DB-grounded numbers, not fabricated ones — verified live,
see `EXPERIMENTS.md`.

---

### Cost Strategy

`claude_client.py` caches by a SHA-256 hash of the prompt for the life of
the process — a re-fired identical signal or recommendation reason returns
the cached explanation instead of paying for it twice (tier 1 only; Ollama
calls are free so aren't cached). The Recommendation Agent bounds spend
further by only requesting an AI reason for the top-5 picks actually
displayed, never the full watchlist. Corporate-action/regulatory/
econ-calendar one-liners are bounded to the top 10 items shown per panel
and persist once written, so a run only pays for genuinely new entries.

---

## 8. Setup & Running

### Prerequisites

- Python 3.11+
- Node.js 20+
- An Anthropic API key is **optional** — see [§7](#7-llms-used--where-and-why). Without one, a local Ollama server (also optional) or a rule-based fallback runs instead. Everything else (prices, news, social, sectors, corporate actions, regulatory announcements, economic calendar, risk, recommendations, FII/DII flow, YouTube sentiment, analytics) needs no key at all.

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Mac/Linux
pip install -r requirements.txt
cp .env.example .env
# Edit .env and fill in your API keys

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173 (falls back to the next free port,
# e.g. 5174, if 5173 is already in use — the backend's default
# ALLOWED_ORIGINS covers 5173-5175 for this)
```

### Docker (full stack)

```bash
docker-compose up --build
# Backend: http://localhost:8000
# Frontend: http://localhost:5173
```

---

## 9. Environment Variables

Create `backend/.env` from `.env.example`:

```env
# Watchlist — NSE tickers in Yahoo Finance format (.NS suffix)
WATCHLIST=RELIANCE.NS,HDFCBANK.NS,TCS.NS,ICICIBANK.NS,BHARTIARTL.NS,CGPOWER.NS,DIXON.NS,COFORGE.NS,PERSISTENT.NS,MPHASIS.NS,CDSL.NS,IEX.NS,CYIENT.NS,GLENMARK.NS,BIRLACORPN.NS

# AI — tier 1 of the 3-tier fallback ladder (§7). Optional; unlocks
# Claude-generated alert explanations, recommendation reasons, briefings,
# and ChatBot answers. Without it, tier 2 (Ollama, below) or tier 3
# (rule-based / templated text) runs instead — never a blank panel.
ANTHROPIC_API_KEY=sk-ant-...

# AI — tier 2, the free no-API-key fallback. Requires `ollama serve`
# running locally with OLLAMA_MODEL pulled (`ollama pull llama3.2`). If
# unreachable, every AI touchpoint falls through to tier 3 automatically.
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2

# News — optional; falls back to Google News RSS if missing
NEWSAPI_KEY=...

# Database — SQLite file path
DATABASE_URL=sqlite:///./market_monitor.db

# CORS — comma-separated allowed frontend origins (defaults cover local
# dev ports 5173-5175; a real deployment must set this to the frontend's
# actual public URL)
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

No env var is needed for CorporateActionAgent, RegulatoryAnnouncementAgent,
RiskAgent, RecommendationAgent, EconCalendarAgent, FiiDiiAgent, or the
YouTube Analyst Sentiment feature — all use free, keyless NSE/YouTube/
Trading-Economics endpoints or the app's own accumulated data.

---

## 10. Deploying to GCP

The app deploys as a single **Compute Engine VM** running both containers via
`docker-compose` — frontend and backend share one host/IP, so the frontend's
API client falls back to `http://<hostname>:8000` automatically
(`frontend/src/api/client.ts`) with no `VITE_API_BASE_URL` build arg needed.
This is why `backend/.env.production`'s `ALLOWED_ORIGINS` is a raw
`http://<external-ip>:5173` rather than an HTTPS Cloud Run–style URL.

### Step 1 — Create the VM

```bash
gcloud compute instances create stock-market-monitor \
  --zone=asia-south1-a \
  --machine-type=e2-small \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --tags=http-server \
  --boot-disk-size=20GB
```

Reserve a **static external IP** so it survives VM restarts (matches what
`ALLOWED_ORIGINS`/CORS is pinned to):

```bash
gcloud compute addresses create stock-market-monitor-ip --region=asia-south1
gcloud compute instances add-access-config stock-market-monitor \
  --zone=asia-south1-a \
  --address=$(gcloud compute addresses describe stock-market-monitor-ip --region=asia-south1 --format='get(address)')
```

### Step 2 — Open firewall ports

```bash
gcloud compute firewall-rules create allow-market-monitor \
  --allow=tcp:8000,tcp:5173 \
  --target-tags=http-server \
  --source-ranges=0.0.0.0/0
```

### Step 3 — Install Docker on the VM

SSH in (`gcloud compute ssh stock-market-monitor --zone=asia-south1-a`) and:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
sudo apt-get install -y docker-compose-plugin
```

### Step 4 — Ship the code and configure the environment

```bash
git clone <your-repo-url> && cd StockMarketMonitor
cp backend/.env.production backend/.env
# Edit backend/.env: fill in ANTHROPIC_API_KEY / NEWSAPI_KEY / FRED_API_KEY
# (all optional — see §9), and set ALLOWED_ORIGINS to the VM's static IP:
#   ALLOWED_ORIGINS=http://<external-ip>:5173
```

### Step 5 — Build and run

```bash
docker compose up --build -d
```

- Backend: `http://<external-ip>:8000`
- Frontend: `http://<external-ip>:5173`

`docker-compose.yml` mounts the SQLite DB at `/app/data` as a named volume
(`backend_data`), so it survives `docker compose up` rebuilds.

### Step 6 — Verify

```bash
curl http://<external-ip>:8000/api/watchlist
curl http://<external-ip>:8000/api/agents/status   # should show all 10 agents, active after the first sweep
```

Then open `http://<external-ip>:5173` in a browser and confirm the
Overview dashboard loads live data.

### Updating a running deployment

```bash
git pull
docker compose up --build -d
```

Or, once CI/CD is set up (below), just `git push` — no SSH needed.

---

## 11. CI/CD

`.github/workflows/deploy.yml` runs on every push/PR to `main`:

```
push/PR → main
   ├─► backend-tests   (pytest, backend/requirements.txt)
   └─► frontend-build  (npm ci && npm run build — tsc + vite)
            │
            ▼  (only on push to main, only if both jobs above passed)
         deploy
            └─► SSH into the GCE VM (appleboy/ssh-action) and run:
                git fetch origin main
                git reset --hard origin/main
                sudo docker compose up --build -d
```

Opening a PR runs the tests/build without deploying; merging (or pushing
directly) to `main` deploys automatically.

### One-time setup

1. **Put the VM's code under git**, not a one-off `scp` — clone the repo
   into the same path `docker-compose.yml` expects, keeping `backend/.env`
   in place (it's gitignored, so a later `git reset --hard` never touches
   it):
   ```bash
   mv StockMarketMonitor StockMarketMonitor.bak   # keep the old copy just in case
   git clone <your-repo-url> StockMarketMonitor
   cp StockMarketMonitor.bak/backend/.env StockMarketMonitor/backend/.env
   cd StockMarketMonitor && sudo docker compose up --build -d
   ```

2. **Generate a dedicated deploy keypair** (not your personal SSH key) and
   append the public half to the VM's `authorized_keys`:
   ```bash
   ssh-keygen -t ed25519 -f deploy_key -N "" -C "github-actions-deploy"
   # then on the VM:
   #   mkdir -p ~/.ssh && echo "<contents of deploy_key.pub>" >> ~/.ssh/authorized_keys
   ```

3. **Add three repo secrets** (Settings → Secrets and variables → Actions):

   | Secret | Value |
   |--------|-------|
   | `DEPLOY_HOST` | the VM's static external IP |
   | `DEPLOY_USER` | the SSH username on the VM |
   | `DEPLOY_SSH_KEY` | contents of the **private** half of the deploy keypair |

4. Push `.github/workflows/deploy.yml` to `main`. If this is the *first*
   push containing a workflow file, a plain `repo`-scoped `gh`/git token
   will be rejected — GitHub requires the `workflow` OAuth scope to create
   or update files under `.github/workflows/`:
   ```bash
   gh auth refresh -h github.com -s workflow
   gh auth setup-git
   ```

**Rotating the deploy key:** generate a new pair, append the new public key
to the VM's `authorized_keys` (don't remove the old one until the new one
is confirmed working), then `gh secret set DEPLOY_SSH_KEY < newkey`.

---

*Built with FastAPI · React 19 · Claude AI (Haiku + Sonnet) + local Ollama fallback · NSE India · goodreturns.in · mfapi.in · youtube-transcript-api*
