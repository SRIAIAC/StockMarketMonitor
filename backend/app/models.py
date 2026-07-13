import datetime as dt
from typing import Optional

from sqlalchemy import Integer, String, Float, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Price(Base):
    __tablename__ = "prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String, index=True, nullable=False)
    sector: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    prev_close: Mapped[float] = mapped_column(Float, nullable=False)
    pct_change: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_volume: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)


class NewsItem(Base):
    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    sentiment: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    published_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)


class SocialPost(Base):
    __tablename__ = "social_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="stocktwits")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    sentiment: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)


class EconomicEvent(Base):
    __tablename__ = "economic_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Previous/forecast context, e.g. "Prev 3.93% · Fcst 4.0%" — kept as one
    # display string rather than separate columns since it's only ever shown
    # together, never queried on.
    detail: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    release_date: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    importance: Mapped[str] = mapped_column(String, nullable=False, default="medium")
    # One-line "why this might matter" gloss, backfilled for only the most
    # recent handful of releases (see EconCalendarAgent) — never fabricated.
    ai_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)


class CorporateAction(Base):
    __tablename__ = "corporate_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String, index=True, nullable=False)
    company_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    action_type: Mapped[str] = mapped_column(String, nullable=False, default="Other")
    ex_date: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True, index=True)
    record_date: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    announcement_date: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    value: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    raw_subject: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # One-line "why this might matter" gloss, backfilled for only the most
    # recent 10 actions (see CorporateActionAgent) — never fabricated.
    ai_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)


class RegulatoryAnnouncement(Base):
    """NSE's own regulatory/compliance corporate-announcements feed — NOT
    literal SEBI EDIFAR filings (no free public API for those exists). See
    agents/README.md for why this is labeled honestly rather than as
    'SEBI filings'. Insider-trading/SAST-disclosure items are filtered out
    before they ever reach this table (agents/regulatory_announcement_agent.py)."""

    __tablename__ = "regulatory_announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String, index=True, nullable=False)
    company_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    category: Mapped[str] = mapped_column(String, nullable=False, default="Other")
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_url: Mapped[Optional[str]] = mapped_column(String, nullable=True, unique=True)
    announcement_date: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True, index=True)
    source_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # One-line "why this might matter" gloss, backfilled for only the most
    # recent 10 filings (see RegulatoryAnnouncementAgent) — never fabricated.
    ai_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)


class RiskSnapshot(Base):
    __tablename__ = "risk_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_label: Mapped[str] = mapped_column(String, nullable=False)
    india_vix: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    watchlist_volatility: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    advances: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    declines: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    breadth_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    volume_spike_count: Mapped[int] = mapped_column(Integer, default=0)
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String, index=True, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)  # Buy / Hold / Sell
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pct_change: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sector: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sentiment: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    ai_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)


class YouTubeInsight(Base):
    __tablename__ = "youtube_insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String, nullable=False)
    video_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    video_title: Mapped[str] = mapped_column(Text, nullable=False)
    video_url: Mapped[str] = mapped_column(String, nullable=False)
    published_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    language: Mapped[str] = mapped_column(String, nullable=False, default="en")
    # Null ticker = a "processed, no company mentions found" marker row, so
    # the agent doesn't burn its per-run budget re-fetching the same video's
    # transcript forever. Filtered out of the public API response.
    ticker: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    recommendation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    topics: Mapped[str] = mapped_column(String, nullable=False, default="")
    tone: Mapped[str] = mapped_column(String, nullable=False, default="Neutral")
    sentiment: Mapped[float] = mapped_column(Float, default=0.0)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    category: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False, default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source_used_ai: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)


class MarketBriefing(Base):
    """Written by OrchestratorAgent — one row per run (append-only, like
    RiskSnapshot). `anomalies`/`agents_triggered` are comma-separated for
    simplicity (no separate join table needed for a handful of short
    tokens per run)."""

    __tablename__ = "market_briefings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    headline: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    anomalies: Mapped[str] = mapped_column(Text, nullable=False, default="")
    agents_triggered: Mapped[str] = mapped_column(String, nullable=False, default="")
    ai_generated: Mapped[int] = mapped_column(Integer, default=0)
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)


class FiiDiiFlow(Base):
    """Whole-market daily net FII/DII trading activity from NSE's own
    `fiidiiTradeReact` feed (real, verified — India's actual reported
    institutional buy/sell totals in ₹ Cr, not a per-stock figure). One row
    per trading day, accumulated over time since NSE only exposes the
    latest day per call, not a historical range."""

    __tablename__ = "fii_dii_flows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_date: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, unique=True, index=True)
    fii_buy_cr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fii_sell_cr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fii_net_cr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dii_buy_cr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dii_sell_cr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dii_net_cr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class InstitutionalMention(Base):
    """Per-stock FII/FDI/DII-tagged news mentions — there is no free public
    API disclosing which specific stocks are about to receive institutional
    investment (that's forward-looking data nobody publishes), so this is
    honestly a news-derived signal: headlines that mention a watchlist
    ticker alongside FII/DII/FDI activity, not a confirmed transaction."""

    __tablename__ = "institutional_mentions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String, index=True, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)  # FII / DII / FDI
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # Not unique — like YouTubeInsight, one headline can mention more than
    # one watchlist company, and gets one row per ticker sharing the same url.
    url: Mapped[str] = mapped_column(String, nullable=False, index=True)
    sentiment: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    published_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)


class YouTubeSentimentSummary(Base):
    """AI roll-up of the current batch of `YouTubeInsight` rows — one row
    per YouTubeAgent run (append-only, like MarketBriefing), not per video.
    Bounds spend to one Claude call per 3h run regardless of how many
    videos/tickers were processed that cycle."""

    __tablename__ = "youtube_sentiment_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    ai_generated: Mapped[int] = mapped_column(Integer, default=0)
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)


class FiiDiiSummary(Base):
    """AI narrative over the current FII/DII flow trend + recent
    institutional mentions — one row per trading day (dedup on
    `trade_date`, like FiiDiiFlow), not per agent run, since the
    underlying flow figure itself only changes once/trading day."""

    __tablename__ = "fii_dii_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_date: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, unique=True, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    ai_generated: Mapped[int] = mapped_column(Integer, default=0)
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
