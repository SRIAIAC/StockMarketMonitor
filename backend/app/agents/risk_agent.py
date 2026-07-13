"""Composite market risk score (0-100) from data already collected elsewhere
in the pipeline — no new external dependency:

- India VIX and whole-market advance/decline breadth both come from the same
  NSE `allIndices` payload `routes_market._fetch_nse_sectors()` already
  calls for sector breadth.
- Watchlist volatility and volume-spike count are computed from our own
  `Price` history.

The weights/normalization ranges below are a starting point, not a
back-tested model — flagged as needing recalibration once real score
history accrues, same spirit as the threshold constants in analysis/rules.py.
"""

import datetime as dt
import logging
import statistics

from sqlalchemy import func

from app.agents.base import BaseAgent
from app.analysis.rules import VOLUME_SPIKE_RATIO
from app.api.nse_client import nse_get
from app.config import settings
from app.models import Price, RiskSnapshot

logger = logging.getLogger(__name__)

_ALL_INDICES_PATH = "/api/allIndices"

# India VIX has historically ranged roughly 10 (calm) to 30+ (stressed) for
# NSE; used only to normalize into a 0-100 contribution, not as a literal
# forecast band.
_VIX_LOW, _VIX_HIGH = 10.0, 30.0
# Cross-sectional stdev of watchlist %-change; >3% same-day dispersion is a
# genuinely turbulent session for a 15-large-cap basket.
_VOLATILITY_HIGH = 3.0

_WEIGHTS = {"vix": 0.40, "breadth": 0.25, "volatility": 0.20, "spike": 0.15}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _fetch_vix_and_breadth() -> tuple[float | None, int | None, int | None]:
    payload = nse_get(_ALL_INDICES_PATH)
    if not isinstance(payload, dict):
        return None, None, None

    vix = None
    for row in payload.get("data", []) or []:
        if (row.get("index") or "").strip().upper() == "INDIA VIX":
            vix = row.get("last")
            break

    def _int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    return vix, _int(payload.get("advances")), _int(payload.get("declines"))


def _latest_prices_for_watchlist(session) -> list[Price]:
    tickers = settings.tickers
    subq = (
        session.query(Price.ticker, func.max(Price.fetched_at).label("max_fetched"))
        .filter(Price.ticker.in_(tickers))
        .group_by(Price.ticker)
        .subquery()
    )
    return (
        session.query(Price)
        .join(subq, (Price.ticker == subq.c.ticker) & (Price.fetched_at == subq.c.max_fetched))
        .all()
    )


class RiskAgent(BaseAgent):
    name = "risk"

    def run(self) -> None:
        vix, advances, declines = _fetch_vix_and_breadth()

        session = self.session()
        try:
            prices = _latest_prices_for_watchlist(session)
            pct_changes = [p.pct_change for p in prices if p.pct_change is not None]
            volatility = statistics.pstdev(pct_changes) if len(pct_changes) >= 2 else None
            spike_count = sum(
                1
                for p in prices
                if p.avg_volume and p.volume > p.avg_volume * VOLUME_SPIKE_RATIO
            )
            spike_ratio = (spike_count / len(prices)) if prices else 0.0

            breadth_ratio = None
            norm_breadth = 0.0
            if advances is not None and declines is not None and (advances + declines) > 0:
                breadth_ratio = advances / (advances + declines)
                # 50/50 → 0 contribution; all-declines skew → max contribution.
                norm_breadth = _clamp((0.5 - breadth_ratio) / 0.5 * 100)

            norm_vix = (
                _clamp((vix - _VIX_LOW) / (_VIX_HIGH - _VIX_LOW) * 100) if vix is not None else 0.0
            )
            norm_volatility = (
                _clamp(volatility / _VOLATILITY_HIGH * 100) if volatility is not None else 0.0
            )
            norm_spike = _clamp(spike_ratio * 100)

            risk_score = _clamp(
                _WEIGHTS["vix"] * norm_vix
                + _WEIGHTS["breadth"] * norm_breadth
                + _WEIGHTS["volatility"] * norm_volatility
                + _WEIGHTS["spike"] * norm_spike
            )
            risk_label = "Low" if risk_score < 33 else "Moderate" if risk_score < 66 else "High"

            session.add(
                RiskSnapshot(
                    risk_score=round(risk_score, 1),
                    risk_label=risk_label,
                    india_vix=vix,
                    watchlist_volatility=round(volatility, 3) if volatility is not None else None,
                    advances=advances,
                    declines=declines,
                    breadth_ratio=round(breadth_ratio, 3) if breadth_ratio is not None else None,
                    volume_spike_count=spike_count,
                    computed_at=dt.datetime.utcnow(),
                )
            )
            session.commit()
        finally:
            session.close()
