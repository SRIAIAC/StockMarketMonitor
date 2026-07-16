import datetime as dt
import logging
import threading
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.api.web_data import _do_refresh as _web_refresh
from app.api.analytics_data import _do_refresh as _analytics_refresh
from app.agents.base import last_run_for
from app.agents.market_agent import MarketAgent
from app.agents.news_agent import NewsAgent
from app.agents.social_agent import SocialAgent
from app.agents.econ_calendar_agent import EconCalendarAgent
from app.agents.alert_agent import AlertAgent
from app.agents.youtube_agent import YouTubeAgent
from app.agents.corporate_action_agent import CorporateActionAgent
from app.agents.regulatory_announcement_agent import RegulatoryAnnouncementAgent
from app.agents.risk_agent import RiskAgent
from app.agents.recommendation_agent import RecommendationAgent
from app.agents.orchestrator_agent import OrchestratorAgent
from app.agents.fii_dii_agent import FiiDiiAgent

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

IST = "Asia/Kolkata"

# Agents are module-level so run_all_agents() can reference them
_market_agent = MarketAgent()
_news_agent = NewsAgent()
_social_agent = SocialAgent()
_econ_agent = EconCalendarAgent()
_alert_agent = AlertAgent()
_youtube_agent = YouTubeAgent()
_corp_action_agent = CorporateActionAgent()
_regulatory_agent = RegulatoryAnnouncementAgent()
_risk_agent = RiskAgent()
_recommendation_agent = RecommendationAgent()
_orchestrator_agent = OrchestratorAgent()
_fii_dii_agent = FiiDiiAgent()


def run_all_agents() -> None:
    """Run all data agents sequentially (call in a thread to avoid blocking).

    Order matters for the tail end: risk and recommendation both read other
    agents' freshly-written rows (prices/sentiment/sector data), so they run
    after market/news/social and just before recommendation, which also
    reads the risk snapshot. OrchestratorAgent runs last of all so its
    briefing reflects this sweep's fresh data (and may itself re-trigger a
    subset of the agents above if it detects an anomaly).
    """
    logger.info(
        "Running all agents — market, news, social, econ, youtube, corp-action, "
        "regulatory, risk, recommendation, alert, fii-dii, orchestrator"
    )
    _market_agent.run_safe()
    _news_agent.run_safe()
    _social_agent.run_safe()
    _econ_agent.run_safe()
    _youtube_agent.run_safe()
    _corp_action_agent.run_safe()
    _regulatory_agent.run_safe()
    _risk_agent.run_safe()
    _recommendation_agent.run_safe()
    _alert_agent.run_safe()
    _fii_dii_agent.run_safe()
    _orchestrator_agent.run_safe()
    _web_refresh()
    logger.info("All agents finished")


_sweep_lock = threading.Lock()


def trigger_immediate_refresh() -> None:
    """Spawn a background thread to refresh all data without blocking the
    caller. Non-blocking lock: if a full sweep is already running (another
    manual refresh, the watchdog below, or a daily cron sweep), a new
    trigger is skipped rather than piling up a redundant duplicate — the
    per-agent locks in agents/base.py already make that safe, but there's
    no reason to spawn a whole extra thread that will just skip everything
    anyway."""
    if not _sweep_lock.acquire(blocking=False):
        logger.info("A full agent sweep is already in progress — skipping duplicate trigger")
        return

    def _run() -> None:
        try:
            run_all_agents()
        finally:
            _sweep_lock.release()

    t = threading.Thread(target=_run, daemon=True, name="immediate-refresh")
    t.start()


def start_scheduler() -> None:
    # ── Every 30-minute refresh for all live data ───────────────────────────
    scheduler.add_job(_market_agent.run_safe, "interval", minutes=30, id="market_30m")
    scheduler.add_job(_news_agent.run_safe,   "interval", minutes=30, id="news_30m")
    scheduler.add_job(_social_agent.run_safe, "interval", minutes=30, id="social_30m")
    scheduler.add_job(_corp_action_agent.run_safe,     "interval", minutes=30, id="corp_action_30m")
    scheduler.add_job(_regulatory_agent.run_safe,      "interval", minutes=30, id="regulatory_30m")
    scheduler.add_job(_risk_agent.run_safe,            "interval", minutes=30, id="risk_30m")
    scheduler.add_job(_recommendation_agent.run_safe,  "interval", minutes=30, id="recommendation_30m")
    scheduler.add_job(_alert_agent.run_safe,  "interval", minutes=30, id="alert_30m")
    scheduler.add_job(_web_refresh,           "interval", minutes=30, id="web_30m")
    # Orchestrator runs more often than the 30-min agent cadence so it can
    # catch and react to anomalies between full sweeps, not just piggyback
    # on them.
    scheduler.add_job(_orchestrator_agent.run_safe, "interval", minutes=15, id="orchestrator_15m")
    # Analytics (MF NAV, gold, IPOs) — every 30 minutes
    scheduler.add_job(_analytics_refresh,     "interval", minutes=30, id="analytics_30m")
    # YouTube channels post far less often than prices/news move — every 3h is plenty
    scheduler.add_job(_youtube_agent.run_safe, "interval", minutes=180, id="youtube_180m")
    # Econ calendar is a page scrape against a third-party site (Trading
    # Economics), not a JSON API — 3h keeps it a good citizen; macro releases
    # don't happen more often than that anyway.
    scheduler.add_job(_econ_agent.run_safe, "interval", minutes=180, id="econ_180m")
    # FII/DII daily figures only update once/trading-day and the news-derived
    # mentions don't need 30-min freshness either — same 3h cadence as
    # YouTube/econ calendar.
    scheduler.add_job(_fii_dii_agent.run_safe, "interval", minutes=180, id="fii_dii_180m")

    # ── Daily cron jobs (IST) ───────────────────────────────────────────────
    # 9:15 AM IST — NSE market opens; full data sweep
    scheduler.add_job(
        run_all_agents,
        CronTrigger(hour=9, minute=15, timezone=IST),
        id="daily_market_open",
        name="Daily market-open import",
        replace_existing=True,
    )
    # 3:45 PM IST — 15 min after NSE close; end-of-day capture
    scheduler.add_job(
        run_all_agents,
        CronTrigger(hour=15, minute=45, timezone=IST),
        id="daily_market_close",
        name="Daily market-close import",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "Scheduler started — most data refreshes every 30 min "
        "(YouTube and econ calendar every 3h) + daily at 09:15 and 15:45 IST"
    )


# ── Watchdog ─────────────────────────────────────────────────────────────
# Found live: after the host machine was suspended (laptop sleep, which
# pauses the Docker Desktop / WSL2 VM this container runs in) and resumed,
# APScheduler's own background thread went silent for ~22 hours — no agent
# fired on its interval at all — while the FastAPI web server stayed
# perfectly responsive the whole time (it's a separate thread). A fix that
# lived *inside* a scheduled job (e.g. extending OrchestratorAgent's
# self-heal step further) can't catch this: if the scheduler itself has
# stalled, that job never fires either. This watchdog is deliberately a
# plain daemon thread with its own sleep loop, not an APScheduler job, so
# it keeps checking regardless of whatever state APScheduler's internal
# thread is in.
_WATCHDOG_CHECK_SECONDS = 600  # every 10 minutes
_WATCHDOG_STALE_AFTER_MINUTES = 60  # 2x the shortest (30-min) agent cadence

# 30-minute-cadence agents only, used purely as canaries to judge "is the
# scheduler ticking at all" — not "is this specific agent healthy" (that's
# OrchestratorAgent's job, and it assumes the scheduler itself is running).
_CANARY_AGENTS = [
    "market", "news", "social", "corporate_action",
    "regulatory_announcement", "risk", "recommendation", "alert",
]


def _watchdog_check() -> None:
    """One staleness check — split out from `_watchdog_loop()`'s sleep loop
    so it's independently callable/testable without waiting on real time."""
    timestamps = [t for t in (last_run_for(name) for name in _CANARY_AGENTS) if t is not None]
    if not timestamps:
        return  # still starting up — nothing to judge yet
    stale_for = dt.datetime.utcnow() - max(timestamps)
    if stale_for >= dt.timedelta(minutes=_WATCHDOG_STALE_AFTER_MINUTES):
        logger.warning(
            "Watchdog: no 30-min-cadence agent has run in %s — the scheduler "
            "likely stalled (e.g. the host was suspended and didn't recover "
            "cleanly on wake). Triggering a catch-up sweep.",
            stale_for,
        )
        trigger_immediate_refresh()


def _watchdog_loop() -> None:
    while True:
        time.sleep(_WATCHDOG_CHECK_SECONDS)
        try:
            _watchdog_check()
        except Exception:
            logger.exception("Watchdog check failed")


def start_watchdog() -> None:
    t = threading.Thread(target=_watchdog_loop, daemon=True, name="scheduler-watchdog")
    t.start()
    logger.info(
        "Watchdog started — checks every %d min, self-triggers a catch-up sweep "
        "if no 30-min-cadence agent has run in over %d min",
        _WATCHDOG_CHECK_SECONDS // 60, _WATCHDOG_STALE_AFTER_MINUTES,
    )
