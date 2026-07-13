import datetime as _dt
import re as _re
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.routes_dashboard import get_db
from app.api import web_data
from app.models import Alert

router = APIRouter(prefix="/api")

_IST_OFFSET = _dt.timedelta(hours=5, minutes=30)
_PCT_IN_MESSAGE = _re.compile(r"([+-]?\d+(?:\.\d+)?)\s*%")


def _today_start_utc() -> _dt.datetime:
    """Return today midnight IST as a naive UTC datetime for DB comparison."""
    now_ist = _dt.datetime.now(_dt.timezone.utc) + _IST_OFFSET
    today_ist_midnight = _dt.datetime.combine(now_ist.date(), _dt.time.min)
    return today_ist_midnight - _IST_OFFSET  # convert back to UTC (naive)


def _build_headline_map():
    """Return ticker→top_headline from the web cache."""
    news = web_data.get("news") or []
    ticker_headline: dict = {}
    for item in news:
        t = item.get("ticker")
        if t and t not in ticker_headline and item.get("title"):
            ticker_headline[t] = item["title"]
    return ticker_headline


def _make_reason(ticker: str | None, message: str, ticker_headline: dict) -> str:
    if not ticker:
        return message
    headline = ticker_headline.get(ticker)
    # Read the move straight out of this alert's own message (the value that
    # was true when the alert fired), not a freshly re-fetched live price —
    # the live price has usually moved on by the time this is rendered,
    # which used to produce contradictions like "+3.58% price move" paired
    # with a reason saying the stock "declined 1.15%".
    m = _PCT_IN_MESSAGE.search(message)
    if m:
        pct = float(m.group(1))
        direction = "down" if pct < 0 else "up"
        verb = "declined" if direction == "down" else "gained"
        pressure = (
            "Selling pressure exceeded buyers across the session."
            if direction == "down"
            else "Strong buying interest drove the price higher."
        )
        base = f"Stock {verb} {abs(pct):.2f}% intraday. {pressure}"
    else:
        base = message
    if headline:
        return f"{base} Latest news: {headline[:120]}."
    return f"{base} No specific news catalyst found in tracked feeds."


@router.get("/alerts")
def list_alerts(
    db: Session = Depends(get_db),
    ticker: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
):
    q = db.query(Alert).filter(Alert.created_at >= _today_start_utc())
    if ticker:
        q = q.filter(Alert.ticker == ticker.upper())
    if category:
        q = q.filter(Alert.category == category)
    alerts = q.order_by(Alert.created_at.desc()).limit(limit).all()

    if not alerts:
        cached = web_data.get("alerts") or []
        today_str = (_dt.datetime.now(_dt.timezone.utc) + _IST_OFFSET).strftime("%Y-%m-%d")
        filtered = [a for a in cached if (a.get("created_at") or "").startswith(today_str)]
        if ticker:
            filtered = [a for a in filtered if a.get("ticker") == ticker.upper()]
        if category:
            filtered = [a for a in filtered if a.get("category") == category]
        return filtered[:limit]

    ticker_headline = _build_headline_map()

    return [
        {
            "id":         a.id,
            "ticker":     a.ticker,
            "category":   a.category,
            "severity":   a.severity,
            "message":    a.message,
            "reason":     _make_reason(a.ticker, a.message, ticker_headline),
            "used_ai":    bool(a.source_used_ai),
            "created_at": (a.created_at.isoformat() + "Z") if a.created_at else None,
        }
        for a in alerts
    ]
