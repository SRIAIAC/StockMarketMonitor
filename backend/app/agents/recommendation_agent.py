"""Watchlist-scoped Buy/Hold/Sell recommendations with a confidence score.

Extends the composite-score idea that used to live inline in
`routes_dashboard.recommendations()` (price momentum + sentiment + volume)
with two more inputs now that dedicated agents produce them:
- sector rotation momentum (routes_market's extended `/api/sectors`)
- a risk dampener from the latest RiskAgent snapshot

Kept watchlist-scoped (not whole-market) for v1: this is the one place in
the pipeline with rich per-ticker price + sentiment history to score
against. `routes_market.py`'s separate `/api/market-recommendations`
(web-scraped, whole-market) remains a distinct, less-structured signal —
surfaced on its own section of the recommendations page rather than merged
into this scored pipeline.

AI-generated one-line reasons are requested only for the tickers that will
actually be displayed (top picks), not the full watchlist, to bound Claude
spend — see `analysis/claude_client.recommend_reason()`.
"""

import datetime as dt
import logging
from collections import defaultdict

from sqlalchemy import func

from app.agents.base import BaseAgent
from app.analysis import claude_client
from app.config import settings
from app.models import NewsItem, Price, Recommendation, RiskSnapshot, SocialPost

logger = logging.getLogger(__name__)

# How many top-ranked picks (by |score|) get an AI-generated reason and are
# actually surfaced — kept small since only the top of each side is shown.
_AI_REASON_LIMIT = 5

_RISK_PENALTY = {"Low": 0.0, "Moderate": 0.07, "High": 0.15}

_BUY_THRESHOLD = 0.5
_SELL_THRESHOLD = -0.5


def _latest_prices(session) -> list[Price]:
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


def _sentiment_by_ticker(session) -> dict[str, list[float]]:
    # 30 days, not 24h — this feeds both the score and (via `reason`, below)
    # the AI-generated one-line explanation on top picks, and AI-facing
    # news/social analysis should draw on the last month, not just today.
    since = dt.datetime.utcnow() - dt.timedelta(days=30)
    out: dict[str, list[float]] = defaultdict(list)
    for n in session.query(NewsItem).filter(
        NewsItem.fetched_at >= since, NewsItem.ticker.isnot(None), NewsItem.sentiment.isnot(None)
    ):
        out[n.ticker].append(n.sentiment)
    for s in session.query(SocialPost).filter(
        SocialPost.fetched_at >= since, SocialPost.ticker.isnot(None), SocialPost.sentiment.isnot(None)
    ):
        out[s.ticker].append(s.sentiment)
    return out


def _sector_momentum_by_name() -> dict[str, float]:
    """Best-effort sector momentum lookup — a network hiccup here shouldn't
    fail the whole recommendation run, just drop that term to 0."""
    try:
        from app.api.routes_market import _fetch_nse_sectors  # local import: avoid a hard route<->agent coupling at module load time

        rows = _fetch_nse_sectors() or []
        return {r["sector"]: r["momentum_score"] for r in rows}
    except Exception:
        logger.warning("Sector momentum lookup failed, scoring without it")
        return {}


def _latest_risk_label(session) -> str:
    latest = session.query(RiskSnapshot).order_by(RiskSnapshot.computed_at.desc()).first()
    return latest.risk_label if latest else "Moderate"


class RecommendationAgent(BaseAgent):
    name = "recommendation"

    def run(self) -> None:
        session = self.session()
        try:
            prices = [p for p in _latest_prices(session) if p.pct_change is not None]
            if not prices:
                logger.info("No priced watchlist rows yet, skipping recommendation run")
                return

            sentiment_by_ticker = _sentiment_by_ticker(session)
            sector_momentum = _sector_momentum_by_name()
            risk_penalty = _RISK_PENALTY.get(_latest_risk_label(session), 0.07)

            scored: list[dict] = []
            for p in prices:
                scores_list = sentiment_by_ticker.get(p.ticker, [])
                sentiment = sum(scores_list) / len(scores_list) if scores_list else 0.0
                vol_ratio = (p.volume / p.avg_volume) if p.avg_volume else 1.0
                # Sector momentum_score is 0-100 (50=neutral) — recenter to
                # -1..+1 to match the other terms' scale before weighting.
                sector_term = ((sector_momentum.get(p.sector, 50.0)) - 50.0) / 50.0

                raw_score = (
                    (p.pct_change / 5.0) * 0.5
                    + sentiment * 0.3
                    + min(vol_ratio - 1, 1.5) * 0.2
                    + sector_term * 0.15
                )
                score = raw_score * (1 - risk_penalty)

                if score >= _BUY_THRESHOLD:
                    label = "Buy"
                elif score <= _SELL_THRESHOLD:
                    label = "Sell"
                else:
                    label = "Hold"
                confidence = round(50 + min(abs(score), 1.0) * 49, 1)

                reasons = []
                reasons.append(f"{p.pct_change:+.2f}% today")
                if sentiment > 0.1:
                    reasons.append("positive sentiment")
                elif sentiment < -0.1:
                    reasons.append("negative sentiment")
                if p.avg_volume and p.volume > p.avg_volume * 1.5:
                    reasons.append(f"{p.volume / p.avg_volume:.1f}x avg volume")
                if p.sector and p.sector in sector_momentum:
                    if sector_term > 0.1:
                        reasons.append(f"{p.sector} sector rotating in")
                    elif sector_term < -0.1:
                        reasons.append(f"{p.sector} sector rotating out")
                reason = ", ".join(reasons) or "Neutral"

                scored.append({
                    "ticker": p.ticker, "label": label, "confidence": confidence,
                    "score": round(score, 4), "price": p.price, "pct_change": p.pct_change,
                    "sector": p.sector, "sentiment": round(sentiment, 2), "reason": reason,
                })

            scored.sort(key=lambda x: abs(x["score"]), reverse=True)

            for item in scored[:_AI_REASON_LIMIT]:
                item["ai_reason"] = claude_client.recommend_reason(
                    item["ticker"], item["label"], item["reason"]
                )
            for item in scored[_AI_REASON_LIMIT:]:
                item["ai_reason"] = None

            session.query(Recommendation).delete()
            now = dt.datetime.utcnow()
            for item in scored:
                session.add(Recommendation(
                    ticker=item["ticker"], label=item["label"], confidence=item["confidence"],
                    score=item["score"], price=item["price"], pct_change=item["pct_change"],
                    sector=item["sector"], sentiment=item["sentiment"], reason=item["reason"],
                    ai_reason=item["ai_reason"], computed_at=now,
                ))
            session.commit()
        finally:
            session.close()
