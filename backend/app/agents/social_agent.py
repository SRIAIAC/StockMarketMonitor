import datetime as dt
import json
import logging
import urllib.request

from app.agents.base import BaseAgent
from app.config import settings
from app.analysis.sentiment import score_text
from app.models import SocialPost

logger = logging.getLogger(__name__)

# Public, no-auth stream of recent posts for a symbol. Note: Cloudflare blocks
# httpx's TLS fingerprint here (403) but urllib.request passes fine.
STOCKTWITS_URL = "https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; StockMarketMonitor/0.1)"}


def _stocktwits_symbol(ticker: str) -> str:
    """NSE tickers use the .NS suffix (yfinance convention); StockTwits uses .NSE."""
    return ticker[:-3] + ".NSE" if ticker.endswith(".NS") else ticker


class SocialAgent(BaseAgent):
    name = "social"

    def run(self) -> None:
        session = self.session()
        # A single post often cashtags several watchlist tickers, so the same
        # message shows up in more than one symbol's stream within this run.
        # The session doesn't autoflush, so a DB dedup check alone can't see
        # rows added earlier in this same run — track them here too.
        seen_urls: set[str] = set()
        failures = 0
        try:
            for ticker in settings.tickers:
                symbol = _stocktwits_symbol(ticker)
                url = STOCKTWITS_URL.format(symbol=symbol)
                try:
                    req = urllib.request.Request(url, headers=HEADERS)
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        payload = json.loads(resp.read())
                except Exception as exc:
                    failures += 1
                    logger.debug("StockTwits lookup failed for %s: %s", ticker, exc)
                    continue

                for msg in payload.get("messages", []):
                    msg_id = msg.get("id")
                    body = msg.get("body")
                    if not msg_id or not body:
                        continue

                    post_url = f"https://stocktwits.com/message/{msg_id}"
                    if post_url in seen_urls:
                        continue
                    if session.query(SocialPost).filter_by(url=post_url).first():
                        continue
                    seen_urls.add(post_url)

                    session.add(
                        SocialPost(
                            ticker=ticker,
                            source="stocktwits",
                            title=body,
                            url=post_url,
                            score=(msg.get("likes") or {}).get("total") or 0,
                            sentiment=score_text(body),
                            fetched_at=dt.datetime.utcnow(),
                        )
                    )
            # A handful of per-ticker misses is normal flakiness; every single
            # ticker failing in the same run means StockTwits/Cloudflare is
            # broadly blocking us (seen in practice: 503 from residential IPs,
            # 403 from datacenter IPs like GCP) — worth one loud signal instead
            # of N buried per-ticker warnings nobody will scroll through.
            if settings.tickers and failures == len(settings.tickers):
                logger.warning(
                    "StockTwits appears to be blocking all %d requests this run "
                    "(Cloudflare 403/503) — no new social posts collected. This "
                    "is an upstream block, not expected to self-resolve by retrying.",
                    failures,
                )
            session.commit()
        finally:
            session.close()
