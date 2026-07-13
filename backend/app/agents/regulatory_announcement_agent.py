"""Whole-market regulatory/compliance disclosures from NSE's own public
corporate-announcements feed.

IMPORTANT — naming honesty: this is **not** a SEBI EDIFAR filings feed.
There is no free, public API for SEBI's own filing system (EDIFAR / SCORES),
the same structural gap that led to the InsiderAgent being removed entirely
(see the "Removed" note in agents/README.md) rather than run as a permanent
no-op. NSE's corporate-announcements feed is the closest real, free,
keyless substitute — it carries the listed-company disclosures NSE requires
under SEBI's LODR regulations (board meetings, credit ratings, investor
presentations, compliance certificates, etc.), which is genuinely useful
but is NSE's disclosure feed, not SEBI's. The frontend must label this
"NSE Regulatory Announcements", never "SEBI Filings".

Insider-trading / SAST-disclosure items are explicitly filtered out below —
never stored, even though NSE's raw feed technically carries some adjacent
categories — to keep this agent's data cleanly separate from the insider-
trading concept the product deliberately excludes.
"""

import datetime as dt
import logging

from app.agents.base import BaseAgent
from app.analysis import claude_client
from app.api.nse_client import nse_get
from app.models import RegulatoryAnnouncement

logger = logging.getLogger(__name__)

_NSE_PATH = "/api/corporate-announcements"

_EXCLUDE_KEYWORDS = [
    "INSIDER TRADING",
    "SAST",
    "REGULATION 29",
    "REGULATION 31",
    "REGULATION 7(2)",
    "SUBSTANTIAL ACQUISITION",
]


def _is_excluded(desc: str, subject: str) -> bool:
    haystack = f"{desc} {subject}".upper()
    return any(keyword in haystack for keyword in _EXCLUDE_KEYWORDS)


def _parse_nse_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.strptime(value.strip(), "%d-%b-%Y %H:%M:%S")
    except ValueError:
        return None


class RegulatoryAnnouncementAgent(BaseAgent):
    name = "regulatory_announcement"

    def run(self) -> None:
        data = nse_get(_NSE_PATH, params={"index": "equities"})
        if not isinstance(data, list):
            logger.warning("Corporate announcements feed unavailable this run")
            return

        session = self.session()
        seen: set[str] = set()
        try:
            for item in data:
                symbol = (item.get("symbol") or "").strip()
                subject = (item.get("attchmntText") or "").strip()
                category = (item.get("desc") or "Other").strip()
                if not symbol or not subject:
                    continue
                if _is_excluded(category, subject):
                    continue

                attachment_url = item.get("attchmntFile") or None
                dedupe_key = attachment_url or f"{symbol}|{subject}|{item.get('an_dt')}"
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                if attachment_url:
                    existing = session.query(RegulatoryAnnouncement).filter_by(
                        attachment_url=attachment_url
                    ).first()
                else:
                    existing = session.query(RegulatoryAnnouncement).filter_by(
                        symbol=symbol, subject=subject,
                    ).first()
                if existing:
                    continue

                session.add(
                    RegulatoryAnnouncement(
                        symbol=symbol,
                        company_name=item.get("sm_name"),
                        category=category,
                        subject=subject,
                        attachment_url=attachment_url,
                        announcement_date=_parse_nse_datetime(item.get("an_dt")),
                        source_url="https://www.nseindia.com/companies-listing/corporate-filings-announcements",
                        fetched_at=dt.datetime.utcnow(),
                    )
                )
            _backfill_ai_reasons(session)
            session.commit()
        finally:
            session.close()


def _backfill_ai_reasons(session) -> None:
    """One-line AI reason for only the 10 filings actually shown at the top
    of the panel (same ordering as `GET /api/regulatory-announcements`) —
    bounds spend, and reasons persist so later runs only pay for genuinely
    new top-10 entries."""
    top = (
        session.query(RegulatoryAnnouncement)
        .order_by(RegulatoryAnnouncement.announcement_date.desc().nullslast())
        .limit(10)
        .all()
    )
    for item in top:
        if item.ai_reason is not None:
            continue
        item.ai_reason = claude_client.explain_relevance(
            "NSE regulatory announcement",
            f"{item.company_name or item.symbol} ({item.symbol}) — {item.category}: {item.subject}",
        ) or _fallback_reason(item.category)


# Generic, honest one-liners used when no ANTHROPIC_API_KEY is configured —
# keyword-matched against NSE's freeform category text, same "never a
# blank panel" convention as OrchestratorAgent's _fallback_briefing.
_FALLBACK_KEYWORDS = [
    ("BOARD MEETING", "Board meetings often precede material announcements like results, dividends, or fundraising plans."),
    ("FINANCIAL RESULT", "Quarterly/annual results are a primary driver of near-term price moves."),
    ("CREDIT RATING", "Credit rating changes affect a company's borrowing cost and can signal shifting financial health."),
    ("INVESTOR PRESENTATION", "Investor presentations often preview management's strategic priorities and outlook."),
    ("ANALYST", "Analyst/investor meets can move sentiment if new guidance or commentary emerges."),
    ("COMPLIANCE", "Compliance disclosures are routine LODR filings with typically limited direct price impact."),
]


def _fallback_reason(category: str) -> str:
    upper = (category or "").upper()
    for keyword, reason in _FALLBACK_KEYWORDS:
        if keyword in upper:
            return reason
    return "NSE-mandated disclosures like this help investors track material developments at the company."
