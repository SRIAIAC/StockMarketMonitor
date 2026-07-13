import datetime as dt
from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.config import settings
from app.models import Price, NewsItem, SocialPost, YouTubeInsight, YouTubeSentimentSummary, Recommendation
from app.api import web_data

router = APIRouter(prefix="/api")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _latest_prices(db: Session) -> list[Price]:
    subq = (
        db.query(Price.ticker, func.max(Price.fetched_at).label("max_fetched"))
        .group_by(Price.ticker)
        .subquery()
    )
    return (
        db.query(Price)
        .join(subq, (Price.ticker == subq.c.ticker) & (Price.fetched_at == subq.c.max_fetched))
        .all()
    )


def _utc_iso(ts: dt.datetime | None) -> str | None:
    return (ts.isoformat() + "Z") if ts else None


def _alpha_beta_for_watchlist(db: Session) -> dict[str, tuple[float, float]]:
    """Alpha/beta per ticker computed from our own periodically-fetched price
    history, using the equal-weighted watchlist average as the market proxy.

    There's no long-run NIFTY 50 history available to benchmark against —
    yfinance is blocked in this environment and NSE's own historical-data
    APIs (which would give per-symbol/index daily closes) return 503s to
    server-side requests, unlike its live snapshot APIs. So this uses the
    real intraday snapshots we do have (one row per ticker per scheduler
    cycle) and regresses each ticker's per-cycle return against the
    cross-sectional average return of the other tracked tickers.
    """
    tickers = settings.tickers
    rows = (
        db.query(Price.ticker, Price.price, Price.fetched_at)
        .filter(Price.ticker.in_(tickers))
        .order_by(Price.fetched_at.asc())
        .all()
    )
    if not rows:
        return {}

    # Bucket into 5-minute cycles so the (near-)simultaneous per-ticker
    # fetches within one scheduler run line up as a single cross-section.
    buckets: dict[dt.datetime, dict[str, float]] = defaultdict(dict)
    for ticker, price, fetched_at in rows:
        bucket_key = fetched_at.replace(second=0, microsecond=0)
        bucket_key -= dt.timedelta(minutes=bucket_key.minute % 5)
        buckets[bucket_key][ticker] = price

    cycles = [buckets[k] for k in sorted(buckets)]

    prev: dict[str, float] = {}
    paired_returns: dict[str, list[tuple[float, float]]] = defaultdict(list)

    for cycle in cycles:
        cycle_returns = {}
        for ticker, price in cycle.items():
            if ticker in prev and prev[ticker] > 0:
                cycle_returns[ticker] = (price - prev[ticker]) / prev[ticker]
        prev.update(cycle)
        # Require a broad enough cross-section for the average to be a
        # meaningful market proxy.
        if len(cycle_returns) >= max(5, len(tickers) // 2):
            market_return = sum(cycle_returns.values()) / len(cycle_returns)
            for ticker, r_i in cycle_returns.items():
                paired_returns[ticker].append((r_i, market_return))

    result: dict[str, tuple[float, float]] = {}
    for ticker, pairs in paired_returns.items():
        if len(pairs) < 5:
            continue
        n = len(pairs)
        mean_i = sum(p[0] for p in pairs) / n
        mean_m = sum(p[1] for p in pairs) / n
        var_m = sum((rm - mean_m) ** 2 for _, rm in pairs) / n
        if var_m == 0:
            continue
        cov = sum((ri - mean_i) * (rm - mean_m) for ri, rm in pairs) / n
        beta = cov / var_m
        alpha = (mean_i - beta * mean_m) * 100  # per-cycle excess return, as %
        result[ticker] = (round(alpha, 3), round(beta, 2))
    return result


@router.get("/watchlist")
def watchlist(db: Session = Depends(get_db)):
    prices = _latest_prices(db)
    by_ticker = {p.ticker: p for p in prices}
    alpha_beta = _alpha_beta_for_watchlist(db)

    # Build from DB first
    rows = []
    for ticker in settings.tickers:
        p = by_ticker.get(ticker)
        alpha, beta = alpha_beta.get(ticker, (None, None))
        rows.append({
            "ticker":     ticker,
            "sector":     p.sector if p else None,
            "price":      p.price if p else None,
            "pct_change": p.pct_change if p else None,
            "volume":     p.volume if p else None,
            "fetched_at": _utc_iso(p.fetched_at) if p else None,
            "alpha":      alpha,
            "beta":       beta,
        })

    # If DB has no price data at all, fall back to web cache
    if not any(r["price"] is not None for r in rows):
        cached = web_data.get("watchlist")
        if cached:
            return cached

    return rows


@router.get("/trending")
def trending(db: Session = Depends(get_db)):
    prices = sorted(_latest_prices(db), key=lambda p: abs(p.pct_change), reverse=True)[:10]
    if not prices:
        # Derive trending from web watchlist cache (highest absolute change)
        wl = web_data.get("watchlist")
        priced = [w for w in wl if w.get("pct_change") is not None]
        priced.sort(key=lambda w: abs(w["pct_change"]), reverse=True)
        return [
            {"ticker": w["ticker"], "pct_change": w["pct_change"], "volume": w.get("volume") or 0}
            for w in priced[:10]
        ]
    return [{"ticker": p.ticker, "pct_change": p.pct_change, "volume": p.volume} for p in prices]


@router.get("/youtube-insights")
def youtube_insights(db: Session = Depends(get_db), limit: int = Query(default=30, le=100)):
    rows = (
        db.query(YouTubeInsight)
        .filter(YouTubeInsight.ticker.isnot(None))
        .order_by(YouTubeInsight.published_at.desc().nullslast(), YouTubeInsight.fetched_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id":             r.id,
            "channel":        r.channel,
            "video_title":    r.video_title,
            "video_url":      r.video_url,
            "published_at":   _utc_iso(r.published_at),
            "language":       r.language,
            "ticker":         r.ticker,
            "recommendation": r.recommendation,
            "topics":         [t for t in r.topics.split(",") if t],
            "tone":           r.tone,
            "sentiment":      r.sentiment,
        }
        for r in rows
    ]


@router.get("/youtube-sentiment-summary")
def youtube_sentiment_summary(db: Session = Depends(get_db)):
    latest = (
        db.query(YouTubeSentimentSummary)
        .order_by(YouTubeSentimentSummary.computed_at.desc())
        .first()
    )
    if latest is None:
        return {"summary": None, "ai_generated": False, "computed_at": None}
    return {
        "summary": latest.summary,
        "ai_generated": bool(latest.ai_generated),
        "computed_at": _utc_iso(latest.computed_at),
    }


@router.get("/movers")
def movers(db: Session = Depends(get_db)):
    prices = _latest_prices(db)
    priced = [p for p in prices if p.pct_change is not None]

    if not priced:
        wl = web_data.get("watchlist")
        priced_wl = [w for w in wl if w.get("pct_change") is not None]
        gainers = sorted(priced_wl, key=lambda w: w["pct_change"], reverse=True)[:5]
        losers  = sorted(priced_wl, key=lambda w: w["pct_change"])[:5]
        def _wrow(w):
            return {
                "ticker": w["ticker"], "price": w.get("price"),
                "pct_change": w["pct_change"], "volume": w.get("volume"),
                "sector": w.get("sector"),
            }
        return {"gainers": [_wrow(w) for w in gainers], "losers": [_wrow(w) for w in losers]}

    gainers = sorted(priced, key=lambda p: p.pct_change, reverse=True)[:5]
    losers  = sorted(priced, key=lambda p: p.pct_change)[:5]

    def _row(p: Price) -> dict:
        return {
            "ticker": p.ticker, "price": p.price,
            "pct_change": p.pct_change, "volume": p.volume, "sector": p.sector,
        }
    return {"gainers": [_row(p) for p in gainers], "losers": [_row(p) for p in losers]}


@router.get("/sentiment-heatmap")
def sentiment_heatmap(db: Session = Depends(get_db)):
    since = dt.datetime.utcnow() - dt.timedelta(hours=24)
    by_ticker: dict[str, list[float]] = defaultdict(list)

    for n in db.query(NewsItem).filter(NewsItem.fetched_at >= since, NewsItem.ticker.isnot(None)):
        if n.sentiment is not None:
            by_ticker[n.ticker].append(n.sentiment)
    for s in db.query(SocialPost).filter(SocialPost.fetched_at >= since, SocialPost.ticker.isnot(None)):
        if s.sentiment is not None:
            by_ticker[s.ticker].append(s.sentiment)

    if not by_ticker:
        return web_data.get("sentiment")

    return [
        {"ticker": ticker, "avg_sentiment": sum(sc) / len(sc), "sample_size": len(sc)}
        for ticker, sc in by_ticker.items()
    ]


@router.get("/news")
def news(db: Session = Depends(get_db), limit: int = Query(default=25, le=100)):
    since = dt.datetime.utcnow() - dt.timedelta(hours=24)
    items = (
        db.query(NewsItem)
        .filter(NewsItem.fetched_at >= since)
        .order_by(NewsItem.fetched_at.desc())
        .limit(limit)
        .all()
    )

    if not items:
        cached = web_data.get("news")
        return cached[:limit] if cached else []

    return [
        {
            "id":           n.id,
            "ticker":       n.ticker,
            "source":       n.source,
            "title":        n.title,
            "url":          n.url,
            "sentiment":    n.sentiment,
            "published_at": _utc_iso(n.published_at),
            "fetched_at":   _utc_iso(n.fetched_at),
        }
        for n in items
    ]


@router.get("/recommendations")
def recommendations(db: Session = Depends(get_db)):
    """Agent-backed Buy/Hold/Sell picks — computed by RecommendationAgent
    (agents/recommendation_agent.py) on its own schedule, this route just
    reads the latest run's rows. Shape: {picks: [...], computed_at}.

    Distinct from `/api/market-recommendations` (routes_market.py), which is
    a whole-market, web-scraped, unscored signal surfaced separately on the
    AI Recommendations page rather than merged into this scored pipeline.
    """
    rows = (
        db.query(Recommendation)
        .order_by(Recommendation.computed_at.desc(), func.abs(Recommendation.score).desc())
        .all()
    )
    if not rows:
        return {"picks": [], "computed_at": None}

    computed_at = rows[0].computed_at
    latest = [r for r in rows if r.computed_at == computed_at]
    latest.sort(key=lambda r: abs(r.score), reverse=True)

    return {
        "picks": [
            {
                "ticker": r.ticker, "label": r.label, "confidence": r.confidence,
                "score": r.score, "price": r.price, "pct_change": r.pct_change,
                "sector": r.sector, "sentiment": r.sentiment, "reason": r.reason,
                "ai_reason": r.ai_reason,
            }
            for r in latest
        ],
        "computed_at": _utc_iso(computed_at),
    }
