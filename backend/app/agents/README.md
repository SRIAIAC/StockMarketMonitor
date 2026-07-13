# Agents

Background workers that fetch external data, normalize it, and write it to
the database. The FastAPI routes never call external APIs directly — they
only read what the agents have already stored (or a short-lived web cache),
so requests stay fast even when a data source is slow or down.

## Common pattern (`base.py`)

Every agent subclasses `BaseAgent` and implements `run()`. The scheduler
calls `run_safe()`, which wraps `run()` in a try/except and logs failures
instead of raising — one flaky source (e.g. Yahoo Finance rate-limiting)
never takes down the scheduler or the other agents.

## The agents

| Agent | File | Data source | Writes to | Notes |
|---|---|---|---|---|
| **MarketAgent** | `market_agent.py` | Moneycontrol price-feed API (primary), yfinance batch download and `Tickers.fast_info` (fallbacks, in that order) | `Price` | Fetches price, previous close, volume, avg volume, and sector for every ticker in `settings.tickers` — 50 NSE tickers spanning 20 large-cap, 15 mid-cap, and 15 small-cap names across banking, IT, FMCG, auto, pharma, energy, cement, metals, chemicals, and consumer/retail (see `frontend/src/marketBuckets.ts` for the exact bucket assignment used by the Watchlist page). Falls through fallbacks only when the previous source returns no usable price/prev_close. |
| **NewsAgent** | `news_agent.py` | Google News RSS (3 India-market search feeds) | `NewsItem` | Skips URLs already stored (dedup). Matches a ticker by checking if it appears in the headline. Scores headline sentiment with VADER (`analysis/sentiment.py`) at fetch time. |
| **SocialAgent** | `social_agent.py` | StockTwits public stream API (`streams/symbol/{ticker}.json`, one call per ticker) | `SocialPost` | No API key needed. Each post arrives already tagged to its exact ticker (`RELIANCE.NSE`, etc. — the `.NS`→`.NSE` suffix swap), so no fuzzy text matching is needed. Uses `urllib.request`, not `httpx` — StockTwits' Cloudflare front blocks `httpx`'s TLS fingerprint (403) but lets `urllib` through. |
| **EconCalendarAgent** | `econ_calendar_agent.py` | Trading Economics' public India calendar page (`tradingeconomics.com/india/calendar`), scraped with `httpx`+`BeautifulSoup` | `EconomicEvent` | No API key, no US-only FRED data — this replaced an earlier FRED-based version that only ever covered US series (CPI/unemployment/fed funds/GDP), which is a structural mismatch for an India-first app. Parses the page's date-grouped event table for whatever India releases it's currently tracking (CPI/WPI, GDP, IIP, PMI, RBI rate decisions, trade balance, forex reserves, etc.) — no static series allowlist to maintain. Upserts by `(series_id, release_date)` so a row initially stored with only a forecast gets its `value`/`detail` updated in place once the real print releases. `detail` carries the previous/forecast context string (e.g. `"Prev 5.25% · Fcst 5.25%"`). The **10 most recent releases** (matching `GET /api/economic-events`'s ordering) get a one-line `ai_reason` via `claude_client.explain_relevance()` — falls back to an importance-tier templated line (high/medium/low) with no API key, never blank. Cleared and regenerated when a release moves from forecast to actual (the old reason no longer matches the new facts). |
| **YouTubeAgent** | `youtube_agent.py` | Each channel's public RSS feed (`feeds/videos.xml?channel_id=...`, no API key) + `youtube-transcript-api` for captions | `YouTubeInsight` + `YouTubeSentimentSummary` | Polls 6 Indian finance YouTube channels (CA Rachana Ranade, SOIC, Groww, Zerodha Varsity, ET Now, CNBC-TV18), pinned by channel ID (handles get squatted/redirected). Pulls YouTube's own captions rather than downloading audio — no ffmpeg/Whisper. Company/recommendation/topic/tone extraction is rule-based (`analysis/youtube_analysis.py`): a name gazetteer, buy/sell/hold keyword counts, a topic-keyword taxonomy, and VADER tone — same "no AI key needed" approach as the rest of the pipeline. Several channels are Hindi/Hinglish; those rows are tagged `language="hi"` since auto-captions partially transliterate company names and extraction accuracy is lower. After storing each run's insights, one Claude call (`claude_client.summarize_context()`) rolls up the last 14 days of ticker-tagged calls into a plain-English paragraph — one call per 3h run regardless of video count, not per video; falls back to a templated buy/sell/bullish/bearish count with no API key. |

**YouTubeAgent hardening (learned the hard way — see `EXPERIMENTS.md` for the
live incident that drove each of these):**
- **Rate limiting:** YouTube's transcript endpoint blocks IPs that burst many
  requests (`IpBlocked`/`RequestBlocked`) — transcript fetches are paced 3s
  apart, capped at 2 new videos/channel/run, and the *whole run* aborts the
  instant a block is detected rather than burning through the rest of the
  queue and prolonging the block.
- **Feed flakiness:** the RSS feed endpoint itself intermittently returns
  404/500 (confirmed live: same URL failed then succeeded 3x a few seconds
  apart) and rejects `feedparser`'s own bare HTTP request for some channels.
  Feeds are now fetched via `httpx` with a real browser User-Agent and a
  3-attempt/2s-backoff retry before giving up on a channel for that cycle.
- **No-company-mentions videos:** a video that yields zero gazetteer matches
  gets a `ticker=NULL` marker row (rather than no row at all) so the agent
  recognizes it as "already tried" and doesn't re-spend its whole per-channel
  budget re-fetching the same empty video every single cycle. `/api/youtube-insights`
  filters these markers out.
| **AlertAgent** | `alert_agent.py` | The last 60 minutes of rows from `Price`, `NewsItem`, `SocialPost` | `Alert` (+ broadcasts over the `/ws/alerts` WebSocket) | Doesn't call any external API itself — it's the rules/AI layer that turns the other agents' raw data into alerts. See below. |
| **CorporateActionAgent** | `corporate_action_agent.py` | NSE `/api/corporates-corporateActions` (whole market, via `app/api/nse_client.py`) | `CorporateAction` | Dividends/bonuses/splits/rights/buybacks/AGMs, classified from NSE's free-text `subject` field by keyword match. Not scoped to `settings.tickers` — whole-market, bounded to a rolling ~30-days-back/60-days-forward window by ex-date so the table doesn't grow unbounded. The **10 actions actually shown at the top of the panel** (same ordering/filter as `GET /api/corporate-actions`) get a one-line `ai_reason` via `claude_client.explain_relevance()`, falling back to an `action_type`-keyed templated line with no API key — reasons persist once written, so a run only pays for genuinely new top-10 entries. |
| **RegulatoryAnnouncementAgent** | `regulatory_announcement_agent.py` | NSE `/api/corporate-announcements` (whole market) | `RegulatoryAnnouncement` | **Naming note:** this is NSE's own regulatory/compliance disclosure feed (board meetings, credit ratings, investor presentations, LODR compliance, etc.) — not literal SEBI EDIFAR filings, since no free public API for those exists (the same structural gap that led to InsiderAgent's removal below). The frontend must label this "NSE Regulatory Announcements", never "SEBI Filings". Insider-trading/SAST-disclosure items are explicitly filtered out before storage, even though NSE's raw feed technically carries some adjacent categories. Same bounded `ai_reason` backfill as CorporateActionAgent (top 10 by `announcement_date`), with a category-keyword fallback (board meeting / financial result / credit rating / etc.) when no API key is configured. |
| **RiskAgent** | `risk_agent.py` | India VIX + whole-market advance/decline breadth (both from the same NSE `/api/allIndices` payload `routes_market.py` already calls for sector data) + our own `Price` history | `RiskSnapshot` | Composite 0-100 risk score (India VIX 40% + market breadth 25% + watchlist volatility 20% + volume-spike ratio 15%) with a Low/Moderate/High label. No new external dependency. Weights/normalization ranges are a starting point flagged for recalibration once real score history accrues, same spirit as `analysis/rules.py`'s tuned thresholds. |
| **RecommendationAgent** | `recommendation_agent.py` | `Price` + `NewsItem`/`SocialPost` sentiment + sector rotation momentum (`routes_market.py`'s extended `/api/sectors`) + the latest `RiskSnapshot` | `Recommendation` | Buy/Hold/Sell label + confidence % for the 50-stock watchlist (kept watchlist-scoped for v1 — richest per-ticker signal). Extends the composite-score idea that used to live inline in `routes_dashboard.recommendations()` with a sector-momentum term and a risk dampener. AI one-line reasons (`analysis/claude_client.recommend_reason()`) are requested only for the top-ranked picks actually displayed, to bound spend. `routes_market.py`'s separate `/api/market-recommendations` (web-scraped, whole-market, unscored) remains a distinct signal surfaced on its own section rather than merged into this scored pipeline. |
| **OrchestratorAgent** | `orchestrator_agent.py` | Every other agent's latest DB rows (`Price`, `NewsItem`/`SocialPost` sentiment, `RiskSnapshot` history, live sector momentum, `Alert` counts, `Recommendation`) — no external calls of its own | `MarketBriefing` | A meta-agent, not a data-source agent — deliberately **not** one of the 10 agent-roster cards on the Overview page (see below). Two jobs: (1) runs deterministic anomaly detection (`analysis/anomaly_rules.py`) and re-triggers just the specific agents relevant to whatever anomaly fired (e.g. a >5% price move re-triggers News/Social/Alert, not the whole `run_all_agents()` sweep); (2) asks Claude to narrate the current cross-agent state into a short plain-English briefing. **The trigger decision is always rule-based, never left to the LLM** — same "rules decide, AI only narrates/explains" split as AlertAgent, just applied one level up. Runs on its own 15-minute interval (more often than the other agents' 30-minute cadence) so it can react between full sweeps, plus once more at the tail of every `run_all_agents()` sweep. The **narrated** content reflects the whole trading day (e.g. "30 warning/critical alerts so far today"), not just the current 15-minute tick — the anomaly-detection rules underneath keep their own short windows (15 min for a burst, 1h for a sentiment cliff) since a genuinely sudden event needs a recent baseline, not a day-long average, to be detectable at all. |
| **FiiDiiAgent** | `fii_dii_agent.py` | NSE `/api/fiidiiTradeReact` (real, whole-market daily net FII/DII ₹ Cr) + Google News RSS matched against the watchlist via the same company-name gazetteer YouTubeAgent uses | `FiiDiiFlow` (one row/trading day) + `InstitutionalMention` (per-stock, VADER-scored) + `FiiDiiSummary` (one row/trading day) | Also **not** one of the 10 roster cards, same reasoning as OrchestratorAgent. There is no free public API anywhere that discloses which specific stocks are "about to receive" FII/FDI/DII investment — that's forward-looking data nobody publishes — and NSE's own bulk/block-deals endpoint (the closest real per-stock disclosure) is blocked (503) from this environment, the same class of protection as `quote-equity`. So this is honestly two separate things: a real whole-market flow trend, and a news-derived per-stock signal explicitly labeled as "not confirmed transactions." Uses `extract_companies()` (full company-name matching) rather than `news_agent.py`'s bare-ticker matcher, since FII/DII/FDI headlines almost always name companies ("Bharti Airtel"), never raw ticker symbols. A daily AI narrative (`claude_client.summarize_context()`) over the flow trend + recent mentions is generated once per real trading day — dedup'd on `trade_date` like `FiiDiiFlow` itself, so it costs one Claude call per day, not one per 3h agent run; falls back to a templated net-buying/selling line with no API key. |

> **Removed:** an `InsiderAgent` previously queried SEC EDGAR (Form 4 filings)
> for the NSE tickers in `settings.tickers`. That's a structural dead end —
> EDGAR only covers US SEC filers, so Indian NSE-listed companies never
> appear there regardless of how long it runs. There's no equivalent free
> public API for NSE/BSE insider-trading disclosures, so the agent, its
> `InsiderFiling` table, and the `insider` alert category were removed
> rather than left running as a permanent no-op. This stays removed — the
> product intentionally ships without an Insider Trading agent, panel, or
> nav item.

## Three-tier AI: Claude → Ollama → rule-based, never blank

Every function in `analysis/claude_client.py` (`triage_and_explain`,
`recommend_reason`, `generate_briefing`, `explain_relevance`,
`summarize_context`) tries Claude first, then falls through to a local
Ollama server (`analysis/ollama_client.py`, same three-tier ladder
`/api/chat` already used) if `ANTHROPIC_API_KEY` isn't configured, and
only returns `None` — letting the calling agent's own deterministic
template take over — if neither is reachable. This means every AI-touched
field in the app (alert explanations, recommendation reasons, the
Orchestrator briefing, corporate-action/filing/econ-calendar one-liners,
the YouTube and FII/DII summaries) is real model-generated text on any
machine with `ollama serve` running, not just ones with a paid API key.

A concrete bug this caught: the Orchestrator's `_fallback_briefing()` (the
third tier, shown when neither Claude nor Ollama answers) had never been
updated when the briefing's *narrated* content was changed to reflect the
whole trading day instead of the current 15-minute cycle — it silently
kept saying "detected this cycle" and never mentioned the day's alert
count at all, since that info was only ever added to the AI-facing
context text, not the template actually shown to most users. Fixed
alongside the Ollama wiring.

Tests must never depend on a real Ollama server being reachable —
`tests/conftest.py` has an autouse fixture patching `claude_client.
_ollama_fallback` to `None` by default; a test that wants to exercise the
Ollama path explicitly re-patches it (see `test_claude_client.py`). Skipping
this turned two agent tests into ~15s network-dependent tests the first
time Ollama was wired in — caught immediately since these tests normally
run in a fraction of a second.

## AlertAgent: rules first, AI only when it's worth paying for

`AlertAgent` runs deterministic threshold checks (`analysis/rules.py`) over
everything fetched in the last 60 minutes (widened from 30 — that exactly
matched the agents' own 30-minute run interval, leaving too little margin
against scheduler jitter; `SocialAgent` in particular often fetches zero
*new* posts in a given cycle, so a qualifying post landing just before a
tight window closed could age out before `AlertAgent` ever saw it):

- **Price**: ≥3% move; escalates to `critical` + AI if volume is also ≥2×
  the average (a real move, not noise).
- **News**: ticker-tagged headline with VADER sentiment ≤ -0.5.
- **Social**: StockTwits post with score (likes) ≥ 1 (AI only if ≥ 2) — lowered
  from ≥ 3/≥ 6 after real data showed only ~1.8% of collected posts ever hit
  that bar, leaving the social-alerts panel empty almost every day.

Signals are deduped per ticker/category/day before being turned into an
`Alert` row. Only signals flagged `needs_ai=True` get a Claude call
(`analysis/claude_client.py`, Haiku for fast triage) to turn the raw
threshold breach into a plain-English explanation — this keeps the majority
of alerts free and instant, and reserves the paid API for the genuinely
ambiguous/high-impact ones.

`routes_alerts.py` builds each alert's displayed "reason" text (e.g. "Stock
gained 3.58% intraday... Latest news: ...") by parsing the percentage out of
the alert's own stored `message`, not a freshly re-fetched live price. It
used to re-derive direction/percentage from the *current* watchlist price at
read time, which drifted from the original alert as the day went on —
producing real contradictions like a `"+3.58%"` badge next to a reason
claiming the stock "declined 1.15%".

## Scheduling (`scheduler.py`)

- Market/News/Social/CorporateAction/RegulatoryAnnouncement/Risk/
  Recommendation/Alert (+ the web/analytics cache refresh) run on a
  **30-minute interval**. Recommendation and Risk run after Market/News/
  Social in `run_all_agents()`'s sequential order so they read
  freshly-written data. YouTubeAgent, EconCalendarAgent, and FiiDiiAgent run
  on a **3-hour interval** instead — YouTube channels post far less often
  than prices or headlines move, EconCalendarAgent scrapes a third-party
  page rather than calling a JSON API, and FiiDiiAgent's NSE flow figure
  only updates once per trading day anyway — so a slower cadence is both
  plenty and a better citizen of the sites being scraped.
- OrchestratorAgent runs on its own **15-minute interval**, independent of
  the 30-minute agent cadence, so it can catch and react to anomalies
  between full sweeps — plus once more at the very end of `run_all_agents()`
  so a fresh briefing follows immediately after every scheduled full sweep
  and the two daily market-open/close sweeps.
- A full sweep (`run_all_agents`, including YouTubeAgent) also runs at
  **09:15 IST** (market open) and **15:45 IST** (15 min after market close).
- `trigger_immediate_refresh()` fires `run_all_agents` in a background
  thread on demand (used by the frontend's "Refresh" button).
