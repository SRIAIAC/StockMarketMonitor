"""Cheap, deterministic threshold rules. These run on every poll cycle and
decide which signals are worth escalating to the (paid) Claude API.
"""

from dataclasses import dataclass

PRICE_MOVE_THRESHOLD_PCT = 3.0
VOLUME_SPIKE_RATIO = 2.0
NEWS_SENTIMENT_THRESHOLD = -0.5
# StockTwits' like counts run 0-5 for these tickers (not Reddit's
# hundreds-of-upvotes scale) — tuned to that, not the old Reddit threshold.
# Lowered from 3 to 1: at 3, only ~1.8% of collected posts ever qualified,
# leaving the social-alerts panel empty almost every day.
SOCIAL_SCORE_THRESHOLD = 1


@dataclass
class Signal:
    ticker: str
    category: str  # market, news, social, economic
    reason: str
    severity: str  # info, warning, critical
    needs_ai: bool = False


def evaluate_price(ticker: str, pct_change: float, volume: int, avg_volume: int | None) -> Signal | None:
    volume_spike = bool(avg_volume) and volume > avg_volume * VOLUME_SPIKE_RATIO

    if abs(pct_change) >= PRICE_MOVE_THRESHOLD_PCT and volume_spike:
        return Signal(
            ticker=ticker,
            category="market",
            reason=f"{pct_change:+.2f}% move on {volume / max(avg_volume, 1):.1f}x avg volume",
            severity="critical",
            needs_ai=True,  # ambiguous/high-impact - worth a Claude read
        )
    if abs(pct_change) >= PRICE_MOVE_THRESHOLD_PCT:
        return Signal(
            ticker=ticker,
            category="market",
            reason=f"{pct_change:+.2f}% price move",
            severity="warning",
            needs_ai=False,
        )
    return None


def evaluate_news(ticker: str | None, title: str, sentiment: float) -> Signal | None:
    if ticker and sentiment <= NEWS_SENTIMENT_THRESHOLD:
        return Signal(
            ticker=ticker,
            category="news",
            reason=f"Negative headline sentiment ({sentiment:.2f}): {title}",
            severity="warning",
            needs_ai=True,
        )
    return None


def evaluate_social(ticker: str | None, title: str, score: int, sentiment: float) -> Signal | None:
    if ticker and score >= SOCIAL_SCORE_THRESHOLD:
        return Signal(
            ticker=ticker,
            category="social",
            reason=f"Trending on StockTwits (score {score}, sentiment {sentiment:.2f}): {title}",
            severity="info",
            needs_ai=score >= SOCIAL_SCORE_THRESHOLD * 2,
        )
    return None
