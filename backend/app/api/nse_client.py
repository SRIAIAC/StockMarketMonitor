"""Shared NSE India public-API session helper.

NSE's `/api/*` endpoints reject requests that don't arrive with cookies from
a prior browser-like GET to the homepage (a lightweight bot-check, not real
auth) — every caller needs to warm a session the same way before hitting an
API path. This was previously duplicated per call-site in routes_market.py;
centralized here so every agent/route that needs an NSE endpoint reuses one
implementation.
"""

import logging

import httpx

logger = logging.getLogger(__name__)

NSE_HOME = "https://www.nseindia.com"

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/market-data/live-equity-market",
}


def nse_get(path: str, params: dict | None = None, timeout: float = 12) -> dict | list | None:
    """Cookie-warm GET against an NSE `/api/...` path. Returns parsed JSON,
    or None on any failure (network, non-2xx, bad JSON) — callers should
    treat None the same as "source unavailable right now"."""
    url = f"{NSE_HOME}{path}"
    try:
        with httpx.Client(headers=NSE_HEADERS, timeout=timeout, follow_redirects=True) as client:
            client.get(NSE_HOME, headers={**NSE_HEADERS, "Accept": "text/html"})
            resp = client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning("NSE API call failed (%s): %s", path, e)
        return None
