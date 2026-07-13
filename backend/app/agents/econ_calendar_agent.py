"""India macro-release calendar — scraped from Trading Economics' public
India calendar page (no free structured API exists for this; FRED only
carries US series, which is why this agent previously showed nothing for
an India-first build). Same "scrape a public page, no API key" pattern as
`analytics_data.py`'s moneycontrol/goodreturns pulls.

Covers CPI/WPI inflation, GDP, IIP, PMI (mfg/services/composite), RBI repo
rate moves via unemployment/rate series, trade balance, forex reserves, and
similar — whatever India releases the page is currently tracking, so no
static series allowlist to maintain.
"""

import datetime as dt
import logging
import re

import httpx
from bs4 import BeautifulSoup

from app.agents.base import BaseAgent
from app.analysis import claude_client
from app.models import EconomicEvent

logger = logging.getLogger(__name__)

CALENDAR_URL = "https://tradingeconomics.com/india/calendar"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Only a handful of categories move Indian markets meaningfully — the rest
# (e.g. individual vehicle-sales sub-series) are kept but shown as lower
# priority. Matched against the row's `data-category` attribute.
_HIGH_IMPORTANCE = {
    "gdp growth rate", "gdp annual growth rate", "inflation rate",
    "interest rate", "unemployment rate", "balance of trade",
    "manufacturing pmi", "services pmi", "composite pmi",
}
_LOW_IMPORTANCE = {
    "foreign exchange reserves", "loan growth", "deposit growth",
    "money supply m3",
}

_DATE_HEADER_RE = re.compile(r"[A-Za-z]+ [A-Za-z]+ \d{1,2} \d{4}")


def _importance_for(category: str) -> str:
    category = category.lower().strip()
    if category in _HIGH_IMPORTANCE:
        return "high"
    if category in _LOW_IMPORTANCE:
        return "low"
    return "medium"


def _parse_number(text: str | None) -> float | None:
    if not text:
        return None
    cleaned = text.strip().replace(",", "").replace("%", "")
    match = re.match(r"-?\d+(\.\d+)?", cleaned)
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def _row_text(row, selector_id: str) -> str:
    el = row.select_one(f"#{selector_id}")
    return el.get_text(strip=True) if el else ""


class EconCalendarAgent(BaseAgent):
    name = "econ_calendar"

    def run(self) -> None:
        try:
            resp = httpx.get(CALENDAR_URL, headers=_HEADERS, timeout=15, follow_redirects=True)
            resp.raise_for_status()
        except Exception:
            logger.warning("India economic calendar fetch failed")
            return

        soup = BeautifulSoup(resp.text, "lxml")
        # NB: `table.calendar-table` is the *outer* wrapper (holds the date-
        # range filter buttons) — the actual event rows live in the nested
        # `table#calendar`.
        table = soup.select_one("table#calendar")
        if table is None:
            logger.warning("India economic calendar page layout changed — no #calendar table found")
            return

        session = self.session()
        current_date: dt.datetime | None = None
        stored = 0
        try:
            for el in table.find_all(["thead", "tr"], recursive=True):
                if el.name == "thead":
                    if "hidden-head" in (el.get("class") or []):
                        continue
                    header = el.find("th", attrs={"colspan": True})
                    if header:
                        match = _DATE_HEADER_RE.search(header.get_text(" ", strip=True))
                        if match:
                            try:
                                current_date = dt.datetime.strptime(match.group(), "%A %B %d %Y")
                            except ValueError:
                                pass
                    continue

                if not el.has_attr("data-event") or current_date is None:
                    continue

                try:
                    self._store_row(session, el, current_date)
                    stored += 1
                except Exception:
                    logger.exception("Failed to parse one India calendar row, skipping it")

            _backfill_ai_reasons(session)
            session.commit()
        finally:
            session.close()

        logger.info("India economic calendar: %d event(s) upserted", stored)

    @staticmethod
    def _store_row(session, row, release_date: dt.datetime) -> None:
        series_id = row.get("data-symbol") or row.get("data-id")
        category = row.get("data-category") or ""
        if not series_id:
            return

        event_link = row.select_one("a.calendar-event")
        event_name = event_link.get_text(strip=True) if event_link else category.title()
        reference = row.select_one(".calendar-reference")
        reference_text = reference.get_text(strip=True) if reference else ""
        title = f"{event_name} ({reference_text})" if reference_text else event_name

        actual_text = _row_text(row, "actual")
        previous_text = _row_text(row, "previous")
        forecast_text = _row_text(row, "forecast")
        consensus_text = _row_text(row, "consensus")

        value = _parse_number(actual_text)
        is_released = value is not None
        if value is None:
            value = _parse_number(forecast_text) or _parse_number(consensus_text)

        detail_parts = []
        if is_released and previous_text:
            detail_parts.append(f"Prev {previous_text}")
        elif not is_released:
            if previous_text:
                detail_parts.append(f"Prev {previous_text}")
            if forecast_text:
                detail_parts.append(f"Fcst {forecast_text}")
        detail = " · ".join(detail_parts) or None

        existing = (
            session.query(EconomicEvent)
            .filter_by(series_id=series_id, release_date=release_date)
            .first()
        )
        if existing:
            # Revisit the same event as it moves from "forecast pending" to
            # "actual released" across successive scrapes. Clear any prior
            # ai_reason too — it was written against the old value/detail,
            # so it needs to be regenerated against the newly-released facts.
            existing.value = value
            existing.detail = detail
            existing.title = title
            existing.ai_reason = None
            existing.fetched_at = dt.datetime.utcnow()
            return

        session.add(
            EconomicEvent(
                series_id=series_id,
                title=title,
                value=value,
                detail=detail,
                release_date=release_date,
                importance=_importance_for(category),
                fetched_at=dt.datetime.utcnow(),
            )
        )


def _backfill_ai_reasons(session) -> None:
    """One-line AI reason for only the 10 releases actually shown at the
    top of the panel (same ordering as `GET /api/economic-events`) — bounds
    spend, and a reason persists until the release itself changes (see
    `_store_row`'s forecast→actual transition, above)."""
    top = (
        session.query(EconomicEvent)
        .order_by(EconomicEvent.release_date.desc().nullslast())
        .limit(10)
        .all()
    )
    for item in top:
        if item.ai_reason is not None:
            continue
        description = item.title
        if item.value is not None:
            description += f" — value {item.value}"
        if item.detail:
            description += f" ({item.detail})"
        item.ai_reason = claude_client.explain_relevance(
            "India economic release", description
        ) or _FALLBACK_REASON[item.importance]


# Generic, honest one-liners used when no ANTHROPIC_API_KEY is configured —
# same "never a blank panel" convention as OrchestratorAgent's
# _fallback_briefing, keyed off the importance tier already assigned in
# _importance_for() rather than fabricating a per-release explanation.
_FALLBACK_REASON = {
    "high": "Headline macro indicators like this can move broad market sentiment and RBI policy expectations.",
    "medium": "Adds context to India's broader economic trend, with typically moderate near-term market impact.",
    "low": "A secondary data point — usually limited direct impact on equity markets.",
}
