import datetime as dt
import logging
import time

import feedparser
import httpx
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound, RequestBlocked

from app.agents.base import BaseAgent
from app.analysis import claude_client
from app.analysis.youtube_analysis import (
    extract_companies,
    extract_recommendation,
    extract_topics,
    extract_tone,
)
from app.models import YouTubeInsight, YouTubeSentimentSummary

logger = logging.getLogger(__name__)

_SUMMARY_WINDOW_DAYS = 14

# Channel IDs verified live against each channel's public YouTube page
# (canonical channelId + og:title cross-checked) — handles get squatted /
# redirected to unrelated channels, so these are pinned by ID, not @handle.
CHANNELS: dict[str, str] = {
    "CA Rachana Ranade": "UCD-qZSqFPqyx43L6gAR8qfQ",
    "SOIC": "UC0AQrC3gYBVLqIGBOvKprKg",
    "Groww": "UCbWW7i7KnwQfqp6HFg1diFw",
    "Zerodha Varsity": "UCzGQDLs9B00YkxVTZk8tDnw",
    "ET Now": "UCI_mwTKUhicNzFrhm33MzBQ",
    "CNBC-TV18": "UCmRbHAgG2k2vDUvb3xsEunQ",
}

_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
_FEED_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
}
MAX_NEW_VIDEOS_PER_CHANNEL = 2
# Prefer English transcripts for extraction quality; several of these
# channels (esp. CA Rachana Ranade) are Hindi/Hinglish, where auto-captions
# only exist in Hindi and company names come through partly transliterated
# (e.g. "Wipro" as "विp्रो") — best-effort extraction still runs on those,
# just tagged with language="hi" so the frontend can show lower confidence.
_LANGUAGE_PREFERENCE = ["en", "hi"]
# YouTube's transcript endpoint rate-limits/blocks IPs that burst many
# requests in a short window (confirmed live — a run fetching ~18 transcripts
# back-to-back got IpBlocked partway through, and subsequent scheduled runs
# kept failing until the window cooled down). Pace requests and bail out on
# the whole run the moment a block is detected, rather than burning through
# (and prolonging) the block by retrying every remaining video anyway.
_REQUEST_DELAY_SECONDS = 3


class YouTubeAgent(BaseAgent):
    name = "youtube"

    def run(self) -> None:
        session = self.session()
        try:
            existing_ids = {row[0] for row in session.query(YouTubeInsight.video_id).distinct().all()}
            seen_ids: set[str] = set()
            blocked = False

            for channel, channel_id in CHANNELS.items():
                if blocked:
                    break
                feed = self._fetch_feed(channel_id)
                if feed is None:
                    logger.warning("YouTube feed unavailable for %s after retries, skipping this cycle", channel)
                    continue
                new_count = 0
                for entry in feed.entries:
                    video_id = entry.get("yt_videoid")
                    if not video_id or video_id in existing_ids or video_id in seen_ids:
                        continue
                    if new_count >= MAX_NEW_VIDEOS_PER_CHANNEL:
                        break

                    time.sleep(_REQUEST_DELAY_SECONDS)
                    try:
                        transcript, language = self._fetch_transcript(video_id)
                    except RequestBlocked:
                        logger.warning(
                            "YouTube transcript API blocked this IP mid-run — "
                            "stopping this cycle early, will retry next scheduled run"
                        )
                        blocked = True
                        break
                    seen_ids.add(video_id)
                    new_count += 1
                    published_at = (
                        dt.datetime(*entry.published_parsed[:6]) if entry.get("published_parsed") else None
                    )
                    title = entry.get("title", "")
                    url = entry.get("link") or f"https://www.youtube.com/watch?v={video_id}"

                    tickers = extract_companies(transcript) if transcript else []
                    if not tickers:
                        # Marker row: no transcript available, or transcript had no
                        # company mentions. Either way, don't retry this video again.
                        session.add(
                            YouTubeInsight(
                                channel=channel, video_id=video_id, video_title=title,
                                video_url=url, published_at=published_at, language=language,
                                ticker=None, fetched_at=dt.datetime.utcnow(),
                            )
                        )
                        continue

                    recommendation = extract_recommendation(transcript)
                    topics = extract_topics(transcript)
                    tone, sentiment = extract_tone(transcript)

                    for ticker in tickers:
                        session.add(
                            YouTubeInsight(
                                channel=channel,
                                video_id=video_id,
                                video_title=title,
                                video_url=url,
                                published_at=published_at,
                                language=language,
                                ticker=ticker,
                                recommendation=recommendation,
                                topics=",".join(topics),
                                tone=tone,
                                sentiment=sentiment,
                                fetched_at=dt.datetime.utcnow(),
                            )
                        )
            self._store_summary(session)
            session.commit()
        finally:
            session.close()

    @staticmethod
    def _store_summary(session) -> None:
        """One AI roll-up of the current ticker-tagged insight batch — one
        Claude call per run regardless of how many videos/tickers were
        processed this cycle (not one per row), same spend discipline as
        every other AI call in this codebase."""
        since = dt.datetime.utcnow() - dt.timedelta(days=_SUMMARY_WINDOW_DAYS)
        rows = (
            session.query(YouTubeInsight)
            .filter(YouTubeInsight.fetched_at >= since, YouTubeInsight.ticker.isnot(None))
            .order_by(YouTubeInsight.fetched_at.desc())
            .limit(50)
            .all()
        )
        if not rows:
            return

        lines = [
            f"{r.ticker.replace('.NS', '')}: {r.recommendation or 'no call'}, {r.tone} "
            f"({r.channel}, {r.video_title})"
            for r in rows
        ]
        context = "\n".join(lines)
        summary = claude_client.summarize_context(
            "batch of Indian finance YouTube analyst calls on specific stocks", context
        )
        ai_generated = summary is not None
        if summary is None:
            # No API key / call failed — a rule-based roll-up beats no
            # summary at all, same "never a blank panel" convention as
            # OrchestratorAgent's fallback briefing.
            buy = sum(1 for r in rows if r.recommendation == "BUY")
            sell = sum(1 for r in rows if r.recommendation == "SELL")
            bullish = sum(1 for r in rows if r.tone == "Bullish")
            bearish = sum(1 for r in rows if r.tone == "Bearish")
            summary = (
                f"{len(rows)} stock-specific calls in the last {_SUMMARY_WINDOW_DAYS} days: "
                f"{buy} buy / {sell} sell calls, {bullish} bullish / {bearish} bearish in tone."
            )

        session.add(
            YouTubeSentimentSummary(
                summary=summary,
                ai_generated=int(ai_generated),
                computed_at=dt.datetime.utcnow(),
            )
        )

    @staticmethod
    def _fetch_feed(channel_id: str, attempts: int = 3):
        """YouTube's RSS feed endpoint is flaky under repeated polling —
        returns transient 404/500s that clear on retry (confirmed live: the
        same feed URL failed then succeeded three times in a row a few
        seconds apart). Also fetches via httpx with a real browser
        User-Agent rather than letting feedparser make its own bare request,
        since YouTube rejected at least one channel's feed for feedparser's
        default (near-empty) User-Agent while httpx-with-UA succeeded.
        """
        url = _FEED_URL.format(channel_id)
        for attempt in range(attempts):
            try:
                resp = httpx.get(url, headers=_FEED_HEADERS, timeout=12, follow_redirects=True)
                if resp.status_code == 200:
                    parsed = feedparser.parse(resp.text)
                    if parsed.entries:
                        return parsed
            except Exception:
                logger.exception("YouTube feed fetch failed for channel %s (attempt %d)", channel_id, attempt + 1)
            if attempt < attempts - 1:
                time.sleep(2)
        return None

    @staticmethod
    def _fetch_transcript(video_id: str) -> tuple[str | None, str]:
        try:
            api = YouTubeTranscriptApi()
            listing = api.list(video_id)
            transcript = None
            for lang in _LANGUAGE_PREFERENCE:
                try:
                    transcript = listing.find_transcript([lang])
                    break
                except NoTranscriptFound:
                    continue
            if transcript is None:
                transcript = next(iter(listing), None)
            if transcript is None:
                return None, "en"
            fetched = transcript.fetch()
            text = " ".join(seg.text for seg in fetched)
            return text, transcript.language_code
        except (TranscriptsDisabled, NoTranscriptFound):
            return None, "en"
        except RequestBlocked:
            raise
        except Exception:
            logger.exception("Transcript fetch failed for video %s", video_id)
            return None, "en"
