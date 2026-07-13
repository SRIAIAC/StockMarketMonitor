import datetime as dt
import logging
import re

import feedparser

from app.agents.base import BaseAgent
from app.config import settings
from app.analysis.sentiment import score_text
from app.models import NewsItem

logger = logging.getLogger(__name__)

# Free RSS feeds - no API key required. "International" prefix is how the
# frontend (NewsPanel.tsx) splits the Indian vs. international columns.
FEEDS = [
    ("Google News India Markets", "https://news.google.com/rss/search?q=Indian%20stock%20market%20NSE%20BSE&hl=en-IN&gl=IN&ceid=IN:en"),
    ("Google News Nifty Sensex", "https://news.google.com/rss/search?q=Nifty%2050%20Sensex%20stocks&hl=en-IN&gl=IN&ceid=IN:en"),
    ("Google News Large Caps", "https://news.google.com/rss/search?q=Reliance%20HDFC%20Bank%20TCS%20ICICI%20Bank%20Bharti%20Airtel%20shares&hl=en-IN&gl=IN&ceid=IN:en"),
    ("Google News International Markets", "https://news.google.com/rss/search?q=Wall%20Street%20Dow%20Jones%20S%26P%20500%20Nasdaq&hl=en-US&gl=US&ceid=US:en"),
    ("Google News International Economy", "https://news.google.com/rss/search?q=Federal%20Reserve%20interest%20rates%20global%20markets&hl=en-US&gl=US&ceid=US:en"),
]


def _ticker_patterns(tickers: list[str]) -> list[tuple[str, re.Pattern]]:
    """Word-boundary regex per bare symbol (".NS" stripped) — headlines never
    include the exchange suffix, so matching the raw `"RELIANCE.NS"` string
    (the previous logic) could never succeed against any real headline; this
    was silently zero-for-zero for every NewsItem ever stored. Word-boundary
    (not a bare substring check) avoids the worst false positives short
    symbols invite, e.g. "LT" inside "MELTDOWN" or "IEX" inside a longer word."""
    return [(t, re.compile(r"\b" + re.escape(t.replace(".NS", "")) + r"\b")) for t in tickers]


class NewsAgent(BaseAgent):
    name = "news"

    def run(self) -> None:
        patterns = _ticker_patterns(settings.tickers)
        session = self.session()
        # A story can be picked up by more than one feed; the session
        # doesn't autoflush, so a DB dedup check alone can't see rows added
        # earlier in this same run (see the identical bug fixed in
        # social_agent.py) — track them here too.
        seen_urls: set[str] = set()
        try:
            for source, url in FEEDS:
                feed = feedparser.parse(url)
                for entry in feed.entries[:30]:
                    title = entry.get("title", "")
                    link = entry.get("link")
                    if not link:
                        continue
                    if link in seen_urls:
                        continue
                    if session.query(NewsItem).filter_by(url=link).first():
                        continue
                    seen_urls.add(link)

                    title_upper = title.upper()
                    matched_ticker = next(
                        (t for t, pattern in patterns if pattern.search(title_upper)), None
                    )

                    published_at = None
                    if entry.get("published_parsed"):
                        published_at = dt.datetime(*entry.published_parsed[:6])

                    session.add(
                        NewsItem(
                            ticker=matched_ticker,
                            source=source,
                            title=title,
                            url=link,
                            sentiment=score_text(title),
                            published_at=published_at,
                            fetched_at=dt.datetime.utcnow(),
                        )
                    )
            session.commit()
        finally:
            session.close()
