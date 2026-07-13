"""Routes for the agent-status panel, headline index bar, and agent-backed
data feeds (corporate actions, regulatory announcements, risk score,
economic events, FII/FDI/DII). Grouped in one file since they're all thin
reads over data the corresponding agents already wrote — no live external
calls here except the indices endpoint's SENSEX fallback."""

import datetime as dt
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.agents.base import agent_liveness
from app.db import SessionLocal
from app.models import (
    Alert,
    CorporateAction,
    EconomicEvent,
    FiiDiiFlow,
    FiiDiiSummary,
    InstitutionalMention,
    MarketBriefing,
    NewsItem,
    Price,
    Recommendation,
    RegulatoryAnnouncement,
    RiskSnapshot,
    SocialPost,
    YouTubeInsight,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _iso(ts: dt.datetime | None) -> str | None:
    return (ts.isoformat() + "Z") if ts else None


# ── Agent status ─────────────────────────────────────────────────────────────

# Canonical 10-agent roster (matches the product spec, Insider Trading
# deliberately excluded — see agents/README.md). Merged with live liveness
# data so the panel always shows all 10, even before any of them have run
# yet in this process (fresh startup shows active=false, last_run=null
# until the immediate background refresh completes).
AGENT_ROSTER = [
    {"key": "market", "label": "Live Market Agent"},
    {"key": "news", "label": "News Intelligence"},
    {"key": "social", "label": "Social Media Agent"},
    {"key": "corporate_action", "label": "Corporate Action"},
    {"key": "regulatory_announcement", "label": "SEBI Filings"},
    {"key": "econ_calendar", "label": "Economic Calendar"},
    {"key": "sector_rotation", "label": "Sector Rotation"},
    {"key": "risk", "label": "Risk Agent"},
    {"key": "recommendation", "label": "Recommendation"},
    {"key": "alert", "label": "Alert Agent"},
]

# Sector Rotation has no standalone BaseAgent (its momentum score is
# computed inline in routes_market._fetch_nse_sectors on every call to
# /api/sectors) — treat it as "active" whenever that route has been hit
# recently. Tracked here rather than in base.py since it isn't a BaseAgent.
_sector_rotation_last_hit: dt.datetime | None = None


def mark_sector_rotation_hit() -> None:
    global _sector_rotation_last_hit
    _sector_rotation_last_hit = dt.datetime.utcnow()


# Each model-backed agent's own table + timestamp column + a singular unit
# noun for its output caption. Used to build a *real* activity sparkline
# (row count per 3h bucket, last 24h) instead of the old decorative
# hash-seeded bars, which carried no actual information about the agent.
_AGENT_TABLES: dict[str, tuple[type, object, str]] = {
    "market": (Price, Price.fetched_at, "price update"),
    "news": (NewsItem, NewsItem.fetched_at, "headline"),
    "social": (SocialPost, SocialPost.fetched_at, "post"),
    "corporate_action": (CorporateAction, CorporateAction.fetched_at, "action"),
    "regulatory_announcement": (RegulatoryAnnouncement, RegulatoryAnnouncement.fetched_at, "filing"),
    "econ_calendar": (EconomicEvent, EconomicEvent.fetched_at, "release"),
    "risk": (RiskSnapshot, RiskSnapshot.computed_at, "snapshot"),
    "recommendation": (Recommendation, Recommendation.computed_at, "pick"),
    "alert": (Alert, Alert.created_at, "alert"),
}

_HISTORY_HOURS = 24
_BUCKET_HOURS = 3


def _bucketed_history(db: Session, ts_col, now: dt.datetime) -> tuple[list[int], int]:
    """Real row-count-per-bucket over the trailing `_HISTORY_HOURS`, oldest
    bucket first — an honest activity texture (how much this agent has
    actually written) rather than a fabricated decoration."""
    since = now - dt.timedelta(hours=_HISTORY_HOURS)
    timestamps = [row[0] for row in db.query(ts_col).filter(ts_col >= since).all() if row[0] is not None]

    n_buckets = _HISTORY_HOURS // _BUCKET_HOURS
    buckets = [0] * n_buckets
    for ts in timestamps:
        age_hours = (now - ts).total_seconds() / 3600
        idx = n_buckets - 1 - int(age_hours // _BUCKET_HOURS)
        if 0 <= idx < n_buckets:
            buckets[idx] += 1
    return buckets, len(timestamps)


def _caption(db: Session, key: str, output_24h: int, unit: str) -> str:
    # Risk/Recommendation write ~1 row per run, so a row count says little —
    # their own latest value is the meaningful "output" to show instead.
    if key == "risk":
        latest = db.query(RiskSnapshot).order_by(RiskSnapshot.computed_at.desc()).first()
        return f"Risk score {round(latest.risk_score)}/100" if latest else "No score yet"
    if key == "recommendation":
        buys = db.query(Recommendation).filter(Recommendation.label == "Buy").count()
        total = db.query(Recommendation).count()
        return f"{buys} Buy picks of {total}" if total else "No picks yet"
    plural = "" if output_24h == 1 else "s"
    return f"{output_24h} {unit}{plural} · 24h"


@router.get("/agents/status")
def agents_status(db: Session = Depends(get_db)):
    now = dt.datetime.utcnow()
    rows = []
    for agent in AGENT_ROSTER:
        key = agent["key"]

        if key == "sector_rotation":
            active = _sector_rotation_last_hit is not None and (
                now - _sector_rotation_last_hit
            ) <= dt.timedelta(minutes=90)
            rows.append({
                "name": key, "label": agent["label"], "active": active,
                "state": "active" if active else "not_active",
                "last_run": _iso(_sector_rotation_last_hit),
                "output_24h": None, "history": [], "caption": None,
            })
            continue

        # econ_calendar runs on its own 3-hour cadence (see scheduler.py),
        # not the other agents' 30-minute one — the default 90-minute
        # staleness window would otherwise call it "not active" for the
        # second half of every single cycle even though it's running
        # exactly on schedule. 200 min covers the 180-min interval plus
        # slack for scheduler jitter, matching how `orchestrator` already
        # gets its own custom threshold below for the same reason.
        stale_after = 200 if key == "econ_calendar" else 90
        active, last_run = agent_liveness(key, stale_after_minutes=stale_after)
        _, ts_col, unit = _AGENT_TABLES[key]
        history, output_24h = _bucketed_history(db, ts_col, now)
        caption = _caption(db, key, output_24h, unit)

        if not active:
            state = "not_active"
        elif key in ("risk", "recommendation") or output_24h > 0:
            state = "active"
        else:
            # Ran successfully and recently, but genuinely nothing new to
            # report this window (e.g. no corporate actions filed today) —
            # distinct from a stale/failed agent.
            state = "idle"

        rows.append({
            "name": key, "label": agent["label"], "active": active, "state": state,
            "last_run": _iso(last_run), "output_24h": output_24h,
            "history": history, "caption": caption,
        })
    return rows


# ── Headline indices ─────────────────────────────────────────────────────────

@router.get("/indices")
def indices():
    from app.api.routes_market import _fetch_nse_all_indices

    rows = _fetch_nse_all_indices()
    by_name = {r.get("index"): r for r in rows}

    out = []
    for key in ("NIFTY 50", "NIFTY BANK"):
        r = by_name.get(key)
        if r:
            out.append({
                "name": key, "last": r.get("last"),
                "change": r.get("variation"), "pct_change": r.get("percentChange"),
            })

    # SENSEX isn't in NSE's allIndices (it's a BSE index) — yfinance fallback,
    # same pattern as other yfinance fallbacks in this codebase.
    try:
        import yfinance as yf
        fi = yf.Ticker("^BSESN").fast_info
        last = fi.get("lastPrice")
        prev = fi.get("previousClose")
        if last and prev:
            out.append({
                "name": "SENSEX", "last": round(last, 2),
                "change": round(last - prev, 2),
                "pct_change": round((last - prev) / prev * 100, 2),
            })
    except Exception:
        logger.warning("SENSEX yfinance fallback failed")

    return out


# ── Corporate actions ────────────────────────────────────────────────────────

@router.get("/corporate-actions")
def corporate_actions(limit: int = Query(default=50, le=200), db: Session = Depends(get_db)):
    today = dt.datetime.utcnow() - dt.timedelta(days=7)
    rows = (
        db.query(CorporateAction)
        .filter((CorporateAction.ex_date.is_(None)) | (CorporateAction.ex_date >= today))
        .order_by(CorporateAction.ex_date.asc().nullslast())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id, "symbol": r.symbol, "company_name": r.company_name,
            "action_type": r.action_type, "ex_date": _iso(r.ex_date),
            "record_date": _iso(r.record_date), "announcement_date": _iso(r.announcement_date),
            "value": r.value, "source_url": r.source_url, "ai_reason": r.ai_reason,
        }
        for r in rows
    ]


# ── Regulatory announcements ────────────────────────────────────────────────

@router.get("/regulatory-announcements")
def regulatory_announcements(limit: int = Query(default=50, le=200), db: Session = Depends(get_db)):
    rows = (
        db.query(RegulatoryAnnouncement)
        .order_by(RegulatoryAnnouncement.announcement_date.desc().nullslast())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id, "symbol": r.symbol, "company_name": r.company_name,
            "category": r.category, "subject": r.subject,
            "attachment_url": r.attachment_url, "announcement_date": _iso(r.announcement_date),
            "source_url": r.source_url, "ai_reason": r.ai_reason,
        }
        for r in rows
    ]


# ── Risk score ───────────────────────────────────────────────────────────────

@router.get("/risk-score")
def risk_score(db: Session = Depends(get_db)):
    latest = db.query(RiskSnapshot).order_by(RiskSnapshot.computed_at.desc()).first()
    if latest is None:
        return None
    return {
        "risk_score": latest.risk_score, "risk_label": latest.risk_label,
        "india_vix": latest.india_vix, "watchlist_volatility": latest.watchlist_volatility,
        "advances": latest.advances, "declines": latest.declines,
        "breadth_ratio": latest.breadth_ratio, "volume_spike_count": latest.volume_spike_count,
        "computed_at": _iso(latest.computed_at),
    }


# ── Social sentiment gauge ───────────────────────────────────────────────────

def _score_0_100(avg_sentiment: float) -> float:
    """VADER-style sentiment is -1..+1 — rescale to a 0-100 gauge."""
    return round(max(0.0, min(100.0, (avg_sentiment + 1) / 2 * 100)), 1)


@router.get("/social-sentiment")
def social_sentiment(db: Session = Depends(get_db)):
    """Real StockTwits + YouTube sentiment only. X/Twitter and Reddit have
    no free/keyless API integrated in this codebase, so they're omitted
    entirely rather than returned as a permanent 'Not connected' stub."""
    since = dt.datetime.utcnow() - dt.timedelta(hours=24)

    st_scores = [
        s.sentiment for s in db.query(SocialPost.sentiment)
        .filter(SocialPost.fetched_at >= since, SocialPost.sentiment.isnot(None))
        .all()
    ]
    yt_scores = [
        y.sentiment for y in db.query(YouTubeInsight.sentiment)
        .filter(YouTubeInsight.fetched_at >= since, YouTubeInsight.ticker.isnot(None))
        .all()
    ]

    platforms = {
        "stocktwits": {
            "connected": True,
            "score": _score_0_100(sum(st_scores) / len(st_scores)) if st_scores else None,
            "sample_size": len(st_scores),
        },
        "youtube": {
            "connected": True,
            "score": _score_0_100(sum(yt_scores) / len(yt_scores)) if yt_scores else None,
            "sample_size": len(yt_scores),
        },
    }

    all_scores = [p["score"] for p in platforms.values() if p["connected"] and p["score"] is not None]
    overall = round(sum(all_scores) / len(all_scores), 1) if all_scores else None
    label = "Bullish" if overall is not None and overall > 55 else "Bearish" if overall is not None and overall < 45 else "Neutral"

    return {"overall_score": overall, "overall_label": label, "platforms": platforms}


# ── Market briefing (OrchestratorAgent) ──────────────────────────────────────

@router.get("/briefing")
def briefing(db: Session = Depends(get_db)):
    """Latest orchestrator-generated market briefing: a headline/summary
    synthesized across every other agent's latest output, plus which
    anomalies (if any) triggered which agents to re-run off-cycle this
    round. Note: OrchestratorAgent is intentionally not one of the 10
    agent-roster cards (it's a meta-agent over the other 10, not a data
    source of its own) — its own liveness is exposed here instead."""
    latest = db.query(MarketBriefing).order_by(MarketBriefing.computed_at.desc()).first()
    active, last_run = agent_liveness("orchestrator", stale_after_minutes=45)
    if latest is None:
        return {
            "headline": None, "summary": None, "anomalies": [], "agents_triggered": [],
            "ai_generated": False, "computed_at": None,
            "orchestrator_active": active, "orchestrator_last_run": _iso(last_run),
        }
    return {
        "headline": latest.headline,
        "summary": latest.summary,
        "anomalies": [a.strip() for a in latest.anomalies.split(";") if a.strip()],
        "agents_triggered": [a.strip() for a in latest.agents_triggered.split(",") if a.strip()],
        "ai_generated": bool(latest.ai_generated),
        "computed_at": _iso(latest.computed_at),
        "orchestrator_active": active,
        "orchestrator_last_run": _iso(last_run),
    }


# ── Economic events ──────────────────────────────────────────────────────────

@router.get("/economic-events")
def economic_events(limit: int = Query(default=20, le=100), db: Session = Depends(get_db)):
    rows = (
        db.query(EconomicEvent)
        .order_by(EconomicEvent.release_date.desc().nullslast())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id, "series_id": r.series_id, "title": r.title, "value": r.value,
            "detail": r.detail, "release_date": _iso(r.release_date), "importance": r.importance,
            "ai_reason": r.ai_reason, "fetched_at": _iso(r.fetched_at),
        }
        for r in rows
    ]


# ── FII / FDI / DII ──────────────────────────────────────────────────────────

_FII_DII_WINDOW_DAYS = 90


@router.get("/fii-dii")
def fii_dii(db: Session = Depends(get_db)):
    """Two honest parts — see FiiDiiAgent's docstring for why:
    `flows` = real whole-market daily net FII/DII trading activity (₹ Cr),
    `mentions` = news-derived per-stock FII/FDI/DII headlines, not
    confirmed transactions. Both scoped to the last 90 days."""
    since = dt.datetime.utcnow() - dt.timedelta(days=_FII_DII_WINDOW_DAYS)

    flows = (
        db.query(FiiDiiFlow)
        .filter(FiiDiiFlow.trade_date >= since)
        .order_by(FiiDiiFlow.trade_date.asc())
        .all()
    )
    mentions = (
        db.query(InstitutionalMention)
        .filter(InstitutionalMention.fetched_at >= since)
        .order_by(InstitutionalMention.published_at.desc().nullslast())
        .limit(100)
        .all()
    )
    latest_summary = (
        db.query(FiiDiiSummary)
        .order_by(FiiDiiSummary.trade_date.desc())
        .first()
    )

    return {
        "summary": latest_summary.summary if latest_summary else None,
        "summary_ai_generated": bool(latest_summary.ai_generated) if latest_summary else False,
        "summary_date": _iso(latest_summary.trade_date) if latest_summary else None,
        "flows": [
            {
                "trade_date": _iso(f.trade_date),
                "fii_net_cr": f.fii_net_cr, "dii_net_cr": f.dii_net_cr,
                "fii_buy_cr": f.fii_buy_cr, "fii_sell_cr": f.fii_sell_cr,
                "dii_buy_cr": f.dii_buy_cr, "dii_sell_cr": f.dii_sell_cr,
            }
            for f in flows
        ],
        "mentions": [
            {
                "id": m.id, "ticker": m.ticker, "category": m.category, "title": m.title,
                "url": m.url, "sentiment": m.sentiment,
                "published_at": _iso(m.published_at), "fetched_at": _iso(m.fetched_at),
            }
            for m in mentions
        ],
    }
