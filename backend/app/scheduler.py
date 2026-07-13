import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.api.web_data import _do_refresh as _web_refresh
from app.api.analytics_data import _do_refresh as _analytics_refresh
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


def trigger_immediate_refresh() -> None:
    """Spawn a background thread to refresh all data without blocking the caller."""
    t = threading.Thread(target=run_all_agents, daemon=True, name="immediate-refresh")
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
