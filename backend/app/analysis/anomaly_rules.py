"""Deterministic cross-agent anomaly detection for OrchestratorAgent.

Same philosophy as rules.py: cheap, explainable thresholds decide *what
happened* and *which agents should re-run* — Claude's only job downstream
is narrating the result into a plain-English briefing, never deciding the
trigger logic itself. Keeps the actually-consequential decision (which
agents burn API/scrape budget re-running off-cycle) fast, free, and
testable, consistent with AlertAgent's "rules first, AI only for
explanation" design (see agents/README.md).
"""

from dataclasses import dataclass, field

# A single-ticker move this large during an off-cycle check is worth
# re-scanning news/social/alerts for immediately, rather than waiting for
# the next scheduled 30-minute sweep. Higher than AlertAgent's 3% price
# threshold since this triggers extra work across multiple agents, not
# just one alert row.
PRICE_ANOMALY_PCT = 5.0

# Risk score is 0-100; a jump this large between consecutive RiskSnapshot
# rows means market conditions shifted materially since the last check.
RISK_SPIKE_DELTA = 15.0

# Market-wide (not per-ticker) news+social sentiment average over the last
# hour, VADER scale -1..+1.
SENTIMENT_CLIFF = -0.4
SENTIMENT_CLIFF_MIN_SAMPLES = 5

# Sector momentum_score is 0-100 (50 = neutral); >=85 or <=15 is an
# extreme, not just "trending" — real rotation worth re-scoring
# recommendations for.
SECTOR_SHOCK_HIGH = 85.0
SECTOR_SHOCK_LOW = 15.0

# New warning/critical alerts within a short window - more than usual
# for the size of this watchlist.
ALERT_BURST_COUNT = 3
ALERT_BURST_WINDOW_MINUTES = 15


@dataclass
class Anomaly:
    kind: str
    description: str
    severity: str  # info, warning, critical
    agents_to_trigger: list[str] = field(default_factory=list)


def detect_price_anomaly(priced_rows: list[tuple[str, float]]) -> Anomaly | None:
    """priced_rows: [(ticker, pct_change), ...] for the watchlist's latest prices."""
    if not priced_rows:
        return None
    ticker, pct = max(priced_rows, key=lambda r: abs(r[1]))
    if abs(pct) < PRICE_ANOMALY_PCT:
        return None
    direction = "surged" if pct > 0 else "dropped"
    return Anomaly(
        kind="price_move",
        description=f"{ticker.replace('.NS', '')} {direction} {pct:+.2f}% — outside the normal 30-min cycle",
        severity="critical" if abs(pct) >= PRICE_ANOMALY_PCT * 1.5 else "warning",
        agents_to_trigger=["news", "social", "alert"],
    )


def detect_risk_spike(current_score: float, previous_score: float | None) -> Anomaly | None:
    if previous_score is None:
        return None
    delta = current_score - previous_score
    if delta < RISK_SPIKE_DELTA:
        return None
    return Anomaly(
        kind="risk_spike",
        description=f"Risk score jumped {delta:+.0f} points (now {current_score:.0f}/100)",
        severity="critical" if current_score >= 66 else "warning",
        agents_to_trigger=["recommendation", "alert"],
    )


def detect_sentiment_cliff(avg_sentiment: float, sample_size: int) -> Anomaly | None:
    if sample_size < SENTIMENT_CLIFF_MIN_SAMPLES or avg_sentiment > SENTIMENT_CLIFF:
        return None
    return Anomaly(
        kind="sentiment_cliff",
        description=f"Market-wide news/social sentiment fell to {avg_sentiment:.2f} (last hour, {sample_size} items)",
        severity="warning",
        agents_to_trigger=["social", "alert"],
    )


def detect_sector_shock(sectors: list[dict]) -> Anomaly | None:
    extreme = [s for s in sectors if s.get("momentum_score", 50) >= SECTOR_SHOCK_HIGH or s.get("momentum_score", 50) <= SECTOR_SHOCK_LOW]
    if not extreme:
        return None
    s = max(extreme, key=lambda r: abs(r["momentum_score"] - 50))
    direction = "rotating sharply in" if s["momentum_score"] >= SECTOR_SHOCK_HIGH else "rotating sharply out"
    return Anomaly(
        kind="sector_shock",
        description=f"{s['sector']} is {direction} (momentum {s['momentum_score']:.0f}/100)",
        severity="info",
        agents_to_trigger=["recommendation"],
    )


def detect_alert_burst(recent_alert_count: int) -> Anomaly | None:
    if recent_alert_count < ALERT_BURST_COUNT:
        return None
    return Anomaly(
        kind="alert_burst",
        description=f"{recent_alert_count} alerts fired in the last {ALERT_BURST_WINDOW_MINUTES} minutes",
        severity="warning",
        agents_to_trigger=["recommendation", "risk"],
    )


def merge_triggered_agents(anomalies: list[Anomaly]) -> list[str]:
    """Union + dedupe, order-preserving, across every anomaly's trigger list."""
    seen: set[str] = set()
    out: list[str] = []
    for a in anomalies:
        for name in a.agents_to_trigger:
            if name not in seen:
                seen.add(name)
                out.append(name)
    return out
