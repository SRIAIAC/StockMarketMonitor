"""Chat endpoint — RAG over live DB data + MAS architecture knowledge."""

import datetime as dt
import logging
import re
from collections import defaultdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.analysis import ollama_client
from app.api.routes_dashboard import get_db
from app.config import settings
from app.models import Alert, NewsItem, Price, SocialPost

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

_MAS_DESCRIPTION = """
You are the assistant embedded in the Indian Stock Market Watch platform — a multi-agent system (MAS) that monitors NSE stocks in real time.

## Multi-Agent System (MAS) — 5 background agents
1. MarketAgent — polls Moneycontrol + yfinance every {price_poll_minutes} min for live NSE prices, % change, and volume.
2. NewsAgent — scrapes Reuters, MarketWatch, and CNBC RSS feeds every {news_poll_minutes} min; each headline is VADER-scored (-1 to +1).
3. SocialAgent — fetches recent StockTwits posts per watchlist ticker every {social_poll_minutes} min, VADER-scored.
4. EconCalendarAgent — scrapes India's macro release calendar (CPI, GDP, PMI, RBI rate moves, trade balance) every 3h.
5. AlertAgent — evaluates all recent DB rows every {price_poll_minutes} min against deterministic thresholds:
   • Price move ≥ 3 % → warning; + volume ≥ 2× avg → critical (AI-escalated)
   • News sentiment ≤ -0.5 → warning (AI-escalated)
   • StockTwits score ≥ 1 → info; ≥ 2 → AI-escalated

## Two-tier AI escalation (cost-aware RAG)
• Haiku triage — cheap pass classifying HIGH_IMPACT: yes/no.
• Sonnet deep-dive — only for HIGH_IMPACT signals; produces 2-3 sentence analysis.
• Results are cached by SHA-256 content hash to avoid duplicate API calls.

## Watchlist (50 NSE tickers, large/mid/small cap across banking, IT,
FMCG, auto, pharma, energy, cement, metals, chemicals, and consumer)
""".strip()

_SYSTEM_TEMPLATE = """{mas}

## Live Market Snapshot ({ts} UTC)
{prices}

## Alerts — last 24 h
{alerts}

## Sentiment Heatmap — last 30 days avg (-1 bearish → +1 bullish)
{sentiment}

## Recent News Headlines — last 30 days
{news}

---
Answer using the live data above. Be concise and specific.
Use ₹ for prices and % for changes. Say so honestly if data is missing.
When asked about the MAS or agent architecture, refer to the descriptions above.

Format the reply as short bullet points (one fact per line, "- " prefix),
not paragraphs of prose. A one-line lead-in sentence is fine before the
bullets if it adds context, but never explain in full sentences what a
bullet list could show instead. Exception: if the user's question has
nothing to enumerate (e.g. a single yes/no or a single number), a single
short line is fine — don't force a list where there's only one point.
"""


def _build_system(db: Session) -> str:
    # --- prices ---
    subq = (
        db.query(Price.ticker, func.max(Price.fetched_at).label("mf"))
        .group_by(Price.ticker)
        .subquery()
    )
    prices = (
        db.query(Price)
        .join(subq, (Price.ticker == subq.c.ticker) & (Price.fetched_at == subq.c.mf))
        .all()
    )
    if prices:
        price_lines = []
        for p in sorted(prices, key=lambda x: x.ticker):
            sign = "+" if p.pct_change >= 0 else ""
            price_lines.append(
                f"  {p.ticker.replace('.NS',''):<14} ₹{p.price:>10.2f}  {sign}{p.pct_change:.2f}%"
                f"  vol={p.volume:>12,}  sector={p.sector or 'Unknown'}"
            )
        prices_block = "\n".join(price_lines)
    else:
        prices_block = "  No price data available yet."

    # --- alerts (kept short — an alert is about a recent triggered event,
    # not the "news/social analysis" window below) ---
    since = dt.datetime.utcnow() - dt.timedelta(hours=24)
    alerts = (
        db.query(Alert)
        .filter(Alert.created_at >= since)
        .order_by(Alert.created_at.desc())
        .limit(20)
        .all()
    )
    if alerts:
        alert_lines = [
            f"  [{a.severity.upper()}] {a.ticker or 'MARKET'}: {a.message}"
            + (" [AI]" if a.source_used_ai else "")
            for a in alerts
        ]
        alerts_block = "\n".join(alert_lines)
    else:
        alerts_block = "  No alerts in the last 24 hours."

    # --- sentiment (30 days — AI-facing news/social analysis draws on the
    # last month, not just the last day) ---
    news_since = dt.datetime.utcnow() - dt.timedelta(days=30)
    news_rows = db.query(NewsItem).filter(
        NewsItem.fetched_at >= news_since,
        NewsItem.ticker.isnot(None),
        NewsItem.sentiment.isnot(None),
    ).all()
    social_rows = db.query(SocialPost).filter(
        SocialPost.fetched_at >= news_since,
        SocialPost.ticker.isnot(None),
        SocialPost.sentiment.isnot(None),
    ).all()
    by_ticker: dict[str, list[float]] = defaultdict(list)
    for n in news_rows:
        by_ticker[n.ticker].append(n.sentiment)
    for s in social_rows:
        by_ticker[s.ticker].append(s.sentiment)

    if by_ticker:
        sent_lines = [
            f"  {t.replace('.NS',''):<14} avg={sum(v)/len(v):+.2f}  ({len(v)} samples)"
            for t, v in sorted(by_ticker.items())
        ]
        sentiment_block = "\n".join(sent_lines)
    else:
        sentiment_block = "  No sentiment data yet."

    # --- news headlines (same 30-day window as sentiment above) ---
    news_items = (
        db.query(NewsItem)
        .filter(NewsItem.fetched_at >= news_since)
        .order_by(NewsItem.fetched_at.desc())
        .limit(15)
        .all()
    )
    if news_items:
        news_lines = []
        for n in news_items:
            score = f"{n.sentiment:.2f}" if n.sentiment is not None else "n/a"
            news_lines.append(f"  [{n.ticker or 'MARKET'}] {n.title} (sentiment={score})")
        news_block = "\n".join(news_lines)
    else:
        news_block = "  No recent news."

    mas = _MAS_DESCRIPTION.format(
        price_poll_minutes=settings.price_poll_minutes,
        news_poll_minutes=settings.news_poll_minutes,
        social_poll_minutes=settings.social_poll_minutes,
    )
    return _SYSTEM_TEMPLATE.format(
        mas=mas,
        ts=dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
        prices=prices_block,
        alerts=alerts_block,
        sentiment=sentiment_block,
        news=news_block,
    )


def _fetch_web(query: str, max_results: int = 5) -> str:
    """Return formatted DuckDuckGo results, or empty string on failure."""
    try:
        from ddgs import DDGS

        results = list(DDGS().text(query, max_results=max_results))
        if not results:
            return ""
        lines = [f"{i+1}. {r['title']}\n   {r['body'][:200]}" for i, r in enumerate(results)]
        return "## Web Search Results\n" + "\n\n".join(lines)
    except Exception:
        logger.warning("Web search failed for query: %s", query)
        return ""


class _Msg(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[_Msg] = []
    web_search: bool = False


@router.post("/chat")
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    system_prompt = _build_system(db)
    searched = False
    web_block = ""

    if req.web_search:
        web_block = _fetch_web(req.message)
        searched = bool(web_block)

    # Compose the actual user content — prepend web results when available,
    # so whichever LLM answers is the one doing the summarizing, not a raw
    # dump of search results.
    user_content = req.message
    if web_block:
        user_content = f"{web_block}\n\n---\nUser question: {req.message}"

    history = [{"role": m.role, "content": m.content} for m in req.history]
    history.append({"role": "user", "content": user_content})

    if settings.anthropic_api_key:
        try:
            from anthropic import Anthropic

            client = Anthropic(api_key=settings.anthropic_api_key)
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=700,
                system=system_prompt,
                messages=history,
            )
            return {"reply": resp.content[0].text.strip(), "used_ai": True, "searched": searched}
        except Exception:
            logger.exception("Claude chat API call failed")

    # No Anthropic key (or the call above failed) — try local Ollama next,
    # same system prompt + history, so DB-grounding and web-search
    # summarizing both still work without a paid API key.
    ollama_reply = ollama_client.chat_completion(system_prompt, history)
    if ollama_reply:
        return {"reply": ollama_reply, "used_ai": True, "searched": searched}

    # Neither Claude nor Ollama available — show raw web results or a
    # keyword-matched reply straight from the DB.
    if searched and web_block:
        return {"reply": web_block, "used_ai": False, "searched": True}
    return {"reply": _fallback(req.message, db), "used_ai": False, "searched": False}


def _fallback(message: str, db: Session) -> str:
    """Keyword-based fallback when no Anthropic key is configured."""
    msg = message.lower()
    since = dt.datetime.utcnow() - dt.timedelta(hours=24)

    if any(w in msg for w in ("agent", "mas", "architecture", "how does", "system", "pipeline")):
        return (
            "The platform runs 5 core agents:\n"
            "- MarketAgent — prices every 15 min\n"
            "- NewsAgent — RSS sentiment every 60 min\n"
            "- SocialAgent — StockTwits every 60 min\n"
            "- EconCalendarAgent — India macro calendar every 3h\n"
            "- AlertAgent — evaluates all signals every 15 min, escalates high-impact "
            "ones to Claude Haiku/Sonnet via a two-tier AI pipeline"
        )

    if any(w in msg for w in ("alert", "warning", "critical")):
        alerts = (
            db.query(Alert)
            .filter(Alert.created_at >= since)
            .order_by(Alert.created_at.desc())
            .limit(5)
            .all()
        )
        if not alerts:
            return "No alerts in the last 24 hours."
        lines = [f"• [{a.severity.upper()}] {a.ticker or 'MARKET'}: {a.message}" for a in alerts]
        return "Recent alerts:\n" + "\n".join(lines)

    if any(w in msg for w in ("top", "gainer", "loser", "best", "worst", "trending", "mover")):
        subq = (
            db.query(Price.ticker, func.max(Price.fetched_at).label("mf"))
            .group_by(Price.ticker)
            .subquery()
        )
        prices = (
            db.query(Price)
            .join(subq, (Price.ticker == subq.c.ticker) & (Price.fetched_at == subq.c.mf))
            .all()
        )
        if not prices:
            return "No price data yet."
        srt = sorted(prices, key=lambda p: p.pct_change, reverse=True)
        top = [f"  {p.ticker.replace('.NS','')}: +{p.pct_change:.2f}%" for p in srt[:3]]
        bot = [f"  {p.ticker.replace('.NS','')}: {p.pct_change:.2f}%" for p in srt[-3:]]
        return "Top gainers:\n" + "\n".join(top) + "\n\nTop losers:\n" + "\n".join(bot)

    for ticker in settings.tickers:
        sym = ticker.replace(".NS", "")
        # Word-boundary match, not substring — several tickers in the 50-name
        # watchlist are short (LT, ITC, SRF, IEX...) and would otherwise
        # false-positive inside ordinary words (e.g. "lt" in "difficult").
        if re.search(rf"\b{re.escape(sym.lower())}\b", msg):
            subq = (
                db.query(Price.ticker, func.max(Price.fetched_at).label("mf"))
                .group_by(Price.ticker)
                .subquery()
            )
            p = (
                db.query(Price)
                .filter(Price.ticker == f"{sym}.NS")
                .join(subq, (Price.ticker == subq.c.ticker) & (Price.fetched_at == subq.c.mf))
                .first()
            )
            if p:
                sign = "+" if p.pct_change >= 0 else ""
                return (
                    f"{sym}: ₹{p.price:.2f} ({sign}{p.pct_change:.2f}%) "
                    f"| Volume: {p.volume:,} | Sector: {p.sector or 'Unknown'}"
                )
            return f"No price data for {sym} yet."

    return (
        "I can answer questions about: live NSE prices, top movers, recent alerts, "
        "news/social sentiment, or how this multi-agent system works. "
        "Try: 'What are today's top gainers?' or 'How does the alert pipeline work?'"
    )
