"""Normalizes a ticker's stored `Price.sector` (Moneycontrol's fine-grained
labels for the original watchlist, yfinance's coarser labels for tickers
that fell through to that fallback — see market_agent.py) into the same
14 canonical names `routes_market.SECTOR_INDEX_MAP` derives from NSE's own
sectoral indices (NIFTY BANK -> "Banking", etc).

Why this exists: `recommendation_agent.py`'s sector-momentum term looks up
`sector_momentum.get(p.sector, 50.0)` by exact string match against those
14 canonical names. Found live that raw `Price.sector` values almost never
match them verbatim (e.g. "Bank - Private", "Financial Services", "Basic
Materials" from the two source APIs vs. "Banking", "Metal", "Cement" from
NSE's own naming) — so the sector-momentum term, and the "{sector} rotating
in/out" reason text, were silently defaulting to neutral for the large
majority of the watchlist. Not something introduced by the 50->100 ticker
expansion — the mismatch already existed for original tickers too (e.g.
AXISBANK.NS's stored sector is "Financial Services", not "Banking").

This module only affects the sector-momentum *lookup* used for scoring and
reason text. `Price.sector` itself is left untouched — it's still the
right thing to display as-is on the Watchlist page.
"""

CANONICAL_SECTORS = {
    "Banking", "IT", "Auto", "Pharma", "FMCG", "Metal", "Energy", "Realty",
    "Media", "Consumer Durables", "Oil & Gas", "Cement", "Chemicals", "Healthcare",
}

# Raw sector string -> canonical bucket, for values that map unambiguously
# regardless of which specific ticker carries them.
_RAW_SECTOR_MAP: dict[str, str] = {
    "Bank - Private": "Banking",
    "Bank - Public": "Banking",
    "Financial Services": "Banking",
    "Finance - Investment": "Banking",
    "Technology": "IT",
    "IT Services & Consulting": "IT",
    "Consumer Defensive": "FMCG",
    "Pharmaceuticals & Drugs": "Pharma",
    "Healthcare": "Healthcare",
    "Oil Exploration and Production": "Oil & Gas",
    "Energy": "Energy",
    "Utilities": "Energy",  # NIFTY Energy in practice spans power gen/transmission too (NTPC, POWERGRID)
}

# Tickers whose raw sector is one of yfinance's broad, ambiguous buckets
# ("Basic Materials", "Consumer Cyclical", "Industrials", etc.) that spans
# several real NSE sectors — resolved individually by what the company
# actually makes/does. Tickers deliberately left out of both maps (e.g.
# BHARTIARTL.NS/telecom, LT.NS/construction, TRENT.NS/retail, hotels,
# ports) have no honest fit among these 14 NSE sectoral indices — left
# unmapped rather than forced into a wrong bucket, same as they were before.
_TICKER_OVERRIDE: dict[str, str] = {
    # Metal
    "TATASTEEL.NS": "Metal", "JSWSTEEL.NS": "Metal", "HINDALCO.NS": "Metal",
    "APLAPOLLO.NS": "Metal", "RATNAMANI.NS": "Metal",
    # Cement
    "ULTRACEMCO.NS": "Cement", "GRASIM.NS": "Cement", "AMBUJACEM.NS": "Cement",
    "BIRLACORPN.NS": "Cement",
    # Chemicals
    "ASIANPAINT.NS": "Chemicals", "BERGEPAINT.NS": "Chemicals", "PIIND.NS": "Chemicals",
    "DEEPAKNTR.NS": "Chemicals", "SRF.NS": "Chemicals", "CLEAN.NS": "Chemicals",
    "NAVINFLUOR.NS": "Chemicals", "FINEORG.NS": "Chemicals", "GALAXYSURF.NS": "Chemicals",
    # Auto
    "MARUTI.NS": "Auto", "TMPV.NS": "Auto", "HEROMOTOCO.NS": "Auto", "EICHERMOT.NS": "Auto",
    "M&M.NS": "Auto", "ESCORTS.NS": "Auto",
    # Consumer Durables
    "TITAN.NS": "Consumer Durables", "VOLTAS.NS": "Consumer Durables",
    "DIXON.NS": "Consumer Durables", "HAVELLS.NS": "Consumer Durables",
    "CROMPTON.NS": "Consumer Durables", "BLUESTARCO.NS": "Consumer Durables",
    "CENTURYPLY.NS": "Consumer Durables", "VGUARD.NS": "Consumer Durables",
    "KEI.NS": "Consumer Durables",
    # IT (engineering/IT/analytics services labeled "Technology"/"Industrials" upstream)
    "LTTS.NS": "IT", "KPITTECH.NS": "IT", "LATENTVIEW.NS": "IT",
    # Oil & Gas
    "ONGC.NS": "Oil & Gas", "BPCL.NS": "Oil & Gas",
    # Pharma / Healthcare services
    "GLENMARK.NS": "Pharma",
    "RAINBOW.NS": "Healthcare", "LALPATHLAB.NS": "Healthcare", "METROPOLIS.NS": "Healthcare",
    # Energy (power exchange / power equipment)
    "IEX.NS": "Energy",
}


def canonical_sector(ticker: str, raw_sector: str | None) -> str | None:
    """Best-effort mapping to one of the 14 NSE-sectoral-index names used
    by `/api/sectors`. Returns None (never guesses) if there's no honest
    fit — callers should treat that the same as "no sector data"."""
    if ticker in _TICKER_OVERRIDE:
        return _TICKER_OVERRIDE[ticker]
    if raw_sector in CANONICAL_SECTORS:
        return raw_sector
    if raw_sector in _RAW_SECTOR_MAP:
        return _RAW_SECTOR_MAP[raw_sector]
    return None
