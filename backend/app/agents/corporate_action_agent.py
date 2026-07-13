"""Whole-market corporate actions (dividends, splits, bonuses, buybacks,
rights issues, AGMs) from NSE's own public corporate-actions feed.

Not scoped to `settings.tickers` — this covers every NSE-listed company,
matching what a general "Corporate Action Agent" implies, bounded to a
rolling date window so the payload/table stay a manageable size.
"""

import datetime as dt
import logging

from app.agents.base import BaseAgent
from app.analysis import claude_client
from app.api.nse_client import nse_get
from app.models import CorporateAction

logger = logging.getLogger(__name__)

_NSE_PATH = "/api/corporates-corporateActions"

# Keep a rolling window around "today" — recently gone-ex plus upcoming —
# rather than ingesting NSE's full historical archive every run.
_WINDOW_PAST_DAYS = 30
_WINDOW_FUTURE_DAYS = 60

_ACTION_KEYWORDS: list[tuple[str, str]] = [
    ("BONUS", "Bonus"),
    ("SPLIT", "Split"),
    ("SUB-DIVISION", "Split"),
    ("SUB DIVISION", "Split"),
    ("RIGHTS", "Rights"),
    ("BUYBACK", "Buyback"),
    ("BUY BACK", "Buyback"),
    ("AGM", "AGM"),
    ("ANNUAL GENERAL MEETING", "AGM"),
    ("DIVIDEND", "Dividend"),
]


def _classify(subject: str) -> str:
    upper = subject.upper()
    for keyword, label in _ACTION_KEYWORDS:
        if keyword in upper:
            return label
    return "Other"


def _parse_nse_date(value: str | None) -> dt.datetime | None:
    if not value or value == "-":
        return None
    try:
        return dt.datetime.strptime(value.strip(), "%d-%b-%Y")
    except ValueError:
        return None


class CorporateActionAgent(BaseAgent):
    name = "corporate_action"

    def run(self) -> None:
        data = nse_get(_NSE_PATH, params={"index": "equities"})
        if not isinstance(data, list):
            logger.warning("Corporate actions feed unavailable this run")
            return

        today = dt.datetime.utcnow()
        window_start = today - dt.timedelta(days=_WINDOW_PAST_DAYS)
        window_end = today + dt.timedelta(days=_WINDOW_FUTURE_DAYS)

        session = self.session()
        seen: set[tuple[str, str, str]] = set()
        try:
            for item in data:
                symbol = (item.get("symbol") or "").strip()
                subject = (item.get("subject") or "").strip()
                if not symbol or not subject:
                    continue

                ex_date = _parse_nse_date(item.get("exDate"))
                if ex_date is not None and not (window_start <= ex_date <= window_end):
                    continue

                key = (symbol, item.get("exDate") or "", subject)
                if key in seen:
                    continue
                seen.add(key)

                if (
                    session.query(CorporateAction)
                    .filter_by(symbol=symbol, raw_subject=subject, ex_date=ex_date)
                    .first()
                ):
                    continue

                action_type = _classify(subject)
                value = subject.split("-", 1)[1].strip() if "-" in subject else None

                session.add(
                    CorporateAction(
                        symbol=symbol,
                        company_name=item.get("comp"),
                        action_type=action_type,
                        ex_date=ex_date,
                        record_date=_parse_nse_date(item.get("recDate")),
                        announcement_date=_parse_nse_date(item.get("caBroadcastDate")),
                        value=value,
                        raw_subject=subject,
                        source_url="https://www.nseindia.com/companies-listing/corporate-filings-actions",
                        fetched_at=dt.datetime.utcnow(),
                    )
                )
            _backfill_ai_reasons(session)
            session.commit()
        finally:
            session.close()


def _backfill_ai_reasons(session) -> None:
    """One-line AI reason for only the 10 actions actually shown at the top
    of the panel (same ordering/filter as `GET /api/corporate-actions`) —
    bounds spend regardless of how many rows this run added, and reasons
    persist once written so a later run only pays for genuinely new
    top-10 entries, not the same ones again."""
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=7)
    top = (
        session.query(CorporateAction)
        .filter((CorporateAction.ex_date.is_(None)) | (CorporateAction.ex_date >= cutoff))
        .order_by(CorporateAction.ex_date.asc().nullslast())
        .limit(10)
        .all()
    )
    for item in top:
        if item.ai_reason is not None:
            continue
        item.ai_reason = claude_client.explain_relevance(
            "Corporate action",
            f"{item.company_name or item.symbol} ({item.symbol}) — {item.action_type}: {item.raw_subject}",
        ) or _FALLBACK_REASON.get(item.action_type, _FALLBACK_REASON["Other"])


# Generic, honest one-liners used when no ANTHROPIC_API_KEY is configured —
# never fabricated per-company detail, just the general reason this
# category of action typically matters. Same "never a blank panel"
# convention as OrchestratorAgent's _fallback_briefing.
_FALLBACK_REASON = {
    "Dividend": "Dividends return cash to shareholders and can signal management's confidence in cash flow.",
    "Bonus": "Bonus issues increase share count without changing fundamental value, often boosting liquidity.",
    "Split": "Stock splits lower the per-share price and can improve retail accessibility, without changing fundamental value.",
    "Buyback": "Buybacks reduce share count, which can support EPS and often signals management sees the stock as undervalued.",
    "Rights": "Rights issues raise capital from existing shareholders and can dilute holders who don't participate.",
    "AGM": "AGMs are where shareholders vote on key company matters — a routine governance event.",
    "Other": "Corporate actions like this can affect share count, valuation, or shareholder returns.",
}
