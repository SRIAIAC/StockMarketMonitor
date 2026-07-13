"""Cross-agent orchestrator: reads every other agent's latest output,
runs deterministic anomaly detection (analysis/anomaly_rules.py) to decide
whether specific agents should re-run off-cycle, and asks Claude to narrate
the current state into a short market briefing.

Design note (mirrors AlertAgent's "rules first, AI only for explanation"
split — see agents/README.md): the *decision* of which agents to
re-trigger is entirely rule-based, never left to the LLM. Claude's only
role here is turning already-decided structured facts into readable
prose — the same reason `rules.py` decides severity/needs_ai before
`claude_client.py` is ever called. This keeps the consequential action
(spending extra scrape/API budget on an off-cycle agent run) fast, free,
deterministic, and testable; only the narrative text depends on an LLM
call succeeding.

Runs independently every 15 minutes (scheduler.py) — more often than the
other agents' 30-minute cadence, so it can catch and react to anomalies
between full sweeps — and once more at the tail of every `run_all_agents()`
sweep so a fresh briefing follows immediately after market-open/close.

The *narrated* content is whole-trading-day, not per-15-minute-cycle,
even though the run cadence itself stays 15 minutes: alert counts in the
briefing text reflect "today so far", not just this tick, so the summary
reads as a coherent daily picture rather than a fragmented series of
narrow snapshots. The anomaly-detection rules underneath are the
exception — those stay on short, real windows (15 min for alert bursts,
1h for a sentiment cliff) since a genuinely sudden event has to be
compared against a recent baseline, not averaged into a whole day.
"""

import datetime as dt
import logging

from sqlalchemy import func

from app.agents.base import BaseAgent
from app.analysis import claude_client
from app.analysis.anomaly_rules import (
    Anomaly,
    detect_alert_burst,
    detect_price_anomaly,
    detect_risk_spike,
    detect_sector_shock,
    detect_sentiment_cliff,
    merge_triggered_agents,
)
from app.config import settings
from app.models import Alert, MarketBriefing, NewsItem, Price, Recommendation, RiskSnapshot, SocialPost

logger = logging.getLogger(__name__)

# Same IST-day-boundary pattern as routes_market.py's _day_start_utc — kept
# as a local copy rather than importing a private route helper, same
# reasoning as _sector_snapshot()'s lazy import below (agents shouldn't
# hard-couple to route modules at import time).
_IST_OFFSET = dt.timedelta(hours=5, minutes=30)


def _today_start_utc() -> dt.datetime:
    now_ist = dt.datetime.utcnow() + _IST_OFFSET
    day_start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start_ist - _IST_OFFSET

# name (as used in anomaly_rules' agents_to_trigger lists) -> agent class.
# Imported lazily inside run() to sidestep any import-order edge cases at
# module load time (scheduler.py imports this module too).
def _agent_classes() -> dict[str, type[BaseAgent]]:
    from app.agents.alert_agent import AlertAgent
    from app.agents.news_agent import NewsAgent
    from app.agents.recommendation_agent import RecommendationAgent
    from app.agents.risk_agent import RiskAgent
    from app.agents.social_agent import SocialAgent

    return {
        "news": NewsAgent,
        "social": SocialAgent,
        "alert": AlertAgent,
        "risk": RiskAgent,
        "recommendation": RecommendationAgent,
    }


def _latest_watchlist_prices(session) -> list[Price]:
    tickers = settings.tickers
    subq = (
        session.query(Price.ticker, func.max(Price.fetched_at).label("max_fetched"))
        .filter(Price.ticker.in_(tickers))
        .group_by(Price.ticker)
        .subquery()
    )
    return (
        session.query(Price)
        .join(subq, (Price.ticker == subq.c.ticker) & (Price.fetched_at == subq.c.max_fetched))
        .all()
    )


def _market_wide_sentiment(session, hours: int) -> tuple[float, int]:
    since = dt.datetime.utcnow() - dt.timedelta(hours=hours)
    scores = [
        r.sentiment for r in session.query(NewsItem.sentiment)
        .filter(NewsItem.fetched_at >= since, NewsItem.sentiment.isnot(None)).all()
    ] + [
        r.sentiment for r in session.query(SocialPost.sentiment)
        .filter(SocialPost.fetched_at >= since, SocialPost.sentiment.isnot(None)).all()
    ]
    if not scores:
        return 0.0, 0
    return sum(scores) / len(scores), len(scores)


def _sector_snapshot() -> list[dict]:
    try:
        from app.api.routes_market import _fetch_nse_sectors
        return _fetch_nse_sectors() or []
    except Exception:
        logger.warning("Orchestrator: sector snapshot unavailable this run")
        return []


class OrchestratorAgent(BaseAgent):
    name = "orchestrator"

    def run(self) -> None:
        session = self.session()
        try:
            prices = _latest_watchlist_prices(session)
            priced = [p for p in prices if p.pct_change is not None]
            advances = sum(1 for p in priced if p.pct_change >= 0)
            declines = len(priced) - advances
            top_mover = max(priced, key=lambda p: abs(p.pct_change)) if priced else None

            # Two different windows, deliberately: the anomaly rule below needs
            # a short window to catch a genuine sudden cliff (diluted to
            # meaninglessness by a month of averaging), while the AI-narrated
            # briefing context should reflect the fuller last-30-days picture
            # per product direction — "any AI analysis should be on news from
            # the last month, whether social media or market news."
            avg_sentiment_1h, sentiment_samples_1h = _market_wide_sentiment(session, hours=1)
            avg_sentiment_30d, sentiment_samples_30d = _market_wide_sentiment(session, hours=24 * 30)

            risk_rows = (
                session.query(RiskSnapshot).order_by(RiskSnapshot.computed_at.desc()).limit(2).all()
            )
            current_risk = risk_rows[0] if risk_rows else None
            previous_risk = risk_rows[1] if len(risk_rows) > 1 else None

            sectors = _sector_snapshot()

            # Two different windows, same reasoning as the sentiment split
            # above: the anomaly rule needs a short window to catch a
            # genuine burst of alerts happening *right now* (a day-long
            # count would never spike sharply enough to trigger), while the
            # briefing narration should reflect the whole trading day so
            # far — "whole day rather than interval cycles" — not just
            # whatever happened to fire in this particular 15-minute tick.
            since_burst = dt.datetime.utcnow() - dt.timedelta(minutes=15)
            burst_alert_count = (
                session.query(Alert)
                .filter(Alert.created_at >= since_burst, Alert.severity.in_(["warning", "critical"]))
                .count()
            )
            todays_alert_count = (
                session.query(Alert)
                .filter(Alert.created_at >= _today_start_utc(), Alert.severity.in_(["warning", "critical"]))
                .count()
            )

            top_pick = (
                session.query(Recommendation)
                .order_by(Recommendation.computed_at.desc(), func.abs(Recommendation.score).desc())
                .first()
            )

            # ── Rule-based anomaly detection — this decides what re-runs, not Claude ──
            anomalies: list[Anomaly] = []
            price_anomaly = detect_price_anomaly([(p.ticker, p.pct_change) for p in priced])
            if price_anomaly:
                anomalies.append(price_anomaly)
            if current_risk:
                risk_anomaly = detect_risk_spike(
                    current_risk.risk_score, previous_risk.risk_score if previous_risk else None
                )
                if risk_anomaly:
                    anomalies.append(risk_anomaly)
            sentiment_anomaly = detect_sentiment_cliff(avg_sentiment_1h, sentiment_samples_1h)
            if sentiment_anomaly:
                anomalies.append(sentiment_anomaly)
            sector_anomaly = detect_sector_shock(sectors)
            if sector_anomaly:
                anomalies.append(sector_anomaly)
            alert_anomaly = detect_alert_burst(burst_alert_count)
            if alert_anomaly:
                anomalies.append(alert_anomaly)

            triggered = merge_triggered_agents(anomalies)
            classes = _agent_classes()
            for name in triggered:
                agent_cls = classes.get(name)
                if agent_cls is None:
                    continue
                logger.info("Orchestrator: anomaly detected, re-triggering %s", name)
                agent_cls().run_safe()

            # ── Briefing context (facts only — Claude narrates, doesn't decide) ──
            context_lines = [
                f"Watchlist breadth: {advances} advancing, {declines} declining, out of {len(priced)} tracked.",
            ]
            if top_mover:
                context_lines.append(
                    f"Biggest mover: {top_mover.ticker.replace('.NS','')} {top_mover.pct_change:+.2f}%."
                )
            if sentiment_samples_30d:
                context_lines.append(
                    f"News/social sentiment (last 30 days, {sentiment_samples_30d} items): "
                    f"{avg_sentiment_30d:.2f} (-1..+1 scale)."
                )
            if current_risk:
                context_lines.append(
                    f"Risk score: {current_risk.risk_score:.0f}/100 ({current_risk.risk_label}), "
                    f"India VIX {current_risk.india_vix}."
                )
            if sectors:
                top_sector = max(sectors, key=lambda s: s.get("momentum_score", 50))
                context_lines.append(
                    f"Strongest sector momentum: {top_sector['sector']} ({top_sector['momentum_score']:.0f}/100)."
                )
            if top_pick:
                context_lines.append(
                    f"Top-ranked recommendation: {top_pick.ticker.replace('.NS','')} — {top_pick.label} "
                    f"({top_pick.confidence:.0f}% confidence)."
                )
            if todays_alert_count:
                context_lines.append(f"{todays_alert_count} warning/critical alerts so far today.")
            if anomalies:
                context_lines.append("Anomalies detected this cycle: " + "; ".join(a.description for a in anomalies) + ".")
            else:
                context_lines.append("No anomalies detected this cycle — conditions are within normal range.")

            context_text = "\n".join(context_lines)

            ai_result = claude_client.generate_briefing(context_text, has_anomalies=bool(anomalies))
            if ai_result:
                headline, summary = ai_result
                ai_generated = True
            else:
                headline, summary = self._fallback_briefing(
                    advances, declines, len(priced), current_risk, anomalies, top_pick, todays_alert_count
                )
                ai_generated = False

            session.add(
                MarketBriefing(
                    headline=headline,
                    summary=summary,
                    anomalies="; ".join(a.description for a in anomalies),
                    agents_triggered=", ".join(triggered),
                    ai_generated=1 if ai_generated else 0,
                    computed_at=dt.datetime.utcnow(),
                )
            )
            session.commit()
        finally:
            session.close()

    @staticmethod
    def _fallback_briefing(advances, declines, total, risk, anomalies, top_pick, todays_alert_count) -> tuple[str, str]:
        """Deterministic templated briefing — used whenever neither Claude
        nor Ollama is available. Never a blank panel.

        This previously dropped `todays_alert_count` entirely and always
        said "detected this cycle" regardless of the whole-day framing
        change made to the AI-narrated `context_text` — meaning anyone
        without an ANTHROPIC_API_KEY (or, now, without Ollama reachable
        either) never actually saw the whole-day framing at all, since
        this template is what real users see far more often than the
        AI-generated text. Fixed to match: alert count is phrased as
        "so far today", not per-cycle.
        """
        risk_bit = f"Risk is {risk.risk_label.lower()} ({risk.risk_score:.0f}/100)." if risk else ""
        alerts_bit = f"{todays_alert_count} warning/critical alert(s) so far today." if todays_alert_count else ""
        anomaly_bit = (
            f"{len(anomalies)} anomaly(ies) flagged this run." if anomalies else "No anomalies flagged this run."
        )
        pick_bit = (
            f" Top pick: {top_pick.ticker.replace('.NS','')} ({top_pick.label})." if top_pick else ""
        )
        headline = f"{advances}/{total} advancing" + (f" · {len(anomalies)} anomaly" if anomalies else "")
        bits = " ".join(b for b in (risk_bit, alerts_bit, anomaly_bit) if b)
        summary = f"{advances} of {total} tracked stocks are advancing, {declines} declining. {bits}{pick_bit}".strip()
        return headline, summary
