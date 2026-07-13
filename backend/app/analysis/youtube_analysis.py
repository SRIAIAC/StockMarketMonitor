"""Rule-based extraction over YouTube transcripts: no LLM call, no API key
needed (there's no ANTHROPIC_API_KEY configured in this environment).

Company names are matched against a hand-built gazetteer (spoken/written name
variants -> NSE ticker) rather than the ticker-code regex already used for
news headlines in routes_market.py, since transcripts say "Bajaj Finance",
not "BAJFINANCE". Recommendation/tone/topic are all keyword- or VADER-based —
deliberately simple, consistent with how the rest of the app behaves without
a Claude key (see AlertAgent/rules.py).
"""

import re

from app.analysis.sentiment import score_text

# ── Company gazetteer: spoken/written name variant -> ticker ────────────────
# Longer, more specific variants are matched first so "bajaj auto" doesn't
# get shadowed by a more generic "bajaj" fragment.
COMPANY_GAZETTEER: dict[str, str] = {
    "reliance industries": "RELIANCE.NS", "reliance": "RELIANCE.NS", "ril": "RELIANCE.NS",
    "tata consultancy services": "TCS.NS", "tata consultancy": "TCS.NS", "tcs": "TCS.NS",
    "hdfc bank": "HDFCBANK.NS",
    "bharti airtel": "BHARTIARTL.NS", "airtel": "BHARTIARTL.NS",
    "icici bank": "ICICIBANK.NS",
    "infosys": "INFY.NS", "infy": "INFY.NS",
    "state bank of india": "SBIN.NS", "state bank": "SBIN.NS", "sbi": "SBIN.NS",
    "hindustan unilever": "HINDUNILVR.NS", "hul": "HINDUNILVR.NS",
    "itc limited": "ITC.NS", "itc": "ITC.NS",
    "wipro": "WIPRO.NS",
    "kotak mahindra bank": "KOTAKBANK.NS", "kotak bank": "KOTAKBANK.NS", "kotak": "KOTAKBANK.NS",
    "larsen and toubro": "LT.NS", "larsen & toubro": "LT.NS", "l&t": "LT.NS", "larsen": "LT.NS",
    "maruti suzuki": "MARUTI.NS", "maruti": "MARUTI.NS",
    "bajaj finance": "BAJFINANCE.NS",
    "bajaj finserv": "BAJAJFINSV.NS",
    "bajaj auto": "BAJAJ-AUTO.NS",
    "axis bank": "AXISBANK.NS",
    "asian paints": "ASIANPAINT.NS",
    "ntpc": "NTPC.NS",
    "power grid": "POWERGRID.NS", "powergrid": "POWERGRID.NS",
    "sun pharmaceutical": "SUNPHARMA.NS", "sun pharma": "SUNPHARMA.NS",
    "adani ports": "ADANIPORTS.NS",
    "ultratech cement": "ULTRACEMCO.NS", "ultratech": "ULTRACEMCO.NS",
    "hcl technologies": "HCLTECH.NS", "hcl tech": "HCLTECH.NS", "hcltech": "HCLTECH.NS",
    "nestle india": "NESTLEIND.NS", "nestle": "NESTLEIND.NS",
    "titan company": "TITAN.NS", "titan": "TITAN.NS",
    "tech mahindra": "TECHM.NS",
    "tata consumer products": "TATACONSUM.NS", "tata consumer": "TATACONSUM.NS",
    "coal india": "COALINDIA.NS",
    "grasim industries": "GRASIM.NS", "grasim": "GRASIM.NS",
    "dr reddys laboratories": "DRREDDY.NS", "dr reddys": "DRREDDY.NS", "dr reddy": "DRREDDY.NS",
    "hero motocorp": "HEROMOTOCO.NS",
    "bharat petroleum": "BPCL.NS", "bpcl": "BPCL.NS",
    "eicher motors": "EICHERMOT.NS", "royal enfield": "EICHERMOT.NS",
    "shriram finance": "SHRIRAMFIN.NS",
    "cipla": "CIPLA.NS",
    "britannia industries": "BRITANNIA.NS", "britannia": "BRITANNIA.NS",
    "divis laboratories": "DIVISLAB.NS", "divis lab": "DIVISLAB.NS",
    "apollo hospitals": "APOLLOHOSP.NS",
    "trent limited": "TRENT.NS", "trent": "TRENT.NS",
    "hindalco industries": "HINDALCO.NS", "hindalco": "HINDALCO.NS",
    "jsw steel": "JSWSTEEL.NS",
    "tata steel": "TATASTEEL.NS",
    "ongc": "ONGC.NS", "oil and natural gas": "ONGC.NS",
    "indusind bank": "INDUSINDBK.NS",
    "mahindra and mahindra": "M&M.NS", "mahindra & mahindra": "M&M.NS",
    "adani enterprises": "ADANIENT.NS",
    "ltimindtree": "LTIM.NS", "lti mindtree": "LTIM.NS",
    "tata motors": "TATAMOTORS.NS",
    "bharat electronics": "BEL.NS",
    "zomato": "ZOMATO.NS", "eternal limited": "ZOMATO.NS",
    "cg power": "CGPOWER.NS", "cg power and industrial": "CGPOWER.NS",
    "dixon technologies": "DIXON.NS", "dixon": "DIXON.NS",
    "coforge": "COFORGE.NS",
    "persistent systems": "PERSISTENT.NS", "persistent": "PERSISTENT.NS",
    "mphasis": "MPHASIS.NS",
    "central depository services": "CDSL.NS", "cdsl": "CDSL.NS",
    "indian energy exchange": "IEX.NS",
    "cyient": "CYIENT.NS",
    "glenmark pharmaceuticals": "GLENMARK.NS", "glenmark": "GLENMARK.NS",
    "birla corporation": "BIRLACORPN.NS", "birla corp": "BIRLACORPN.NS",
    # Added when the watchlist grew from 15 to 50 tickers — this gazetteer
    # wasn't updated at the time, so any mention of these 20 names was
    # silently unrecognized (marked "no company mentions found") regardless
    # of transcript quality. TMPV = Tata Motors Passenger Vehicles (incl.
    # JLR), the entity TATAMOTORS.NS was renamed to after the Oct 2025
    # demerger — "tata motors" is kept pointing at it since most commentary
    # won't distinguish PV from the separately-listed CV entity.
    "tata motors passenger vehicles": "TMPV.NS", "tmpv": "TMPV.NS", "tata motors": "TMPV.NS",
    "federal bank": "FEDERALBNK.NS",
    "au small finance bank": "AUBANK.NS", "au bank": "AUBANK.NS", "au smfb": "AUBANK.NS",
    "pi industries": "PIIND.NS",
    "deepak nitrite": "DEEPAKNTR.NS",
    "srf limited": "SRF.NS", "srf": "SRF.NS",
    "page industries": "PAGEIND.NS",
    "voltas": "VOLTAS.NS",
    "indian hotels": "INDHOTEL.NS", "ihcl": "INDHOTEL.NS",
    "l&t technology services": "LTTS.NS", "lt technology services": "LTTS.NS", "ltts": "LTTS.NS",
    "computer age management services": "CAMS.NS", "cams": "CAMS.NS",
    "kpit technologies": "KPITTECH.NS", "kpit": "KPITTECH.NS",
    "rainbow childrens": "RAINBOW.NS", "rainbow hospitals": "RAINBOW.NS",
    "clean science": "CLEAN.NS", "clean science and technology": "CLEAN.NS",
    "angel one": "ANGELONE.NS", "angel broking": "ANGELONE.NS",
    "route mobile": "ROUTE.NS",
    "latentview analytics": "LATENTVIEW.NS", "latentview": "LATENTVIEW.NS",
    "happiest minds": "HAPPSTMNDS.NS",
    "granules india": "GRANULES.NS", "granules": "GRANULES.NS",
    "ratnamani metals": "RATNAMANI.NS", "ratnamani": "RATNAMANI.NS",
}
# Longest phrase first so multi-word variants win over their own substrings.
_GAZETTEER_PHRASES = sorted(COMPANY_GAZETTEER, key=len, reverse=True)

BUY_WORDS = [
    "buy", "accumulate", "add on dips", "top pick", "outperform",
    "overweight", "upgrade to buy", "bullish on", "long term buy",
]
SELL_WORDS = [
    "sell", "exit", "avoid", "reduce", "book profit", "booking profits",
    "bearish on", "underperform", "downgrade", "underweight",
]
HOLD_WORDS = ["hold", "neutral on", "stay invested", "maintain hold"]

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "Earnings": ["earnings", "quarterly result", "q1 result", "q2 result", "q3 result", "q4 result", "profit growth", "revenue growth"],
    "IPO": ["ipo", "initial public offering", "listing gains"],
    "Buyback": ["buyback", "buy back", "tender offer"],
    "Budget": ["union budget", "fiscal deficit", "budget 202"],
    "RBI Policy": ["rbi", "repo rate", "monetary policy", "interest rate"],
    "FII/DII Flows": ["fii", "dii", "foreign institutional", "domestic institutional", "inflows", "outflows"],
    "Technical Analysis": ["support level", "resistance level", "moving average", "rsi", "macd", "breakout", "chart pattern"],
    "Mutual Funds": ["mutual fund", "sip", "expense ratio", "nav"],
    "Global Markets": ["us markets", "nasdaq", "dow jones", "fed rate", "crude oil", "dollar index"],
}


def extract_companies(text: str, limit: int = 8) -> list[str]:
    """Return tickers mentioned in text, in order of first mention."""
    normalized = re.sub(r"\s+", " ", text.lower())
    hits: list[tuple[int, str]] = []
    matched_spans: list[tuple[int, int]] = []
    for phrase in _GAZETTEER_PHRASES:
        for m in re.finditer(r"\b" + re.escape(phrase) + r"\b", normalized):
            start, end = m.start(), m.end()
            if any(start < e and s < end for s, e in matched_spans):
                continue
            matched_spans.append((start, end))
            hits.append((start, COMPANY_GAZETTEER[phrase]))
    hits.sort(key=lambda h: h[0])
    out: list[str] = []
    for _, ticker in hits:
        if ticker not in out:
            out.append(ticker)
        if len(out) >= limit:
            break
    return out


def extract_recommendation(text: str) -> str | None:
    """Best-effort BUY/SELL/HOLD verdict from keyword counts across the whole
    transcript. There's no per-company attribution here (that would need real
    NLP) — it's a single overall verdict per video, same spirit as the rest
    of the rule-based pipeline.
    """
    lower = text.lower()
    buy = sum(lower.count(w) for w in BUY_WORDS)
    sell = sum(lower.count(w) for w in SELL_WORDS)
    hold = sum(lower.count(w) for w in HOLD_WORDS)
    if buy == 0 and sell == 0 and hold == 0:
        return None
    best = max(("BUY", buy), ("SELL", sell), ("HOLD", hold), key=lambda p: p[1])
    return best[0] if best[1] > 0 else None


def extract_topics(text: str, limit: int = 3) -> list[str]:
    lower = text.lower()
    scored = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        hits = sum(lower.count(k) for k in keywords)
        if hits > 0:
            scored.append((hits, topic))
    scored.sort(key=lambda p: p[0], reverse=True)
    return [topic for _, topic in scored[:limit]]


def extract_tone(text: str) -> tuple[str, float]:
    score = score_text(text)
    if score >= 0.2:
        return "Bullish", score
    if score <= -0.2:
        return "Bearish", score
    return "Neutral", score
