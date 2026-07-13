import datetime as dt
import logging

from app.agents.base import BaseAgent
from app.analysis import rules
from app.analysis.claude_client import triage_and_explain
from app.api.ws import broadcast_alert
from app.models import Price, NewsItem, SocialPost, Alert

logger = logging.getLogger(__name__)

# Widened from 30 to 60: AlertAgent and SocialAgent both run on independent
# 30-minute interval jobs, so their timing can drift (scheduler jitter,
# restarts). SocialAgent often fetches zero *new* posts in a given cycle —
# when a qualifying post does land, a lookback exactly equal to the run
# interval left too small a margin, letting posts age out of the window
# before AlertAgent ever got a chance to see them (confirmed live: real
# score>=1 posts existed but no social alert had fired in over a day).
# Doubling it gives a full extra cycle of buffer without loosening any
# actual alert criteria — thresholds are unchanged, and the duplicate-alert
# check below uses the same window so re-alerting is, if anything, less
# frequent, not more.
LOOKBACK_MINUTES = 60


class AlertAgent(BaseAgent):
    name = "alert"

    def run(self) -> None:
        session = self.session()
        try:
            since = dt.datetime.utcnow() - dt.timedelta(minutes=LOOKBACK_MINUTES)
            signals = []

            for price in session.query(Price).filter(Price.fetched_at >= since).all():
                signal = rules.evaluate_price(price.ticker, price.pct_change, price.volume, price.avg_volume)
                if signal:
                    signals.append(signal)

            for news in session.query(NewsItem).filter(NewsItem.fetched_at >= since).all():
                if news.sentiment is None:
                    continue
                signal = rules.evaluate_news(news.ticker, news.title, news.sentiment)
                if signal:
                    signals.append(signal)

            for post in session.query(SocialPost).filter(SocialPost.fetched_at >= since).all():
                if post.sentiment is None:
                    continue
                signal = rules.evaluate_social(post.ticker, post.title, post.score, post.sentiment)
                if signal:
                    signals.append(signal)

            for signal in signals:
                duplicate = (
                    session.query(Alert)
                    .filter(
                        Alert.ticker == signal.ticker,
                        Alert.category == signal.category,
                        Alert.created_at >= since,
                    )
                    .first()
                )
                if duplicate:
                    continue

                message = signal.reason
                used_ai = False
                if signal.needs_ai:
                    message, _ = triage_and_explain(signal.ticker, signal.category, signal.reason)
                    used_ai = True

                alert = Alert(
                    ticker=signal.ticker,
                    category=signal.category,
                    severity=signal.severity,
                    message=message,
                    source_used_ai=1 if used_ai else 0,
                    created_at=dt.datetime.utcnow(),
                )
                session.add(alert)
                session.flush()

                broadcast_alert(
                    {
                        "id": alert.id,
                        "ticker": alert.ticker,
                        "category": alert.category,
                        "severity": alert.severity,
                        "message": alert.message,
                        "created_at": alert.created_at.isoformat(),
                    }
                )

            session.commit()
        finally:
            session.close()
