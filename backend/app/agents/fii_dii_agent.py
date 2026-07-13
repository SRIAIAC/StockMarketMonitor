"""FII/FDI/DII institutional-investment signal, in two honest parts:

1. Whole-market daily net FII/DII trading activity — real, from NSE's own
   `fiidiiTradeReact` feed (₹ Cr buy/sell/net). Accumulated one row per
   trading day since NSE only ever returns the latest day, not a range.
2. Per-stock FII/FDI/DII news mentions — there is no free API anywhere
   that discloses which specific stocks are about to receive institutional
   investment (that's forward-looking data nobody publishes for free, and
   NSE's own bulk/block-deals endpoint is blocked from this environment,
   same as the quote-equity endpoint documented in nse_client.py). This is
   a Google News scrape matched against the watchlist via the same
   company-name gazetteer YouTubeAgent uses (`analysis/youtube_analysis.
   extract_companies`) — FII/DII/FDI headlines almost always use full
   company names ("Bharti Airtel"), never bare ticker symbols, so the
   plain-substring ticker matcher news_agent.py uses would essentially
   never match anything here. VADER-scored, explicitly labeled as
   news-derived rather than a confirmed transaction — same honesty
   precedent as the removed InsiderAgent and RegulatoryAnnouncementAgent's
   "not literal SEBI EDIFAR" note.
"""

import datetime as dt
import logging

import feedparser

from app.agents.base import BaseAgent
from app.analysis import claude_client
from app.analysis.sentiment import score_text
from app.analysis.youtube_analysis import extract_companies
from app.api.nse_client import nse_get
from app.models import FiiDiiFlow, FiiDiiSummary, InstitutionalMention

logger = logging.getLogger(__name__)

_FLOW_PATH = "/api/fiidiiTradeReact"

# category -> Google News query. "FDI" here means foreign-company-into-
# listed-Indian-company deal announcements, the closest per-stock analogue
# to FDI that ever shows up in news (true FDI is an RBI/govt macro
# aggregate, not stock-level — see analysis/econ, no per-stock API exists).
_MENTION_FEEDS = [
    ("FII", "https://news.google.com/rss/search?q=FII+buying+stake+NSE+India+stock&hl=en-IN&gl=IN&ceid=IN:en"),
    ("DII", "https://news.google.com/rss/search?q=DII+mutual+fund+buying+NSE+India+stock&hl=en-IN&gl=IN&ceid=IN:en"),
    ("FDI", "https://news.google.com/rss/search?q=foreign+investment+stake+Indian+company+deal&hl=en-IN&gl=IN&ceid=IN:en"),
]

_MENTION_MAX_AGE_DAYS = 90


def _parse_nse_date(value: str) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(value.strip(), "%d-%b-%Y")
    except (ValueError, AttributeError):
        return None


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class FiiDiiAgent(BaseAgent):
    name = "fii_dii"

    def run(self) -> None:
        session = self.session()
        try:
            self._store_market_flow(session)
            self._store_mentions(session)
            self._store_daily_summary(session)
            session.commit()
        finally:
            session.close()

    @staticmethod
    def _store_market_flow(session) -> None:
        data = nse_get(_FLOW_PATH)
        if not isinstance(data, list):
            logger.warning("FII/DII trade activity feed unavailable this run")
            return

        by_category = {row.get("category"): row for row in data}
        dii = by_category.get("DII")
        fii = by_category.get("FII/FPI") or by_category.get("FII")
        if not dii and not fii:
            return

        trade_date = _parse_nse_date((dii or fii).get("date", ""))
        if trade_date is None:
            return

        if session.query(FiiDiiFlow).filter_by(trade_date=trade_date).first():
            return  # already have today's figure

        session.add(
            FiiDiiFlow(
                trade_date=trade_date,
                fii_buy_cr=_to_float(fii.get("buyValue")) if fii else None,
                fii_sell_cr=_to_float(fii.get("sellValue")) if fii else None,
                fii_net_cr=_to_float(fii.get("netValue")) if fii else None,
                dii_buy_cr=_to_float(dii.get("buyValue")) if dii else None,
                dii_sell_cr=_to_float(dii.get("sellValue")) if dii else None,
                dii_net_cr=_to_float(dii.get("netValue")) if dii else None,
                fetched_at=dt.datetime.utcnow(),
            )
        )

    @staticmethod
    def _store_daily_summary(session) -> None:
        """AI narrative over the flow trend + recent mentions — dedup on
        `trade_date` (like FiiDiiFlow itself), so this only ever costs one
        Claude call per real trading day, not one per 3h agent run."""
        latest_flow = session.query(FiiDiiFlow).order_by(FiiDiiFlow.trade_date.desc()).first()
        if latest_flow is None:
            return
        trade_date = latest_flow.trade_date

        if session.query(FiiDiiSummary).filter_by(trade_date=trade_date).first():
            return  # already summarized today

        history = (
            session.query(FiiDiiFlow)
            .order_by(FiiDiiFlow.trade_date.desc())
            .limit(10)
            .all()
        )
        flow_lines = [
            f"{f.trade_date.strftime('%d-%b')}: FII net {f.fii_net_cr:+.0f} Cr, DII net {f.dii_net_cr:+.0f} Cr"
            for f in reversed(history)
            if f.fii_net_cr is not None and f.dii_net_cr is not None
        ]

        recent_mentions = (
            session.query(InstitutionalMention)
            .order_by(InstitutionalMention.fetched_at.desc())
            .limit(15)
            .all()
        )
        mention_lines = [
            f"{m.ticker.replace('.NS', '')} ({m.category}): {m.title}" for m in recent_mentions
        ]

        context = "Recent daily FII/DII net flow (₹ Cr):\n" + "\n".join(flow_lines)
        if mention_lines:
            context += "\n\nRecent per-stock FII/DII/FDI news mentions:\n" + "\n".join(mention_lines)

        summary = claude_client.summarize_context("India FII/DII institutional investment activity", context)
        ai_generated = summary is not None
        if summary is None:
            trend = "net buying" if latest_flow.fii_net_cr and latest_flow.fii_net_cr >= 0 else "net selling"
            dii_trend = "net buying" if latest_flow.dii_net_cr and latest_flow.dii_net_cr >= 0 else "net selling"
            summary = (
                f"FIIs were {trend} ({latest_flow.fii_net_cr:+.0f} Cr) and DIIs were {dii_trend} "
                f"({latest_flow.dii_net_cr:+.0f} Cr) on {trade_date.strftime('%d %b')}."
            )

        session.add(
            FiiDiiSummary(
                trade_date=trade_date,
                summary=summary,
                ai_generated=int(ai_generated),
                computed_at=dt.datetime.utcnow(),
            )
        )

    @staticmethod
    def _store_mentions(session) -> None:
        cutoff = dt.datetime.utcnow() - dt.timedelta(days=_MENTION_MAX_AGE_DAYS)
        seen: set[tuple[str, str]] = set()  # (ticker, url) — see model docstring

        for category, url in _MENTION_FEEDS:
            try:
                feed = feedparser.parse(url)
            except Exception:
                logger.warning("FII/DII mention feed failed for %s", category)
                continue

            for entry in feed.entries[:30]:
                title = entry.get("title", "")
                link = entry.get("link")
                if not link:
                    continue

                published_at = None
                if entry.get("published_parsed"):
                    published_at = dt.datetime(*entry.published_parsed[:6])
                    if published_at < cutoff:
                        continue

                tickers = extract_companies(title)
                if not tickers:
                    continue  # only keep headlines tied to a watchlist stock

                sentiment = score_text(title)
                for ticker in tickers:
                    key = (ticker, link)
                    if key in seen:
                        continue
                    seen.add(key)
                    if session.query(InstitutionalMention).filter_by(ticker=ticker, url=link).first():
                        continue

                    session.add(
                        InstitutionalMention(
                            ticker=ticker,
                            category=category,
                            title=title,
                            url=link,
                            sentiment=sentiment,
                            published_at=published_at,
                            fetched_at=dt.datetime.utcnow(),
                        )
                    )
