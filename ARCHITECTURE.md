# Architecture

A system-level reference: how the pieces fit together, how data and
requests actually flow, how it's deployed, and why the major structural
decisions were made. For a step-by-step walkthrough of every file, route,
and component, see [README.md](README.md); for the history of what changed
and why, see [EXPERIMENTS.md](EXPERIMENTS.md).

---

## 1. System at a Glance

StockMarketMonitor is a full-stack Indian (NSE) stock market dashboard: a
FastAPI backend runs 11 independent background agents on a scheduler,
each fetching from a different free/public data source and writing to its
own SQLite table; a React frontend polls read-only REST endpoints (plus one
WebSocket for live alerts) and never talks to an external data source
directly. Three optional AI tiers (Claude → local Ollama → deterministic
rule-based text) narrate what the rules have already decided — the AI never
makes the underlying decision, only explains it.

```
┌─────────────────────────────────────────────────────────────────────┐
│  Browser                                                             │
│  React 19 SPA — Sidebar (14 routes) + TopBar + Overview card-grid    │
└───────────────────────────────┬─────────────────────────────────────┘
                                 │ HTTPS/HTTP · REST + WebSocket
┌───────────────────────────────▼─────────────────────────────────────┐
│  FastAPI Backend (single process)                                    │
│  ┌──────────────┐   ┌───────────────────┐   ┌─────────────────────┐ │
│  │  REST routes  │   │   APScheduler      │   │  WebSocket /ws/alerts│ │
│  │  (read-only —│   │   (in-process,      │   │  (Alert push)        │ │
│  │  DB reads or  │◄──┤   BackgroundScheduler)  └─────────────────────┘ │
│  │  short-lived  │   └─────────┬───────────┘                          │
│  │  cache reads) │             │ triggers                             │
│  └───────┬───────┘   ┌─────────▼───────────────────────────────────┐ │
│          │           │  11 Agents (BaseAgent.run_safe())            │ │
│          │           │  Market·News·Social·CorporateAction·         │ │
│          │           │  Regulatory·EconCalendar·Risk·Recommendation·│ │
│          │           │  YouTube·FiiDii·Alert  +  OrchestratorAgent   │ │
│          │           │  (meta-agent over the 11, not a 12th card)    │ │
│          │           └─────────┬────────────────────┬───────────────┘ │
│          │                     │ fetch/normalize/store│ narrate        │
│          │           ┌─────────▼──────────┐  ┌────────▼─────────────┐ │
│          │           │  External sources   │  │  AI fallback ladder  │ │
│          │           │  (§3)               │  │  (§4)                 │ │
│          │           └─────────────────────┘  └───────────────────────┘ │
│          │                                                              │
│  ┌───────▼──────────────────────────────────────────────────────────┐ │
│  │  SQLite (15 tables — one per agent's output, append-only where    │ │
│  │  history matters, full-replace where only "latest" matters)       │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
```

**The one rule everything else follows:** routes never call an external API
on the request path. An agent fetches → normalizes → stores; a route only
ever reads what's already in SQLite (or a short-lived in-memory cache
refreshed by the same scheduler). This is why the app stays fast and
responsive even when NSE, Yahoo Finance, or YouTube are slow, rate-limited,
or down — a slow/failed agent run degrades data *freshness*, never request
*latency*, and `run_safe()` means one agent's failure never takes down the
scheduler or any other agent.

---

## 2. Agent Roster & Cadence

| Agent | Table(s) written | Cadence | Notes |
|---|---|---|---|
| MarketAgent | `Price` | 30 min | Moneycontrol → yfinance fallback |
| NewsAgent | `NewsItem` | 30 min | Google News RSS, VADER sentiment |
| SocialAgent | `SocialPost` | 30 min | StockTwits (keyless) |
| CorporateActionAgent | `CorporateAction` | 30 min | Whole-market NSE, not watchlist-scoped |
| RegulatoryAnnouncementAgent | `RegulatoryAnnouncement` | 30 min | NSE disclosures — explicitly not SEBI EDIFAR (§6) |
| RiskAgent | `RiskSnapshot` | 30 min | Composite VIX/breadth/volatility/volume score |
| RecommendationAgent | `Recommendation` | 30 min | Buy/Hold/Sell + confidence, full-replace per run |
| AlertAgent | `Alert` | 30 min | Reads the last 60 min of Price/News/Social |
| YouTubeAgent | `YouTubeInsight`, `YouTubeSentimentSummary` | 3 h | 6 channels, transcript-based, rule-based extraction |
| EconCalendarAgent | `EconomicEvent` | 3 h | Trading Economics scrape (real India data, no API key) |
| FiiDiiAgent | `FiiDiiFlow`, `InstitutionalMention`, `FiiDiiSummary` | 3 h | Real NSE flow + news-derived per-stock mentions |
| **OrchestratorAgent** *(meta)* | `MarketBriefing` | 15 min | Reads all agents above; see §5 |

Plus two daily IST cron sweeps (09:15 and 15:45, market open/close) that
run every agent once in sequence via `run_all_agents()`.

**Why three different cadences, not one:** the 30-minute agents track data
that genuinely changes intraday (prices, news, sentiment). YouTube/
EconCalendar/FiiDii track things that don't — a channel posts a few
times a week, a macro release happens once a month, the FII/DII flow
figure only updates once per trading day — polling them every 30 minutes
would just hammer a third-party site for no new information. The
Orchestrator runs *faster* than everything else specifically so it can
react to an anomaly between full sweeps, not slower.

---

## 3. External Data Sources

| Source | What it provides | Auth |
|---|---|---|
| Moneycontrol | Live NSE prices, IPO listings | None (scraped) |
| NSE India (`nse_client.py`, shared cookie-warm session) | Sector indices, movers, corporate actions, regulatory announcements, index series, FII/DII flow | None |
| yfinance | Price/commodity/currency fallback, SENSEX, longer-range index history | None |
| Google News RSS | Headlines (general + FII/DII-themed queries) | None |
| StockTwits API | Social sentiment | None |
| YouTube (RSS + captions) | 6 Indian finance channels | None |
| Trading Economics | India macro calendar | None (scraped) |
| goodreturns.in / mfapi.in | Gold rates / mutual fund NAVs | None |

Every integration in this app is deliberately keyless. The two places an
API key is *optional* are the AI tiers (§4) — everything else works with
zero configuration, which is why `docker compose up` produces a fully
functional app with an empty `.env`.

---

## 4. AI Fallback Ladder

A cross-cutting pattern, not a per-feature choice — every AI-touched string
in the app goes through the same three tiers:

```
                    ┌─────────────────────────┐
                    │ 1. Claude (Haiku, or     │   skipped if
                    │    Sonnet for high-      │   ANTHROPIC_API_KEY
                    │    impact/anomaly cases) │   is unset
                    └────────────┬─────────────┘
                                 │ unset or call failed
                    ┌────────────▼─────────────┐
                    │ 2. Local Ollama           │   skipped if
                    │    (llama3.2 by default)  │   ollama serve isn't
                    │                           │   reachable
                    └────────────┬─────────────┘
                                 │ unreachable or call failed
                    ┌────────────▼─────────────┐
                    │ 3. Deterministic rule-    │   never fails —
                    │    based / templated text │   this is the floor
                    └───────────────────────────┘
```

Implemented once, in `claude_client.py`'s shared `_ollama_fallback()`
helper, reused by every AI call site: alert triage, recommendation reasons,
the Orchestrator briefing, corporate-action/regulatory/econ-calendar
one-liners, the YouTube and FII/DII summaries, and the ChatBot
(`routes_chat.py` implements the same three tiers directly).

**The decision is never tier 1's to make.** Which alerts need AI at all
(`rules.py`), what a Recommendation's label/confidence is (`recommendation_
agent.py`'s formula), and — critically — *which agents the Orchestrator
re-triggers* (`anomaly_rules.py`) are all pure, deterministic, unit-tested
functions. The LLM's only job anywhere in this codebase is turning an
already-decided fact into readable prose. This is what makes the whole
system testable without mocking an LLM in the hot path, and what makes
"no API key configured" a fully supported, first-class mode rather than a
degraded one.

---

## 5. The Orchestrator Pattern

`OrchestratorAgent` is a meta-agent, not a 12th data source — it reads
every other agent's latest output, decides (rule-based) whether anything
warrants an off-cycle re-run, self-heals any agent that's actually broken,
and asks the AI ladder to narrate the result.

```
every 15 min ──► gather snapshot (Price, sentiment, RiskSnapshot ×2,
                  sector momentum, recent Alert count, top Recommendation)
                        │
                        ▼
             anomaly_rules.py — 5 threshold detectors
             (price move >5% · risk jump ≥15pt · sentiment < -0.4 ·
              sector momentum ≥85/≤15 · ≥3 alerts in 15 min)
                        │
             ┌──────────┴──────────┐
             ▼                     ▼
     triggered agents        self-heal: any agent whose *last*
     .run_safe() only —      run genuinely failed also gets
     never a full sweep      retried (agent_last_ok() == False —
             │               not just "hasn't run in a while")
             ▼                     │
     claude_client.generate_briefing() ◄──┘
     (Haiku, or Sonnet if an anomaly fired)
                  │
                  ▼
       MarketBriefing row (append-only)
```

This is the same "rules decide, AI narrates" split as `AlertAgent`, applied
one level up — the Orchestrator's value is in deciding *what's worth
re-checking right now*, which is exactly the kind of decision that should
be fast, free, and deterministic rather than delegated to a model call.

**Self-healing, found live:** two overlapping runs of the same agent (a
manual `/api/refresh` racing that agent's own scheduled interval) used to
both fetch the same item and crash the second one on a SQLite `UNIQUE`
constraint — silently leaving that agent `inactive` until its next
scheduled cycle. `agents/base.py`'s `run_safe()` now holds a per-agent
lock so a second concurrent trigger skips cleanly instead of racing;
the orchestrator's self-heal step is the safety net for whatever still
manages to fail for a real reason (an external API outage, a genuine bug).

---

## 6. Honesty Constraints (deliberate absences)

Two things this app **does not do**, on purpose, documented here so they
aren't "rediscovered" as gaps later:

- **No Insider Trading agent, route, or panel.** SEC EDGAR only covers US
  filers (irrelevant to NSE-listed companies) and no free public API for
  NSE/BSE insider-trading disclosures exists. Rather than ship a
  permanently-empty panel, the agent was removed entirely.
- **RegulatoryAnnouncementAgent is not "SEBI filings."** There's no free
  API for SEBI's own EDIFAR system. The sidebar label says "SEBI Filings"
  (matching the product spec's naming) but the panel and data model are
  honest that this is NSE's own regulatory/compliance disclosure feed — the
  closest free real substitute, not a re-labeled placeholder. The same
  agent explicitly filters out insider-trading/SAST-adjacent categories
  before storage.
- **FII/DII per-stock "about to receive investment" data doesn't exist**
  anywhere free — it's forward-looking data nobody publishes. `FiiDiiAgent`
  is explicit that its per-stock signal is a *news mention*, not a
  confirmed transaction, alongside the real whole-market flow figure.

---

## 7. Deployment Topology

```
┌──────────────┐   git push   ┌───────────────────────────────────────┐
│  Developer    │─────────────►│  GitHub (private repo)                │
│  (local repo) │              │  .github/workflows/deploy.yml         │
└──────────────┘              └───────────────┬───────────────────────┘
                                               │ push/PR → main
                                   ┌───────────▼────────────┐
                                   │  GitHub Actions          │
                                   │  ┌─────────────────────┐│
                                   │  │ backend-tests (pytest)││
                                   │  ├─────────────────────┤│
                                   │  │ frontend-build (vite)││
                                   │  └──────────┬──────────┘│
                                   │   both pass, push to main│
                                   │  ┌──────────▼──────────┐│
                                   │  │ deploy (SSH)          ││
                                   │  └──────────┬──────────┘│
                                   └─────────────┼───────────┘
                                                 │ ssh (dedicated deploy key)
                          ┌──────────────────────▼───────────────────────┐
                          │  GCE VM (e2-small, asia-south1)               │
                          │  static external IP                          │
                          │  git reset --hard origin/main                │
                          │  docker compose up --build -d                │
                          │  ┌──────────────┐   ┌──────────────────────┐ │
                          │  │ backend       │   │ frontend              │ │
                          │  │ container     │   │ container             │ │
                          │  │ :8000         │   │ :5173 (serve -s dist) │ │
                          │  │ restart:      │   │ restart: unless-      │ │
                          │  │ unless-stopped│   │ stopped               │ │
                          │  └──────┬───────┘   └───────────────────────┘ │
                          │         │ named volume                        │
                          │  ┌──────▼───────┐                             │
                          │  │ backend_data  │  ← SQLite DB, survives     │
                          │  │ (Docker volume)│    rebuilds & redeploys    │
                          │  └──────────────┘                             │
                          └───────────────────────────────────────────────┘
```

**Why a persistent VM, not Cloud Run/serverless:** the scheduler
(APScheduler) runs *in-process*, inside the same Python process serving
HTTP requests. Cloud Run can freeze or scale a container to zero between
requests, which would silently pause every background agent — the app
would look fine on the next request but the data behind it would be stale.
A continuously-running VM is the simplest way to guarantee the scheduler
never stops, at the cost of paying for idle capacity rather than
true pay-per-request. (The Dockerfiles still respect an injected `$PORT`
env var for Cloud-Run compatibility if that tradeoff is ever revisited —
see `Dockerfile` comments in both `backend/` and `frontend/`.)

**Why `git reset --hard` on deploy is safe:** `backend/.env` is gitignored
and lives only on the VM's filesystem, never in a commit — a hard reset
touches only tracked files, so secrets and the running config survive every
deploy untouched.

**Why the Docker Compose project name matters:** the `backend_data` named
volume (and the SQLite DB inside it) is keyed by the Compose project name,
which defaults to the working directory's basename. As long as the
deployment directory is always named `StockMarketMonitor`, redeploys —
even a full directory swap, as happened when moving from a one-off `scp`
copy to a real git clone — keep reusing the same volume instead of starting
from an empty DB.

---

## 8. Tech Stack Summary

| Layer | Choice | Why |
|---|---|---|
| Backend framework | FastAPI + Uvicorn | Async-capable, typed, WebSocket support built in |
| ORM / DB | SQLAlchemy + SQLite (WAL mode, per-agent write locks) | Zero-ops persistence; one file, one Docker volume — no managed DB service to run for a single-instance app. WAL + a 30s busy_timeout + an in-process per-agent lock (§2/§5) handle the concurrent-writer pattern this scheduler creates, found live rather than anticipated upfront |
| Scheduling | APScheduler (in-process `BackgroundScheduler`) | No external queue/broker needed; ties agent liveness directly to the running process (§7 tradeoff) |
| Frontend framework | React 19 + TypeScript + Vite | Fast HMR dev loop, static typing across every API boundary |
| Charts | chart.js | Used for both the Market Overview index chart and the Calculators' Monte Carlo simulation chart — one charting dependency, not two |
| AI | Anthropic Claude (Haiku/Sonnet) → local Ollama → rule-based | Three-tier ladder, §4 — the app is fully functional with zero AI configured |
| Containerization | Docker + docker-compose | Two services (backend/frontend), one shared network, one named volume for the DB |
| Deployment | GCE VM (Compute Engine), asia-south1 | Persistent process for the in-process scheduler, §7 |
| CI/CD | GitHub Actions | Test → build → SSH deploy on push to `main`; see README §11 |

---

## 9. Where to Go Next

- **README.md** — full step-by-step walkthrough of every backend module,
  route, frontend page/component, setup instructions, environment
  variables, and the detailed GCP + CI/CD runbooks.
- **backend/app/agents/README.md** — per-agent data-source and design
  notes, one level more detailed than §2/§3 here.
- **EXPERIMENTS.md** — chronological log of what changed, why, what broke
  and how it was actually found/fixed, and how each change was verified.
