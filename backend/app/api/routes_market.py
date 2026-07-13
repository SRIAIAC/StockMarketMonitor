"""Market-wide movers (NSE India live API / NIFTY 50 fallback) and web-sourced
buy/sell recommendations (Google News RSS + DuckDuckGo HTML, yfinance enrichment).

Results are kept in a module-level cache refreshed every 15 minutes by a
background thread so route handlers always return instantly."""

import concurrent.futures
import datetime as dt
import logging
import re
import threading

import feedparser
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Price
from app.api.nse_client import nse_get as _nse_get

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ── NSE India live API ──────────────────────────────────────────────────────
_NSE_GAINERS = "/api/live-analysis-variations?index=gainers"
_NSE_LOSERS  = "/api/live-analysis-variations?index=loosers"
_NSE_ALL_INDICES = "/api/allIndices"

# Curated set of the major, non-overlapping NSE sector indices (whole-market
# breadth, not just our 50-stock watchlist). NSE's own "SECTORAL INDICES"
# grouping is missing NIFTY BANK (filed under a different category) and
# includes near-duplicate sub-variants (e.g. both REALTY and REITS & REALTY),
# so this is an explicit allowlist rather than a filter on NSE's own key.
SECTOR_INDEX_MAP: dict[str, str] = {
    "NIFTY BANK":              "Banking",
    "NIFTY IT":                "IT",
    "NIFTY AUTO":              "Auto",
    "NIFTY PHARMA":            "Pharma",
    "NIFTY FMCG":              "FMCG",
    "NIFTY METAL":             "Metal",
    "NIFTY ENERGY":            "Energy",
    "NIFTY REALTY":            "Realty",
    "NIFTY MEDIA":             "Media",
    "NIFTY CONSUMER DURABLES": "Consumer Durables",
    "NIFTY OIL & GAS":         "Oil & Gas",
    "NIFTY CEMENT":            "Cement",
    "NIFTY CHEMICALS":         "Chemicals",
    "NIFTY HEALTHCARE INDEX":  "Healthcare",
}

# ── NIFTY 50 tickers (yfinance fallback) ────────────────────────────────────
NIFTY_50 = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","BHARTIARTL.NS","ICICIBANK.NS",
    "INFOSYS.NS","SBIN.NS","HINDUNILVR.NS","ITC.NS","WIPRO.NS",
    "KOTAKBANK.NS","LT.NS","MARUTI.NS","BAJFINANCE.NS","AXISBANK.NS",
    "ASIANPAINT.NS","NTPC.NS","POWERGRID.NS","SUNPHARMA.NS","ADANIPORTS.NS",
    "BAJAJFINSV.NS","ULTRACEMCO.NS","HCLTECH.NS","NESTLEIND.NS","TITAN.NS",
    "TECHM.NS","TATACONSUM.NS","COALINDIA.NS","GRASIM.NS","DRREDDY.NS",
    "HEROMOTOCO.NS","BPCL.NS","EICHERMOT.NS","SHRIRAMFIN.NS","CIPLA.NS",
    "BRITANNIA.NS","DIVISLAB.NS","APOLLOHOSP.NS","TRENT.NS","HINDALCO.NS",
    "JSWSTEEL.NS","TATASTEEL.NS","ONGC.NS","INDUSINDBK.NS","M&M.NS",
    "ADANIENT.NS","LTIM.NS","TATAMOTORS.NS","BEL.NS","ZOMATO.NS",
]

# ── Known NSE symbols for text extraction ───────────────────────────────────
_NSE_SYMBOLS: set[str] = {
    "RELIANCE","TCS","HDFCBANK","BHARTIARTL","ICICIBANK","INFOSYS","SBIN",
    "HINDUNILVR","ITC","WIPRO","KOTAKBANK","LT","MARUTI","BAJFINANCE",
    "AXISBANK","ASIANPAINT","NTPC","POWERGRID","SUNPHARMA","ADANIPORTS",
    "BAJAJFINSV","ULTRACEMCO","HCLTECH","NESTLEIND","TITAN","TECHM",
    "TATACONSUM","COALINDIA","GRASIM","DRREDDY","HEROMOTOCO","BPCL",
    "EICHERMOT","SHRIRAMFIN","CIPLA","BRITANNIA","DIVISLAB","APOLLOHOSP",
    "TRENT","HINDALCO","JSWSTEEL","TATASTEEL","ONGC","INDUSINDBK",
    "ADANIENT","LTIM","TATAMOTORS","BEL","ZOMATO","PERSISTENT","COFORGE",
    "MPHASIS","CDSL","IEX","CGPOWER","DIXON","CYIENT","GLENMARK","BIRLACORPN",
    "DMART","HDFCLIFE","SBILIFE","ICICIGI","TATACHEM","PIDILITIND","HAVELLS",
    "VOLTAS","GODREJCP","BERGEPAINT","SIEMENS","ABB","CONCOR","OFSS","LUPIN",
    "AUROPHARMA","TORNTPHARM","ALKEM","MFSL","LICI","NYKAA",
    "MOTHERSON","CUMMINSIND","ESCORTS","MUTHOOTFIN","CHOLAFIN","TATAPOWER",
    "ADANIGREEN","ADANITRANS","JINDALSTEL","SAIL","ETERNAL","JIOFIN",
    "BAJAJ-AUTO","SHREECEM","HDFCAMC","BANDHANBNK","IDFCFIRSTB","FEDERALBNK",
    "INDIANB","BANKBARODA","PNB","CANBK","UNIONBANK","CENTRALBK",
}

_NOISE: set[str] = {
    "NSE","BSE","IPO","FII","DII","GDP","CPI","RBI","ETF","NAV","SIP","NFO",
    "LTP","EPS","MCX","SEBI","YES","ONE","BIG","NEW","TOP","KEY","NET","ALL",
    "THE","AND","FOR","WITH","FROM","WILL","PDF","URL","HTTP","COM","WWW",
    "INC","LTD","PVT","BUY","SELL","ARE","THEY","HAVE","THIS","THAT","RSI",
    "CEO","CFO","CTO","AGM","EGM","MOU","LOI","FPO","OFS","NCD","SGB","SGX",
}

# ── Google News RSS feeds for recommendations ───────────────────────────────
_REC_FEEDS = [
    (
        "buy",
        "https://news.google.com/rss/search?q=NSE+stocks+buy+recommendation+analyst+target+price&hl=en-IN&gl=IN&ceid=IN:en",
    ),
    (
        "sell",
        "https://news.google.com/rss/search?q=NSE+stocks+sell+reduce+exit+recommendation&hl=en-IN&gl=IN&ceid=IN:en",
    ),
    (
        "buy",
        "https://news.google.com/rss/search?q=India+stock+market+top+picks+analyst+2026&hl=en-IN&gl=IN&ceid=IN:en",
    ),
    (
        "sell",
        "https://news.google.com/rss/search?q=India+stock+market+bearish+caution+downgrade&hl=en-IN&gl=IN&ceid=IN:en",
    ),
]

# ── Module-level caches ──────────────────────────────────────────────────────
_CACHE_TTL = dt.timedelta(minutes=15)

_movers_cache: dict = {"data": None, "ts": None, "refreshing": False}
_movers_lock  = threading.Lock()

_rec_cache: dict = {"data": None, "ts": None, "refreshing": False}
_rec_lock   = threading.Lock()

_sectors_cache: dict = {"data": None, "ts": None, "refreshing": False}
_sectors_lock  = threading.Lock()


# ── helpers ──────────────────────────────────────────────────────────────────

def _f(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _extract_symbols(text: str) -> list[str]:
    words = re.findall(r'\b([A-Z][A-Z0-9&\-]{1,11})\b', text.upper())
    seen: set[str] = set()
    out: list[str] = []
    for w in words:
        w = w.strip("-&")
        if w in _NSE_SYMBOLS and w not in _NOISE and w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _enrich_prices(symbols: list[str]) -> dict[str, dict]:
    """Parallel yfinance fast_info lookups capped at 10 workers / 20 s."""
    if not symbols:
        return {}
    try:
        import yfinance as yf
        out: dict[str, dict] = {}

        def _fetch(sym: str) -> tuple[str, dict] | None:
            try:
                fi = yf.Ticker(f"{sym}.NS").fast_info
                lp   = fi.get("lastPrice")
                prev = fi.get("previousClose")
                pct  = round((lp - prev) / prev * 100, 2) if (lp and prev and prev != 0) else None
                return sym, {"price": lp, "pct_change": pct, "sector": None}
            except Exception:
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futs = [pool.submit(_fetch, s) for s in symbols]
            for fut in concurrent.futures.as_completed(futs, timeout=20):
                try:
                    res = fut.result()
                    if res:
                        out[res[0]] = res[1]
                except Exception:
                    pass
        return out
    except Exception:
        logger.exception("yfinance price enrichment failed")
        return {}


# ── NSE India live movers ────────────────────────────────────────────────────

def _parse_nse_index_data(payload: dict | list, limit: int = 5) -> list[dict]:
    """Extract top movers from NSE live-analysis-variations response.

    The response has the shape:
        {"legends": [...], "NIFTY": {"data": [...], "timestamp": "..."}, "BANKNIFTY": {...}}
    Each item in the "data" list has fields: symbol, ltp, perChange, trade_quantity.
    """
    items: list = []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        # Preferred: nested index dict with "data" list
        for key in ("NIFTY", "BANKNIFTY", "NIFTYNEXT50", "FOSec", "allSec", "SecGtr20"):
            val = payload.get(key)
            if isinstance(val, dict) and isinstance(val.get("data"), list):
                items = val["data"]
                break
            if isinstance(val, list) and val and isinstance(val[0], dict):
                items = val
                break
        else:
            # Flat dict with "data" key
            if isinstance(payload.get("data"), list):
                items = payload["data"]

    seen: set[str] = set()
    rows: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sym = (item.get("symbol") or item.get("Symbol") or "").strip()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        price = _f(item.get("ltp") or item.get("lastPrice") or item.get("LTP"))
        pct   = _f(item.get("perChange") or item.get("net_price") or item.get("pChange"))
        vol   = int(_f(item.get("trade_quantity") or item.get("tradedQuantity") or item.get("volume") or 0) or 0)
        name  = item.get("companyName") or sym
        sector = item.get("industry") or item.get("sector")
        if price is not None:
            rows.append({
                "ticker": f"{sym}.NS", "symbol": sym, "name": name,
                "price": round(price, 2), "pct_change": round(pct or 0.0, 2),
                "volume": vol, "sector": sector, "source": "NSE India live",
            })
        if len(rows) == limit:
            break
    return rows


def _fetch_nse_all_indices() -> list[dict]:
    """Raw NSE allIndices payload (all index rows, not just our sectoral
    allowlist) — shared by sector breadth, India VIX, and headline index
    lookups so each doesn't warm its own separate session."""
    payload = _nse_get(_NSE_ALL_INDICES)
    if not isinstance(payload, dict):
        return []
    return payload.get("data", []) or []


# Sector Rotation momentum: blends today's move (immediacy) with the
# trailing-30-day move (real rotation, not single-day noise) into one 0-100
# score.
#
# Recalibrated after live NSE sectoral data showed the original ±8% scale
# saturating in practice: 30-day sector moves routinely run ±10-22% (Realty
# was +21.77% 30d the day this was checked), so at the old 65% 30d weight
# almost any strongly-rotating sector pinned at the 0/100 clamp regardless
# of that day's actual move — the score looked permanently frozen at the
# extremes instead of tracking live rotation. Widened the scale to match
# that real dispersion and shifted weight slightly toward today's move,
# since this is a live dashboard widget, not an end-of-month report.
_MOMENTUM_TODAY_WEIGHT = 0.40
_MOMENTUM_30D_WEIGHT = 0.60
_MOMENTUM_SCALE_PCT = 20.0  # a ±20% blended move maps to the 0/100 extremes
_TREND_DEAD_ZONE = 3.0      # momentum_score within 3 of the neutral midpoint (50) reads as "neutral"


def _momentum_score(pct_today: float, pct_30d: float | None) -> float:
    blended = _MOMENTUM_TODAY_WEIGHT * pct_today + _MOMENTUM_30D_WEIGHT * (pct_30d or pct_today)
    score = 50 + (blended / _MOMENTUM_SCALE_PCT) * 50
    return round(max(0.0, min(100.0, score)), 1)


def _fetch_nse_sectors() -> list[dict] | None:
    """Whole-market sector breadth + rotation momentum from NSE's sectoral
    indices — each index tracks its own basket of constituents, not just
    our 50-stock watchlist. Returns None on failure."""
    data = _fetch_nse_all_indices()
    if not data:
        return None

    rows: list[dict] = []
    for item in data:
        display = SECTOR_INDEX_MAP.get(item.get("index", ""))
        if not display:
            continue
        pct = _f(item.get("percentChange"))
        if pct is None:
            continue
        advances = item.get("advances") or 0
        declines = item.get("declines") or 0
        pct_30d = _f(item.get("perChange30d"))
        momentum = _momentum_score(pct, pct_30d)
        trend = "up" if momentum > 50 + _TREND_DEAD_ZONE else "down" if momentum < 50 - _TREND_DEAD_ZONE else "neutral"
        rows.append({
            "sector": display,
            "avg_pct_change": round(pct, 2),
            "count": int(advances) + int(declines),
            "momentum_score": momentum,
            "trend": trend,
        })
    return rows or None


def _fetch_nse_movers() -> dict | None:
    """NSE India gainers + losers via the shared session helper. Returns None on failure."""
    g_data = _nse_get(_NSE_GAINERS)
    l_data = _nse_get(_NSE_LOSERS)
    if g_data is None and l_data is None:
        return None

    gainers = _parse_nse_index_data(g_data) if g_data is not None else []
    losers  = _parse_nse_index_data(l_data) if l_data is not None else []
    if gainers or losers:
        return {"gainers": gainers, "losers": losers, "source": "NSE India live"}
    return None


def _fetch_yfinance_movers() -> dict:
    """Parallel fast_info calls for NIFTY 50. Capped at 10 workers, 30 s total."""
    try:
        import yfinance as yf

        def _one(sym: str) -> dict | None:
            try:
                fi    = yf.Ticker(sym).fast_info
                price = fi.get("lastPrice")
                prev  = fi.get("previousClose")
                if not price or not prev or prev == 0:
                    return None
                pct  = (price - prev) / prev * 100
                base = sym.replace(".NS", "")
                return {
                    "ticker": sym, "symbol": base, "name": base,
                    "price": round(price, 2), "pct_change": round(pct, 2),
                    "volume": int(fi.get("lastVolume") or 0),
                    "sector": None, "source": "NIFTY 50 / yfinance",
                }
            except Exception:
                return None

        rows: list[dict] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futs = [pool.submit(_one, sym) for sym in NIFTY_50]
            for fut in concurrent.futures.as_completed(futs, timeout=30):
                try:
                    r = fut.result()
                    if r:
                        rows.append(r)
                except Exception:
                    pass

        if not rows:
            return {"gainers": [], "losers": [], "source": "unavailable"}
        rows.sort(key=lambda r: r["pct_change"], reverse=True)
        return {
            "gainers": rows[:5],
            "losers":  list(reversed(rows[-5:])),
            "source":  "NIFTY 50 / yfinance",
        }
    except Exception:
        logger.exception("yfinance NIFTY 50 fallback failed")
        return {"gainers": [], "losers": [], "source": "unavailable"}


def _do_refresh_movers() -> None:
    """Background worker: fetch movers and write to cache."""
    try:
        result = _fetch_nse_movers()
        if not result or (not result["gainers"] and not result["losers"]):
            result = _fetch_yfinance_movers()
    except Exception:
        logger.exception("movers refresh crashed")
        result = {"gainers": [], "losers": [], "source": "unavailable"}
    with _movers_lock:
        _movers_cache["data"] = result
        _movers_cache["ts"]   = dt.datetime.utcnow()
        _movers_cache["refreshing"] = False


def _ensure_movers_fresh() -> None:
    """Trigger a background refresh if cache is absent or stale."""
    with _movers_lock:
        ts = _movers_cache["ts"]
        already = _movers_cache["refreshing"]
    stale = ts is None or (dt.datetime.utcnow() - ts) > _CACHE_TTL
    if stale and not already:
        with _movers_lock:
            _movers_cache["refreshing"] = True
        threading.Thread(target=_do_refresh_movers, daemon=True).start()


def _do_refresh_sectors() -> None:
    """Background worker: fetch NSE sector indices and write to cache."""
    try:
        result = _fetch_nse_sectors() or []
    except Exception:
        logger.exception("sectors refresh crashed")
        result = []
    with _sectors_lock:
        _sectors_cache["data"] = result
        _sectors_cache["ts"]   = dt.datetime.utcnow()
        _sectors_cache["refreshing"] = False


def _ensure_sectors_fresh() -> None:
    """Trigger a background refresh if cache is absent or stale."""
    with _sectors_lock:
        ts = _sectors_cache["ts"]
        already = _sectors_cache["refreshing"]
    stale = ts is None or (dt.datetime.utcnow() - ts) > _CACHE_TTL
    if stale and not already:
        with _sectors_lock:
            _sectors_cache["refreshing"] = True
        threading.Thread(target=_do_refresh_sectors, daemon=True).start()


# ── Web recommendations ──────────────────────────────────────────────────────

def _ddg_search(query: str, max_results: int = 8) -> list[dict]:
    try:
        resp = httpx.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query, "kl": "in-en"},
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                ),
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=15,
            follow_redirects=True,
        )
        clean = lambda s: re.sub(r"<[^>]+>", "", s).strip()
        titles   = re.findall(r'class="result__a"[^>]*>(.*?)</a>', resp.text, re.DOTALL)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', resp.text, re.DOTALL)
        results = []
        for i, title in enumerate(titles[:max_results]):
            results.append({
                "title": clean(title),
                "body":  clean(snippets[i]) if i < len(snippets) else "",
                "href":  "",
            })
        return results
    except Exception as e:
        logger.warning("DDG HTML search failed: %s", e)
        return []


# Google News RSS search results aren't sorted by recency — a highly
# "relevant" match can be months old. These recommendations should reflect
# current analyst calls, not a stale sell rating from long before this
# session's watchlist even existed, so anything older than this is dropped.
_REC_MAX_AGE_DAYS = 30


def _rss_recommendations() -> tuple[list[dict], list[dict]]:
    buy_articles:  list[dict] = []
    sell_articles: list[dict] = []
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=_REC_MAX_AGE_DAYS)
    for signal, url in _REC_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:20]:
                published = entry.get("published_parsed")
                if published and dt.datetime(*published[:6]) < cutoff:
                    continue
                bucket = buy_articles if signal == "buy" else sell_articles
                bucket.append({
                    "title": entry.get("title", ""),
                    "href":  entry.get("link", ""),
                    "body":  entry.get("title", ""),
                })
        except Exception as e:
            logger.warning("RSS feed failed (%s): %s", url, e)
    return buy_articles, sell_articles


def _pick_stocks(articles: list[dict], limit: int = 5) -> list[dict]:
    seen: set[str] = set()
    picks: list[dict] = []
    for art in articles:
        text = f"{art.get('title','')} {art.get('body','')}"
        for sym in _extract_symbols(text):
            if sym in seen:
                continue
            seen.add(sym)
            picks.append({
                "symbol": sym, "ticker": f"{sym}.NS", "name": sym,
                "price": None, "pct_change": None, "sector": None,
                "reason": art.get("title", "Analyst recommendation"),
                "source_url": art.get("href", ""),
            })
            if len(picks) >= limit:
                return picks
    return picks


def _pad_with_nifty50_recs(buys: list[dict], sells: list[dict]) -> tuple[list[dict], list[dict]]:
    """Fill buy/sell slots using cached movers data, a fresh NSE India call,
    or (last resort) parallel yfinance calls."""
    with _movers_lock:
        cached = _movers_cache.get("data")

    if cached and (cached.get("gainers") or cached.get("losers")):
        nifty_rows = cached["gainers"] + cached["losers"]
    else:
        # NSE India directly, same as _fetch_nse_movers — yfinance is
        # unreliable in this environment (frequently blocked/rate-limited)
        # and was leaving this panel empty whenever the movers cache hadn't
        # warmed up yet.
        fresh = _fetch_nse_movers()
        if fresh and (fresh.get("gainers") or fresh.get("losers")):
            nifty_rows = fresh["gainers"] + fresh["losers"]
        else:
            try:
                import yfinance as yf
                def _one(sym: str) -> dict | None:
                    try:
                        fi    = yf.Ticker(sym).fast_info
                        price = fi.get("lastPrice")
                        prev  = fi.get("previousClose")
                        if not price or not prev or prev == 0:
                            return None
                        pct  = (price - prev) / prev * 100
                        base = sym.replace(".NS", "")
                        return {
                            "symbol": base, "ticker": sym, "name": base,
                            "price": round(price, 2), "pct_change": round(pct, 2),
                            "sector": None,
                            "reason": f"{pct:+.2f}% intraday — NIFTY 50 momentum",
                            "source_url": "",
                        }
                    except Exception:
                        return None

                nifty_rows = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
                    futs = [pool.submit(_one, sym) for sym in NIFTY_50]
                    for fut in concurrent.futures.as_completed(futs, timeout=25):
                        try:
                            r = fut.result()
                            if r:
                                nifty_rows.append(r)
                        except Exception:
                            pass
                nifty_rows.sort(key=lambda r: r["pct_change"], reverse=True)
            except Exception:
                logger.exception("NIFTY 50 pad fallback failed")
                return buys[:3], sells[:3]

    buy_syms  = {s["symbol"] for s in buys}
    sell_syms = {s["symbol"] for s in sells}
    for r in nifty_rows:
        if len(buys) >= 3:
            break
        if r["symbol"] not in buy_syms:
            buy_syms.add(r["symbol"])
            reason = r.get("reason") or f"{r.get('pct_change', 0):+.2f}% intraday — NIFTY 50 momentum"
            buys.append({**r, "reason": reason})
    for r in reversed(nifty_rows):
        if len(sells) >= 3:
            break
        if r["symbol"] not in sell_syms:
            sell_syms.add(r["symbol"])
            reason = r.get("reason") or f"{r.get('pct_change', 0):+.2f}% intraday — NIFTY 50 momentum"
            sells.append({**r, "reason": reason})

    return buys[:3], sells[:3]


def _do_refresh_recommendations() -> None:
    """Background worker: build recommendations and write to cache."""
    try:
        today = dt.date.today().strftime("%B %Y")
        buy_articles, sell_articles = _rss_recommendations()

        if len(_pick_stocks(buy_articles)) < 3:
            buy_articles.extend(
                _ddg_search(f"NSE India top stocks buy recommendation analyst target {today}")
            )
        if len(_pick_stocks(sell_articles)) < 3:
            sell_articles.extend(
                _ddg_search(f"NSE India stocks sell reduce downgrade recommendation {today}")
            )

        buys  = _pick_stocks(buy_articles,  limit=6)
        sells = _pick_stocks(sell_articles, limit=6)

        all_syms = list({s["symbol"] for s in buys + sells})
        prices   = _enrich_prices(all_syms)
        for item in buys + sells:
            p = prices.get(item["symbol"])
            if p:
                item["price"]      = p["price"]
                item["pct_change"] = p["pct_change"]
                item["sector"]     = p["sector"]

        buys_ok  = [s for s in buys  if s.get("price")][:3]
        sells_ok = [s for s in sells if s.get("price")][:3]

        if len(buys_ok) < 3 or len(sells_ok) < 3:
            buys_ok, sells_ok = _pad_with_nifty50_recs(buys_ok, sells_ok)

        src = "Google News RSS + yfinance" if (buys_ok or sells_ok) else "NIFTY 50 / yfinance"
        result = {"buy": buys_ok, "sell": sells_ok, "source": src}
    except Exception:
        logger.exception("recommendations refresh crashed")
        result = {"buy": [], "sell": [], "source": "unavailable"}

    with _rec_lock:
        _rec_cache["data"] = result
        _rec_cache["ts"]   = dt.datetime.utcnow()
        _rec_cache["refreshing"] = False


def _ensure_recs_fresh() -> None:
    with _rec_lock:
        ts = _rec_cache["ts"]
        already = _rec_cache["refreshing"]
    stale = ts is None or (dt.datetime.utcnow() - ts) > _CACHE_TTL
    if stale and not already:
        with _rec_lock:
            _rec_cache["refreshing"] = True
        threading.Thread(target=_do_refresh_recommendations, daemon=True).start()


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/market-movers")
def market_movers():
    _ensure_movers_fresh()
    with _movers_lock:
        data = _movers_cache["data"]
        refreshing = _movers_cache["refreshing"]
    if data is None:
        # First-ever call: block briefly for NSE (fast path only)
        result = _fetch_nse_movers()
        if result:
            with _movers_lock:
                _movers_cache["data"] = result
                _movers_cache["ts"]   = dt.datetime.utcnow()
            return result
        return {"gainers": [], "losers": [], "source": "loading…"}
    return data


@router.get("/sectors")
def sectors():
    """Whole-market sector breadth + rotation momentum (NSE sectoral
    indices), not just the 15 watchlist tickers — each entry's `count` is
    that sector index's full advances+declines constituent count."""
    from app.api.routes_agents import mark_sector_rotation_hit
    mark_sector_rotation_hit()

    _ensure_sectors_fresh()
    with _sectors_lock:
        data = _sectors_cache["data"]
    if data is None:
        # First-ever call: block briefly for NSE (fast path only)
        result = _fetch_nse_sectors()
        if result:
            with _sectors_lock:
                _sectors_cache["data"] = result
                _sectors_cache["ts"]   = dt.datetime.utcnow()
            return result
        return []
    return data


@router.get("/market-recommendations")
def market_recommendations():
    _ensure_recs_fresh()
    with _rec_lock:
        data = _rec_cache["data"]
    if data is None:
        return {"buy": [], "sell": [], "source": "loading…"}
    return data


_IST_OFFSET = dt.timedelta(hours=5, minutes=30)


def _day_start_utc(ist_date: dt.date) -> dt.datetime:
    """Midnight IST for the given date, as a naive UTC datetime (matches how
    Price.fetched_at is stored) for DB comparison."""
    return dt.datetime.combine(ist_date, dt.time.min) - _IST_OFFSET


def _price_series_from_db(db: Session, ticker: str, limit: int = 200) -> list[float]:
    """Fallback series built from our own periodic price fetches, used when
    yfinance's live intraday call fails (rate-limited/blocked, which happens
    often for cloud-hosted requests).

    Scoped to a single trading day (today IST, or the most recent day we
    have data for) so the shape of the sparkline reflects the same window as
    the "Day Change" figure, instead of blending in older days' price levels
    and showing a misleading trend.
    """
    today_ist = (dt.datetime.now(dt.timezone.utc) + _IST_OFFSET).date()
    rows = (
        db.query(Price)
        .filter(Price.ticker == ticker, Price.fetched_at >= _day_start_utc(today_ist))
        .order_by(Price.fetched_at.asc())
        .limit(limit)
        .all()
    )
    if len(rows) >= 2:
        return [r.price for r in rows]

    # No (or one) fetch yet today, e.g. before market hours — use the most
    # recent day we actually have data for instead of mixing days together.
    latest = db.query(Price).filter(Price.ticker == ticker).order_by(Price.fetched_at.desc()).first()
    if latest is None:
        return [r.price for r in rows]
    last_day = (latest.fetched_at + _IST_OFFSET).date()
    rows = (
        db.query(Price)
        .filter(
            Price.ticker == ticker,
            Price.fetched_at >= _day_start_utc(last_day),
            Price.fetched_at < _day_start_utc(last_day + dt.timedelta(days=1)),
        )
        .order_by(Price.fetched_at.asc())
        .limit(limit)
        .all()
    )
    return [r.price for r in rows]


# ── Headline index historical series (Market Overview chart) ───────────────

_INDEX_YF_SYMBOLS = {
    "NIFTY 50": "^NSEI",
    "SENSEX": "^BSESN",
    "NIFTY BANK": "^NSEBANK",
}

# yfinance (period, interval) per UI range button. Index-level intraday/
# historical series has no free NSE API — yfinance is the only source, and
# per this codebase's existing comments it's frequently blocked for
# server-side requests. Attempted honestly; callers should show an
# "unavailable" state on a 204/empty response rather than fabricate data.
_RANGE_PARAMS = {
    "1D": ("1d", "5m"),
    "1W": ("5d", "15m"),
    "1M": ("1mo", "1d"),
    "3M": ("3mo", "1d"),
    "6M": ("6mo", "1d"),
    "1Y": ("1y", "1d"),
}


def _nse_intraday_index_series(index: str) -> list[dict]:
    """Real NSE intraday tick series for today's session — only populated
    during live NSE trading hours (this reflects NSE's own real-world
    server clock, not any client-side date). Empty outside market hours is
    expected, not a bug."""
    data = _nse_get("/api/chart-databyindex", params={"index": index})
    if not isinstance(data, dict):
        return []
    points = data.get("grapthData") or []
    out = []
    for point in points:
        if not isinstance(point, list) or len(point) < 2:
            continue
        ts_ms, close = point[0], point[1]
        try:
            out.append({
                "t": dt.datetime.utcfromtimestamp(ts_ms / 1000).isoformat() + "Z",
                "c": round(float(close), 2),
            })
        except (TypeError, ValueError):
            continue
    return out


@router.get("/index-series")
def index_series(index: str = "NIFTY 50", range: str = "1D"):
    """[{t: iso-timestamp, c: close}] for a headline index over the given
    range, or an empty list if the source is unavailable this call."""
    if range.upper() == "1D":
        live = _nse_intraday_index_series(index)
        if live:
            return live

    symbol = _INDEX_YF_SYMBOLS.get(index.upper()) or _INDEX_YF_SYMBOLS.get(index)
    params = _RANGE_PARAMS.get(range.upper())
    if not symbol or not params:
        return []

    try:
        import yfinance as yf
        period, interval = params
        hist = yf.Ticker(symbol).history(period=period, interval=interval)
        if hist is None or hist.empty:
            return []
        return [
            {"t": ts.isoformat(), "c": round(float(row["Close"]), 2)}
            for ts, row in hist.iterrows()
            if row["Close"] == row["Close"]  # drop NaN rows
        ]
    except Exception as e:
        logger.warning("index_series failed for %s/%s: %s", index, range, e)
        return []


@router.get("/price-series/{ticker}")
def price_series(ticker: str, db: Session = Depends(get_db)):
    """Return recent close prices for a ticker, most recent last.

    Prefers our own periodically-fetched price history (fast, always
    available for tracked tickers) since yfinance's live intraday call is
    frequently blocked/rate-limited for server-side requests and can take
    ~20s to fail — too slow for a UI sparkline. Falls back to yfinance only
    when we have no local history (e.g. an untracked ticker).
    """
    local_series = _price_series_from_db(db, ticker)
    if len(local_series) >= 2:
        return local_series

    try:
        import yfinance as yf
        sym = ticker
        # yfinance expects exchange suffix like .NS for NSE symbols; if missing, try raw symbol first
        if not sym.upper().endswith(".NS") and not "." in sym:
            sym_ns = f"{sym}.NS"
        else:
            sym_ns = sym
        t = yf.Ticker(sym_ns)
        # fetch 1 day of intraday data at 5m intervals
        hist = t.history(period="1d", interval="5m")
        if hist is not None and not hist.empty:
            return [float(x) for x in hist["Close"].tolist()]
    except Exception:
        logger.exception("price_series failed for %s", ticker)

    return local_series
