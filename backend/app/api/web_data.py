"""Web-data cache for all dashboard panels.

Fetches live data from NSE / yfinance / Google News RSS when the DB agents
haven't imported anything yet (or as a real-time supplement).  Refreshes
every CACHE_TTL minutes in a background daemon thread.
"""

import concurrent.futures
import datetime as dt
import logging
import re
import threading
from collections import defaultdict

import feedparser
import httpx

logger = logging.getLogger(__name__)

# ── Moneycontrol price API (same codes as MarketAgent) ───────────────────────
_MC_CODES: dict[str, str] = {
    "RELIANCE.NS": "RI",    "HDFCBANK.NS": "HDF01",  "TCS.NS": "TCS",
    "ICICIBANK.NS": "ICI02","BHARTIARTL.NS": "BTV",   "CGPOWER.NS": "CG",
    "DIXON.NS": "DT07",     "COFORGE.NS": "NII02",    "PERSISTENT.NS": "PS15",
    "MPHASIS.NS": "BFL",    "CDSL.NS": "CDS",         "IEX.NS": "IEE",
    "CYIENT.NS": "IE07",    "GLENMARK.NS": "GP08",    "BIRLACORPN.NS": "BC07",
}
_MC_URL = "https://priceapi.moneycontrol.com/pricefeed/nse/equitycash/{code}"
_MC_HEADERS = {"User-Agent": "Mozilla/5.0 StockMarketMonitor/0.1"}

CACHE_TTL = dt.timedelta(minutes=15)

# ── Watchlist tickers (must match settings.tickers) ─────────────────────────
WATCHLIST = [
    "RELIANCE.NS", "HDFCBANK.NS", "TCS.NS", "ICICIBANK.NS", "BHARTIARTL.NS",
    "CGPOWER.NS",  "DIXON.NS",    "COFORGE.NS", "PERSISTENT.NS", "MPHASIS.NS",
    "CDSL.NS",     "IEX.NS",      "CYIENT.NS",  "GLENMARK.NS",   "BIRLACORPN.NS",
]

# Predefined sector map (avoids slow yfinance .info calls)
_SECTOR: dict[str, str] = {
    "RELIANCE.NS":   "Energy",
    "HDFCBANK.NS":   "Banking",
    "TCS.NS":        "Information Technology",
    "ICICIBANK.NS":  "Banking",
    "BHARTIARTL.NS": "Telecom",
    "CGPOWER.NS":    "Industrials",
    "DIXON.NS":      "Consumer Electronics",
    "COFORGE.NS":    "Information Technology",
    "PERSISTENT.NS": "Information Technology",
    "MPHASIS.NS":    "Information Technology",
    "CDSL.NS":       "Financial Services",
    "IEX.NS":        "Energy",
    "CYIENT.NS":     "Information Technology",
    "GLENMARK.NS":   "Pharmaceuticals",
    "BIRLACORPN.NS": "Cement",
}

# Company name → ticker, used for news ticker extraction
_COMPANY_KEYWORDS: list[tuple[str, str]] = [
    ("RELIANCE", "RELIANCE.NS"), ("RIL", "RELIANCE.NS"),
    ("HDFCBANK", "HDFCBANK.NS"), ("HDFC BANK", "HDFCBANK.NS"), ("HDFC", "HDFCBANK.NS"),
    ("TCS", "TCS.NS"), ("TATA CONSULTANCY", "TCS.NS"),
    ("ICICI BANK", "ICICIBANK.NS"), ("ICICIBANK", "ICICIBANK.NS"), ("ICICI", "ICICIBANK.NS"),
    ("AIRTEL", "BHARTIARTL.NS"), ("BHARTIARTL", "BHARTIARTL.NS"), ("BHARTI", "BHARTIARTL.NS"),
    ("CG POWER", "CGPOWER.NS"), ("CGPOWER", "CGPOWER.NS"),
    ("DIXON", "DIXON.NS"),
    ("COFORGE", "COFORGE.NS"),
    ("PERSISTENT", "PERSISTENT.NS"),
    ("MPHASIS", "MPHASIS.NS"),
    ("CDSL", "CDSL.NS"),
    ("IEX", "IEX.NS"),
    ("CYIENT", "CYIENT.NS"),
    ("GLENMARK", "GLENMARK.NS"),
    ("BIRLA CORP", "BIRLACORPN.NS"), ("BIRLACORPN", "BIRLACORPN.NS"),
    # Broad market references → no ticker
    ("NIFTY", None), ("SENSEX", None), ("NSE", None), ("BSE", None),
]

# Google News RSS feeds for market-wide news
_MARKET_FEEDS = [
    "https://news.google.com/rss/search?q=NSE+India+stock+market+today&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=NIFTY+50+BSE+Sensex+India+shares&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=Indian+stock+market+Reliance+TCS+HDFC+ICICI&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=NSE+India+quarterly+results+earnings+2026&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=India+midcap+smallcap+technology+pharma+stocks&hl=en-IN&gl=IN&ceid=IN:en",
]

# Global-market feeds — kept separate from _MARKET_FEEDS so _fetch_news can
# tag them with a distinct "International" source label (see NewsPanel.tsx,
# which splits the Indian vs. international columns on that label).
_GLOBAL_FEEDS = [
    "https://news.google.com/rss/search?q=Wall+Street+Dow+Jones+S%26P+500+Nasdaq&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=Federal+Reserve+interest+rates+global+markets&hl=en-US&gl=US&ceid=US:en",
]

# Ticker-specific RSS feeds for watchlist stocks
_TICKER_FEEDS = [
    ("RELIANCE.NS",   "https://news.google.com/rss/search?q=Reliance+Industries+NSE+stock&hl=en-IN&gl=IN&ceid=IN:en"),
    ("HDFCBANK.NS",   "https://news.google.com/rss/search?q=HDFC+Bank+NSE+stock&hl=en-IN&gl=IN&ceid=IN:en"),
    ("TCS.NS",        "https://news.google.com/rss/search?q=Tata+Consultancy+Services+TCS+NSE&hl=en-IN&gl=IN&ceid=IN:en"),
    ("ICICIBANK.NS",  "https://news.google.com/rss/search?q=ICICI+Bank+NSE+stock&hl=en-IN&gl=IN&ceid=IN:en"),
    ("BHARTIARTL.NS", "https://news.google.com/rss/search?q=Bharti+Airtel+NSE+telecom&hl=en-IN&gl=IN&ceid=IN:en"),
    ("CGPOWER.NS",    "https://news.google.com/rss/search?q=CG+Power+NSE+stock&hl=en-IN&gl=IN&ceid=IN:en"),
    ("DIXON.NS",      "https://news.google.com/rss/search?q=Dixon+Technologies+NSE&hl=en-IN&gl=IN&ceid=IN:en"),
    ("COFORGE.NS",    "https://news.google.com/rss/search?q=Coforge+NSE+IT+stock&hl=en-IN&gl=IN&ceid=IN:en"),
    ("PERSISTENT.NS", "https://news.google.com/rss/search?q=Persistent+Systems+NSE&hl=en-IN&gl=IN&ceid=IN:en"),
    ("MPHASIS.NS",    "https://news.google.com/rss/search?q=Mphasis+NSE+IT+stock&hl=en-IN&gl=IN&ceid=IN:en"),
    ("CDSL.NS",       "https://news.google.com/rss/search?q=CDSL+Central+Depository+NSE&hl=en-IN&gl=IN&ceid=IN:en"),
    ("IEX.NS",        "https://news.google.com/rss/search?q=IEX+India+Energy+Exchange+NSE&hl=en-IN&gl=IN&ceid=IN:en"),
    ("CYIENT.NS",     "https://news.google.com/rss/search?q=Cyient+NSE+engineering+stock&hl=en-IN&gl=IN&ceid=IN:en"),
    ("GLENMARK.NS",   "https://news.google.com/rss/search?q=Glenmark+Pharmaceuticals+NSE&hl=en-IN&gl=IN&ceid=IN:en"),
    ("BIRLACORPN.NS", "https://news.google.com/rss/search?q=Birla+Corporation+cement+NSE&hl=en-IN&gl=IN&ceid=IN:en"),
]

# ── Module-level cache ───────────────────────────────────────────────────────
_lock = threading.Lock()
_cache: dict = {
    "watchlist":  [],
    "news":       [],
    "sentiment":  [],
    "alerts":     [],
    "ts":         None,
    "refreshing": False,
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _score_sentiment(text: str) -> float:
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        return round(SentimentIntensityAnalyzer().polarity_scores(text)["compound"], 3)
    except Exception:
        pos = {"rally","gain","profit","growth","bullish","surge","jump","beat","strong","positive","upgrade"}
        neg = {"fall","drop","loss","decline","bearish","crash","miss","weak","negative","downgrade","concern","slump"}
        words = set(text.lower().split())
        p, n = len(words & pos), len(words & neg)
        return round((p - n) / max(p + n, 1), 2)


def _extract_ticker(text: str) -> str | None:
    upper = text.upper()
    for keyword, ticker in _COMPANY_KEYWORDS:
        if keyword in upper:
            return ticker  # may be None for market-wide terms
    return None


def _parse_pub_date(raw: str) -> str | None:
    try:
        import email.utils
        ts = email.utils.parsedate_to_datetime(raw)
        return ts.utctimetuple() and (
            dt.datetime(*ts.utctimetuple()[:6]).isoformat() + "Z"
        )
    except Exception:
        return None


# ── Fetch functions ──────────────────────────────────────────────────────────

def _fetch_watchlist() -> list[dict]:
    """Fetch live prices for all 15 watchlist stocks via Moneycontrol price API."""
    now_iso = dt.datetime.utcnow().isoformat() + "Z"

    def _one(ticker: str, client: httpx.Client) -> dict:
        base = {
            "ticker": ticker, "sector": _SECTOR.get(ticker),
            "price": None, "pct_change": None, "volume": None,
            "fetched_at": now_iso,
        }
        code = _MC_CODES.get(ticker)
        if not code:
            return base
        try:
            resp    = client.get(_MC_URL.format(code=code))
            payload = resp.json().get("data", {})
            price   = _to_float(payload.get("pricecurrent"))
            prev    = _to_float(payload.get("priceprevclose"))
            vol     = int(_to_float(payload.get("VOL")) or 0)
            if price and prev and prev != 0:
                base["price"]      = round(price, 2)
                base["pct_change"] = round((price - prev) / prev * 100, 2)
                base["volume"]     = vol
                if not base["sector"]:
                    base["sector"] = payload.get("newSubsector") or payload.get("SC_SUBSEC")
        except Exception as e:
            logger.debug("Moneycontrol quote failed for %s: %s", ticker, e)
        return base

    rows: list[dict] = []
    with httpx.Client(headers=_MC_HEADERS, timeout=10) as client:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futs = {pool.submit(_one, t, client): t for t in WATCHLIST}
            for fut in concurrent.futures.as_completed(futs, timeout=25):
                try:
                    rows.append(fut.result())
                except Exception:
                    pass

    order = {t: i for i, t in enumerate(WATCHLIST)}
    rows.sort(key=lambda r: order.get(r["ticker"], 99))
    return rows


def _to_float(v) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _fetch_news() -> list[dict]:
    now_iso = dt.datetime.utcnow().isoformat() + "Z"
    items: list[dict] = []
    seen: set[str] = set()

    def _parse_feed(url: str, default_ticker: str | None = None, source: str = "Google News") -> list[dict]:
        results = []
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:
                title = entry.get("title", "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                ticker = default_ticker or _extract_ticker(title)
                results.append({
                    "id":           0,  # filled in below
                    "ticker":       ticker,
                    "source":       source,
                    "title":        title,
                    "url":          entry.get("link", ""),
                    "sentiment":    _score_sentiment(title),
                    "published_at": _parse_pub_date(entry.get("published", "")) or now_iso,
                    "fetched_at":   now_iso,
                })
        except Exception as e:
            logger.warning("RSS failed (%s): %s", url, e)
        return results

    # Parallel: market-wide feeds + per-ticker feeds + international feeds.
    # "International" in the source label is what NewsPanel.tsx keys off of
    # to split the Indian vs. international columns.
    all_feeds = (
        [(url, None, "Google News") for url in _MARKET_FEEDS]
        + [(url, ticker, "Google News") for ticker, url in _TICKER_FEEDS]
        + [(url, None, "Google News International Markets") for url in _GLOBAL_FEEDS]
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(_parse_feed, url, ticker, source) for url, ticker, source in all_feeds]
        for fut in concurrent.futures.as_completed(futs, timeout=30):
            try:
                items.extend(fut.result())
            except Exception:
                pass

    # Sort by published_at desc, de-dup by title, assign IDs
    items.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    seen_titles: set[str] = set()
    final: list[dict] = []
    for i, item in enumerate(items, 1):
        if item["title"] in seen_titles:
            continue
        seen_titles.add(item["title"])
        item["id"] = i
        final.append(item)
        if len(final) == 30:
            break
    return final


def _build_sentiment(news_items: list[dict]) -> list[dict]:
    by_ticker: dict[str, list[float]] = defaultdict(list)
    for item in news_items:
        if item["ticker"] and item["sentiment"] is not None:
            by_ticker[item["ticker"]].append(item["sentiment"])
    return [
        {
            "ticker":        ticker,
            "avg_sentiment": round(sum(scores) / len(scores), 3),
            "sample_size":   len(scores),
        }
        for ticker, scores in by_ticker.items()
        if ticker  # skip None keys
    ]


def _price_reason(pct: float, direction: str, headline: str | None) -> str:
    """Build a ≤100-word reason for a price-based alert."""
    name = "declined" if direction == "down" else "gained"
    base = (
        f"Stock {name} {abs(pct):.2f}% intraday. "
        f"{'Selling pressure exceeded buyers across the session.' if direction == 'down' else 'Strong buying interest drove the price higher.'}"
    )
    if headline:
        # truncate headline so total stays under 100 words
        return f"{base} Latest news: {headline[:120]}."
    return f"{base} No specific news catalyst found in tracked feeds."


def _generate_alerts(watchlist: list[dict], news_items: list[dict]) -> list[dict]:
    now_iso = dt.datetime.utcnow().isoformat() + "Z"
    alerts: list[dict] = []

    # ticker → top headline
    ticker_headline: dict[str, str] = {}
    for item in news_items:
        t = item.get("ticker")
        if t and t not in ticker_headline and item.get("title"):
            ticker_headline[t] = item["title"]

    # Price-based alerts
    for w in watchlist:
        pct    = w.get("pct_change")
        price  = w.get("price")
        ticker = w["ticker"]
        if pct is None:
            continue
        headline = ticker_headline.get(ticker)
        if pct <= -5:
            alerts.append({
                "id": len(alerts) + 1, "ticker": ticker, "category": "price",
                "severity": "critical",
                "message": f"Sharp fall {pct:+.2f}% today — LTP ₹{price:.2f}" if price else f"Sharp fall {pct:+.2f}% today",
                "reason": _price_reason(pct, "down", headline),
                "used_ai": False, "created_at": now_iso,
            })
        elif pct <= -3:
            alerts.append({
                "id": len(alerts) + 1, "ticker": ticker, "category": "price",
                "severity": "warning",
                "message": f"Significant decline {pct:+.2f}% today",
                "reason": _price_reason(pct, "down", headline),
                "used_ai": False, "created_at": now_iso,
            })
        elif pct >= 5:
            alerts.append({
                "id": len(alerts) + 1, "ticker": ticker, "category": "price",
                "severity": "warning",
                "message": f"Sharp rally {pct:+.2f}% today — LTP ₹{price:.2f}" if price else f"Sharp rally {pct:+.2f}% today",
                "reason": _price_reason(pct, "up", headline),
                "used_ai": False, "created_at": now_iso,
            })
        elif pct >= 3:
            alerts.append({
                "id": len(alerts) + 1, "ticker": ticker, "category": "price",
                "severity": "info",
                "message": f"Strong gain {pct:+.2f}% today",
                "reason": _price_reason(pct, "up", headline),
                "used_ai": False, "created_at": now_iso,
            })

    # Sentiment-based alerts
    by_ticker: dict[str, list[float]] = defaultdict(list)
    by_ticker_headlines: dict[str, list[str]] = defaultdict(list)
    for item in news_items:
        if item["ticker"] and item["sentiment"] is not None:
            by_ticker[item["ticker"]].append(item["sentiment"])
            if item.get("title"):
                by_ticker_headlines[item["ticker"]].append(item["title"])
    for ticker, scores in by_ticker.items():
        avg = sum(scores) / len(scores)
        headlines = by_ticker_headlines[ticker]
        top = headlines[0] if headlines else None
        if avg < -0.4 and len(scores) >= 2:
            reason = (
                f"Negative tone detected across {len(scores)} recent articles. "
                + (f"Top story: {top[:120]}." if top else "No specific headline available.")
            )
            alerts.append({
                "id": len(alerts) + 1, "ticker": ticker, "category": "sentiment",
                "severity": "warning",
                "message": f"Negative news sentiment ({avg:+.2f}) across {len(scores)} articles",
                "reason": reason, "used_ai": False, "created_at": now_iso,
            })
        elif avg > 0.4 and len(scores) >= 2:
            reason = (
                f"Positive tone detected across {len(scores)} recent articles. "
                + (f"Top story: {top[:120]}." if top else "No specific headline available.")
            )
            alerts.append({
                "id": len(alerts) + 1, "ticker": ticker, "category": "sentiment",
                "severity": "info",
                "message": f"Positive news sentiment ({avg:+.2f}) across {len(scores)} articles",
                "reason": reason, "used_ai": False, "created_at": now_iso,
            })

    return alerts


# ── Cache refresh ────────────────────────────────────────────────────────────

def _do_refresh() -> None:
    logger.info("web_data: refreshing all panels from web…")
    try:
        watchlist  = _fetch_watchlist()
        news       = _fetch_news()
        sentiment  = _build_sentiment(news)
        alerts     = _generate_alerts(watchlist, news)

        with _lock:
            _cache["watchlist"]  = watchlist
            _cache["news"]       = news
            _cache["sentiment"]  = sentiment
            _cache["alerts"]     = alerts
            _cache["ts"]         = dt.datetime.utcnow()
            _cache["refreshing"] = False
        logger.info(
            "web_data: done — %d watchlist, %d news, %d alerts",
            len(watchlist), len(news), len(alerts),
        )
    except Exception:
        logger.exception("web_data: refresh crashed")
        with _lock:
            _cache["refreshing"] = False


def ensure_fresh() -> None:
    """Trigger a background refresh if the cache is absent or stale."""
    with _lock:
        ts        = _cache["ts"]
        already   = _cache["refreshing"]
    stale = ts is None or (dt.datetime.utcnow() - ts) > CACHE_TTL
    if stale and not already:
        with _lock:
            _cache["refreshing"] = True
        threading.Thread(target=_do_refresh, daemon=True).start()


def get(key: str):
    ensure_fresh()
    with _lock:
        return _cache.get(key, [])
