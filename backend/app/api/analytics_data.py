import datetime as dt
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_refreshing = False
_refresh_done = threading.Event()
_cache: dict = {
    "mutual_funds": [],
    "gold": None,
    "fd_rates": [],
    "ipos": [],
    "commodities": [],
    "currencies": [],
    "gov_bonds": [],
    "refreshed_at": None,
}

GOV_BONDS = [
    {
        "name": "10Y Indian G-Sec",
        "maturity": "2034-05-30",
        "coupon": "7.26%",
        "yield_pct": 7.26,
        "price": 100.15,
    },
    {
        "name": "7Y Indian G-Sec",
        "maturity": "2031-11-15",
        "coupon": "7.03%",
        "yield_pct": 7.03,
        "price": 100.02,
    },
    {
        "name": "5Y Indian G-Sec",
        "maturity": "2029-06-15",
        "coupon": "6.79%",
        "yield_pct": 6.79,
        "price": 100.10,
    },
    {
        "name": "3Y Indian G-Sec",
        "maturity": "2027-08-20",
        "coupon": "6.35%",
        "yield_pct": 6.35,
        "price": 99.78,
    },
    {
        "name": "2Y Indian G-Sec",
        "maturity": "2026-12-10",
        "coupon": "6.10%",
        "yield_pct": 6.10,
        "price": 99.42,
    },
]

# ── Mutual fund scheme config (AMFI codes via mfapi.in) ─────────────────────
MF_CONFIG = {
    "Large Cap": [
        {"name": "Mirae Asset Large Cap Fund", "code": "118825"},
        {"name": "SBI Large Cap Fund", "code": "119598"},
        {"name": "Axis Large Cap Fund", "code": "120465"},
    ],
    "Mid Cap": [
        {"name": "HDFC Mid Cap Fund", "code": "118989"},
        {"name": "ICICI Prudential MidCap Fund", "code": "120381"},
        {"name": "Nippon India Multi Cap Fund", "code": "118650"},
    ],
    "ELSS (Tax Saving)": [
        {"name": "Mirae Asset ELSS Tax Saver Fund", "code": "135781"},
        {"name": "Axis ELSS Tax Saver Fund", "code": "120503"},
        {"name": "SBI ELSS Tax Saver Fund", "code": "119723"},
    ],
}

# ── NSE IPO session headers ──────────────────────────────────────────────────
# NSE retired the old `liveIPO?status=` endpoints (now 404) in favor of these.
_NSE_HOME     = "https://www.nseindia.com"
_NSE_IPO_URL  = "https://www.nseindia.com/api/all-upcoming-issues?category=ipo"
_NSE_OPEN_URL = "https://www.nseindia.com/api/ipo-current-issue"
_NSE_HEADERS  = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/market-data/upcoming-issues-ipo",
}

MF_API = "https://api.mfapi.in/mf/{code}"

# ── FD rates — top 5 banks by highest general-public rate ───────────────────
FD_RATES = [
    {
        "bank": "Unity Small Finance Bank",
        "max_rate": 9.50,
        "tenure": "1001 days",
        "type": "Small Finance Bank",
        "note": "General public rate",
    },
    {
        "bank": "Suryoday Small Finance Bank",
        "max_rate": 9.10,
        "tenure": "5 years",
        "type": "Small Finance Bank",
        "note": "General public rate",
    },
    {
        "bank": "ESAF Small Finance Bank",
        "max_rate": 8.75,
        "tenure": "2–3 years",
        "type": "Small Finance Bank",
        "note": "General public rate",
    },
    {
        "bank": "Utkarsh Small Finance Bank",
        "max_rate": 8.50,
        "tenure": "2 years",
        "type": "Small Finance Bank",
        "note": "General public rate",
    },
    {
        "bank": "Jana Small Finance Bank",
        "max_rate": 8.25,
        "tenure": "1–2 years",
        "type": "Small Finance Bank",
        "note": "General public rate",
    },
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fetch_one_mf(scheme: dict, category: str) -> dict | None:
    try:
        with httpx.Client(timeout=12) as client:
            r = client.get(MF_API.format(code=scheme["code"]))
            r.raise_for_status()
            payload = r.json()
        nav_data = payload.get("data", [])
        if not nav_data:
            return None

        current_nav = float(nav_data[0]["nav"])
        prev_nav = float(nav_data[1]["nav"]) if len(nav_data) > 1 else current_nav
        day_change = (current_nav - prev_nav) / prev_nav * 100 if prev_nav else 0

        year_return: float | None = None
        today = dt.date.today()
        for entry in nav_data:
            try:
                edate = dt.datetime.strptime(entry["date"], "%d-%m-%Y").date()
                if (today - edate).days >= 360:
                    nav_1y = float(entry["nav"])
                    year_return = (current_nav - nav_1y) / nav_1y * 100
                    break
            except Exception:
                continue

        return {
            "name": scheme["name"],
            "code": scheme["code"],
            "category": category,
            "nav": round(current_nav, 4),
            "nav_date": nav_data[0]["date"],
            "day_change": round(day_change, 2),
            "year_return": round(year_return, 2) if year_return is not None else None,
        }
    except Exception as exc:
        logger.warning("MF fetch failed %s: %s", scheme["code"], exc)
        return None


def _fetch_mutual_funds() -> list[dict]:
    tasks = [(s, cat) for cat, schemes in MF_CONFIG.items() for s in schemes]
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_fetch_one_mf, s, cat): s for s, cat in tasks}
        for fut in as_completed(futures):
            r = fut.result()
            if r:
                results.append(r)
    return results


_MC_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://www.moneycontrol.com/",
}

_GOLD_API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

_YAHOO_QUERY_HEADERS = {
    "User-Agent": _GOLD_API_HEADERS["User-Agent"],
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

# 1 troy oz = 31.1035 grams
_TROY_OZ_GRAMS = 31.1035


def _to_float(v) -> float | None:
    try:
        return float(str(v).replace(",", "").replace("₹", "").strip()) if v not in (None, "", "-") else None
    except (ValueError, TypeError):
        return None


def _parse_gr_price(text: str) -> tuple[float | None, float | None]:
    """Parse goodreturns price cell like '₹14,455 (+377)' → (price, change)."""
    import re as _re
    clean = text.replace("₹", "").replace(",", "")
    nums = _re.findall(r"[\d]+(?:\.\d+)?", clean)
    price = float(nums[0]) if nums else None
    change = float(nums[1]) if len(nums) > 1 else None
    if change and "-" in text:
        change = -change
    return price, change


def _parse_gr_history_cell(text: str) -> tuple[float | None, float | None]:
    """Parse goodreturns daily-history cell like '₹14,673(0)' or
    '₹14,700(+322)' → (price, change)."""
    import re as _re
    m = _re.search(r"₹?([\d,]+)\(([+-]?\d+)\)", text)
    if not m:
        return None, None
    return float(m.group(1).replace(",", "")), float(m.group(2))


def _fetch_gold() -> dict | None:
    """Scrape Indian 22K/24K/18K gold rates from goodreturns.in.
    Falls back to gold-api.com international spot + import duties.
    """
    try:
        r = httpx.get(
            "https://www.goodreturns.in/gold-rates/",
            headers={**_MC_HEADERS, "Referer": "https://www.goodreturns.in/"},
            timeout=14, follow_redirects=True,
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "lxml")

        # Primary: summary price cards. Price lives in a dedicated
        # .gold-bottom sub-element — the card's combined text also contains
        # the "24K"/"22K" label itself, whose digits would otherwise get
        # mistaken for the price by a naive whole-card number scan.
        cards = soup.find_all(class_="gold-each-container")
        k24_g: float | None = None
        k22_g: float | None = None

        for card in cards:
            label = card.find(class_="gold-top")
            label_txt = label.get_text(strip=True).lower() if label else ""
            price_el = card.find(class_="gold-bottom")
            price, _ = _parse_gr_price(price_el.get_text(" ", strip=True)) if price_el else (None, None)
            if price is None:
                continue

            if "24k" in label_txt:
                k24_g = price
            elif "22k" in label_txt:
                k22_g = price

        # Fallback: parse Table 0 (Gram | 24K | 22K | 18K), row for 1g
        if not (k24_g and k22_g):
            for table in soup.find_all("table"):
                rows = table.find_all("tr")
                if len(rows) < 2:
                    continue
                hdrs = [c.get_text(strip=True).lower() for c in rows[0].find_all(["th","td"])]
                if "24k" not in hdrs or "22k" not in hdrs:
                    continue
                idx24 = hdrs.index("24k")
                idx22 = hdrs.index("22k")
                for row in rows[1:]:
                    cells = row.find_all("td")
                    if not cells:
                        continue
                    row_label = cells[0].get_text(strip=True)
                    if row_label == "1":  # per-gram row
                        k24_g, _ = _parse_gr_price(cells[idx24].get_text(" ", strip=True))
                        k22_g, _ = _parse_gr_price(cells[idx22].get_text(" ", strip=True))
                        break
                if k24_g:
                    break

        # Day-over-day change: the summary cards don't carry it at all
        # anymore, but goodreturns' own "Date | 24K | 22K" history table
        # embeds it per-day as "₹14,700(+322)" — take the most recent row.
        k24_chg: float | None = None
        k22_chg: float | None = None
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue
            hdrs = [c.get_text(strip=True).lower() for c in rows[0].find_all(["th", "td"])]
            if "date" not in hdrs or "24k" not in hdrs:
                continue
            idx24 = hdrs.index("24k")
            idx22 = hdrs.index("22k") if "22k" in hdrs else None
            cells = rows[1].find_all("td")
            if cells:
                _, k24_chg = _parse_gr_history_cell(cells[idx24].get_text(strip=True))
                if idx22 is not None:
                    _, k22_chg = _parse_gr_history_cell(cells[idx22].get_text(strip=True))
            break

        if k24_g and k22_g and k24_g > 5000:
            k24_chg = k24_chg or 0.0
            k22_chg = k22_chg or 0.0
            day_change_pct = round(k24_chg / (k24_g - k24_chg) * 100, 2) if k24_chg else 0.0
            logger.info("goodreturns gold: 24K ₹%s/g, 22K ₹%s/g", k24_g, k22_g)
            return {
                "k24_per_gram_inr": round(k24_g, 2),
                "k22_per_gram_inr": round(k22_g, 2),
                "k24_per_10g_inr": round(k24_g * 10, 2),
                "k22_per_10g_inr": round(k22_g * 10, 2),
                "k24_day_change_inr": round(k24_chg * 10, 2),
                "k22_day_change_inr": round(k22_chg * 10, 2),
                "day_change_pct": day_change_pct,
                "usd_per_oz": None,
                "usd_inr_rate": None,
                "fetched_at": dt.datetime.utcnow().isoformat() + "Z",
            }
    except Exception as exc:
        logger.warning("goodreturns gold scrape failed: %s", exc)

    # Fallback: gold-api.com spot + Indian duties (6.3% import + 3% GST)
    try:
        r2 = httpx.get("https://api.gold-api.com/price/XAU/INR", headers=_GOLD_API_HEADERS, timeout=10)
        r2.raise_for_status()
        data = r2.json()
        price_oz_inr = _to_float(data.get("price"))
        exchange_rate = _to_float(data.get("exchangeRate"))
        if price_oz_inr and price_oz_inr > 10000:
            k24_g = price_oz_inr / _TROY_OZ_GRAMS * 1.063 * 1.03
            k22_g = k24_g * 22 / 24
            usd_per_oz = round(price_oz_inr / exchange_rate, 2) if exchange_rate else None
            logger.info("gold-api.com fallback: 24K ₹%.2f/g (spot+duties)", k24_g)
            return {
                "k24_per_gram_inr": round(k24_g, 2),
                "k22_per_gram_inr": round(k22_g, 2),
                "k24_per_10g_inr": round(k24_g * 10, 2),
                "k22_per_10g_inr": round(k22_g * 10, 2),
                "k24_day_change_inr": 0.0,
                "k22_day_change_inr": 0.0,
                "day_change_pct": 0.0,
                "usd_per_oz": usd_per_oz,
                "usd_inr_rate": round(exchange_rate, 2) if exchange_rate else None,
                "fetched_at": dt.datetime.utcnow().isoformat() + "Z",
            }
    except Exception as exc:
        logger.warning("gold-api.com fallback failed: %s", exc)

    return None


def _parse_nse_ipos(raw: list[dict], status: str) -> list[dict]:
    out = []
    cutoff = dt.date.today() + dt.timedelta(days=180)
    for item in raw:
        try:
            # `ipo-current-issue` / `all-upcoming-issues` (current NSE API)
            # use issueStartDate/issueEndDate and don't carry price/size/lot
            # at all; keep the older field names too as a defensive fallback
            # in case NSE's shape shifts again.
            name      = item.get("companyName") or item.get("CompanyName") or ""
            open_str  = item.get("issueStartDate") or item.get("openDate") or item.get("OpenDate") or ""
            close_str = item.get("issueEndDate") or item.get("closeDate") or item.get("CloseDate") or ""
            low       = item.get("issuePriceLow")  or item.get("IssuePriceLow")  or ""
            high      = item.get("issuePriceHigh") or item.get("IssuePriceHigh") or ""
            size      = item.get("issueSize") or item.get("IssueSize") or ""
            lot       = item.get("lotSize") or item.get("LotSize") or ""

            # Parse date — NSE uses "10-JUL-2026" or "2026-07-10"
            open_date = None
            for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y"):
                try:
                    open_date = dt.datetime.strptime(open_str, fmt).date()
                    break
                except (ValueError, TypeError):
                    continue

            if open_date and open_date > cutoff:
                continue  # beyond 6-month window

            price_band = ""
            if low and high:
                price_band = f"₹{low} – ₹{high}"
            elif high:
                price_band = f"₹{high}"

            out.append({
                "company": name,
                "open_date": open_str,
                "close_date": close_str,
                "price_band": price_band,
                "issue_size": f"₹{size} Cr" if size else "",
                "lot_size": str(lot),
                "status": status,
            })
        except Exception:
            continue
    return out




def _scrape_mc_ipos() -> list[dict]:
    """Scrape Moneycontrol /ipo/ page — extracts IPO cards with their Details tables."""
    import re as _re
    try:
        r = httpx.get("https://www.moneycontrol.com/ipo/", headers=_MC_HEADERS, timeout=16, follow_redirects=True)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "lxml")  # bytes → lxml detects UTF-8 correctly
    except Exception as exc:
        logger.warning("Moneycontrol IPO page fetch failed: %s", exc)
        return []

    out: list[dict] = []
    # Each IPO is an ipoInfoCardHolder div containing a Details table
    cards = soup.find_all(class_=_re.compile(r"ipoInfoCardHolder", _re.I))
    for card in cards:
        try:
            # Company name
            title_el = card.find(class_=_re.compile(r"cardTitle", _re.I))
            company = title_el.get_text(strip=True) if title_el else ""
            if not company:
                continue

            # Status from button text (Open / Upcoming / Closed)
            buttons = [b.get_text(strip=True) for b in card.find_all("button")]
            status = "Open"
            for btn in buttons:
                bl = btn.lower()
                if "upcoming" in bl:
                    status = "Upcoming"
                elif "closed" in bl or "listed" in bl:
                    status = "Closed"
                elif "open" in bl:
                    status = "Open"

            # Details table rows
            details: dict[str, str] = {}
            for t in card.find_all("table"):
                rows = t.find_all("tr")
                if not rows:
                    continue
                first = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
                if first and first[0] == "Details":
                    for row in rows[1:]:
                        cells = row.find_all("td")
                        if len(cells) >= 2:
                            details[cells[0].get_text(strip=True)] = cells[1].get_text(strip=True)

            out.append({
                "company": company,
                "open_date": details.get("Open Date", ""),
                "close_date": details.get("Close Date", ""),
                "price_band": details.get("Issue Price", ""),
                "issue_size": details.get("Issue Size", ""),
                "lot_size": details.get("Lot Size", ""),
                "status": status,
            })
        except Exception:
            continue

    logger.info("Moneycontrol IPO scrape: %d cards", len(out))
    return out


def _fetch_ipos() -> list[dict]:
    """Primary: Moneycontrol /ipo/ card scrape. Secondary: NSE live API."""
    mc_result = _scrape_mc_ipos()

    # NSE for upcoming IPOs (MC only shows currently open ones)
    nse_result: list[dict] = []
    try:
        import time
        with httpx.Client(headers=_NSE_HEADERS, timeout=16, follow_redirects=True) as client:
            client.get(_NSE_HOME, headers={**_NSE_HEADERS, "Accept": "text/html"})
            time.sleep(1)
            upcoming_raw = client.get(_NSE_IPO_URL).json()
            open_raw     = client.get(_NSE_OPEN_URL).json()
        for raw, status in [(open_raw, "Open"), (upcoming_raw, "Upcoming")]:
            items = raw if isinstance(raw, list) else raw.get("data", [])
            nse_result.extend(_parse_nse_ipos(items, status))
        if nse_result:
            logger.info("NSE IPO: %d entries", len(nse_result))
    except Exception as exc:
        logger.warning("NSE IPO failed: %s", exc)

    # Merge: deduplicate by normalized company name. MC says "X IPO", NSE
    # says "X Limited" for the same issue — strip both kinds of suffix so
    # they collide instead of showing the same IPO twice (once with full
    # price/size/lot details from MC, once bare from NSE).
    def _norm(name: str) -> str:
        n = name.lower().strip()
        for suffix in (" ipo", " limited", " ltd.", " ltd", " private limited", " pvt ltd"):
            if n.endswith(suffix):
                n = n[: -len(suffix)].strip()
        return n

    seen = {_norm(ipo["company"]) for ipo in mc_result}
    for ipo in nse_result:
        key = _norm(ipo["company"])
        if key not in seen:
            mc_result.append(ipo)
            seen.add(key)

    return mc_result


# ── Commodities (Yahoo Finance quote API) ─────────────────────────────────

_COMMODITIES = [
    {"name": "Gold",   "symbol": "GC=F", "unit": "USD/oz"},
    {"name": "Silver", "symbol": "SI=F", "unit": "USD/oz"},
    {"name": "Copper", "symbol": "BZ=F", "unit": "USD/bbl"},
]

_CURRENCY_PAIRS = [
    {"currency": "USD", "name": "US Dollar",      "symbol": "USDINR=X"},
    {"currency": "EUR", "name": "Euro",            "symbol": "EURINR=X"},
    {"currency": "GBP", "name": "British Pound",   "symbol": "GBPINR=X"},
    {"currency": "JPY", "name": "Japanese Yen",    "symbol": "JPYINR=X"},
]


def _fetch_yahoo_chart(symbol: str) -> dict | None:
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        r = httpx.get(url, headers=_YAHOO_QUERY_HEADERS, timeout=14)
        r.raise_for_status()
        payload = r.json()
        results = payload.get("chart", {}).get("result") or []
        if not results:
            return None
        return results[0].get("meta", {})
    except Exception as exc:
        logger.warning("Yahoo chart fetch failed %s: %s", symbol, exc)
        return None


def _fetch_commodities() -> list[dict]:
    results = []
    for c in _COMMODITIES:
        quote = _fetch_yahoo_chart(c["symbol"])
        if not quote:
            logger.warning("commodity quote missing %s", c["symbol"])
            continue
        price = _to_float(quote.get("regularMarketPrice"))
        prev = _to_float(quote.get("previousClose"))
        pct = _to_float(quote.get("regularMarketChangePercent"))
        if pct is None and price is not None and prev is not None:
            pct = (price - prev) / prev * 100 if prev else 0.0
        if price is None or pct is None:
            logger.warning("commodity quote incomplete %s", c["symbol"])
            continue
        results.append({
            "name":       c["name"],
            "symbol":     c["symbol"],
            "price":      round(price, 2),
            "unit":       c["unit"],
            "change_pct": round(pct, 2),
        })
    if not results:
        try:
            import yfinance as yf
            for c in _COMMODITIES:
                try:
                    hist = yf.Ticker(c["symbol"]).history(period="5d")
                    if hist.empty:
                        continue
                    current = float(hist["Close"].iloc[-1])
                    prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current
                    pct = (current - prev) / prev * 100 if prev else 0.0
                    results.append({
                        "name":       c["name"],
                        "symbol":     c["symbol"],
                        "price":      round(current, 2),
                        "unit":       c["unit"],
                        "change_pct": round(pct, 2),
                    })
                except Exception as exc:
                    logger.warning("commodity fetch failed %s: %s", c["symbol"], exc)
        except ImportError:
            logger.warning("yfinance not available — skipping commodities")
    logger.info("commodities fetched: %d", len(results))
    return results


def _fetch_currencies() -> list[dict]:
    results = []
    for p in _CURRENCY_PAIRS:
        quote = _fetch_yahoo_chart(p["symbol"])
        if not quote:
            logger.warning("currency quote missing %s", p["symbol"])
            continue
        rate = _to_float(quote.get("regularMarketPrice"))
        prev = _to_float(quote.get("previousClose"))
        pct = _to_float(quote.get("regularMarketChangePercent"))
        if pct is None and rate is not None and prev is not None:
            pct = (rate - prev) / prev * 100 if prev else 0.0
        if rate is None or pct is None:
            logger.warning("currency quote incomplete %s", p["symbol"])
            continue
        results.append({
            "currency":   p["currency"],
            "name":       p["name"],
            "rate_inr":   round(rate, 4),
            "change_pct": round(pct, 4),
        })
    if not results:
        try:
            import yfinance as yf
            for p in _CURRENCY_PAIRS:
                try:
                    hist = yf.Ticker(p["symbol"]).history(period="5d")
                    if hist.empty:
                        continue
                    current = float(hist["Close"].iloc[-1])
                    prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current
                    pct = (current - prev) / prev * 100 if prev else 0.0
                    results.append({
                        "currency":   p["currency"],
                        "name":       p["name"],
                        "rate_inr":   round(current, 4),
                        "change_pct": round(pct, 4),
                    })
                except Exception as exc:
                    logger.warning("currency fetch failed %s: %s", p["symbol"], exc)
        except ImportError:
            logger.warning("yfinance not available — skipping currencies")
    logger.info("currencies fetched: %d", len(results))
    return results


# ── Public API ───────────────────────────────────────────────────────────────

def _do_refresh() -> None:
    global _refreshing
    logger.info("analytics_data: refreshing…")
    with _lock:
        if _refreshing:
            logger.info("analytics_data: refresh already in progress")
            return
        _refreshing = True
        _refresh_done.clear()
    try:
        mutual_funds = _fetch_mutual_funds()
        gold         = _fetch_gold()
        commodities  = _fetch_commodities()
        currencies   = _fetch_currencies()
        ipos         = _fetch_ipos()
        gov_bonds    = GOV_BONDS
        with _lock:
            _cache["mutual_funds"] = mutual_funds
            _cache["gold"]         = gold
            _cache["commodities"]  = commodities
            _cache["currencies"]   = currencies
            _cache["fd_rates"]     = FD_RATES
            _cache["ipos"]         = ipos
            _cache["gov_bonds"]   = gov_bonds
            _cache["refreshed_at"] = dt.datetime.utcnow().isoformat() + "Z"
        logger.info(
            "analytics_data: done — %d funds, gold=%s, %d commodities, %d currencies, %d IPOs",
            len(mutual_funds), gold is not None, len(commodities), len(currencies), len(ipos),
        )
    finally:
        with _lock:
            _refreshing = False
        _refresh_done.set()


def get(key: str):
    with _lock:
        return _cache.get(key)


def ensure_fresh() -> None:
    with _lock:
        refreshed = _cache.get("refreshed_at")
        refreshing = _refreshing
    if refreshed is None and not refreshing:
        threading.Thread(target=_do_refresh, daemon=True, name="analytics-refresh").start()


def wait_for_fresh(timeout: float = 15.0) -> None:
    ensure_fresh()
    _refresh_done.wait(timeout=timeout)
