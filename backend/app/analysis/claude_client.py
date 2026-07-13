"""Cost-aware wrapper around the Claude API, with local Ollama as a second
tier wherever ANTHROPIC_API_KEY isn't configured.

- Haiku is used for cheap triage/classification of every escalated signal.
- Sonnet is used only for the subset of signals Haiku flags as high-impact.
- An in-memory cache (keyed by a hash of the signal content) avoids paying
  twice for near-duplicate signals within the same process lifetime.
- Every function tries Claude first, then local Ollama (`ollama_client.py`)
  if no API key is configured, then returns None — callers fall back to
  their own rule-based text on a None return. Same never-raise contract as
  the chat endpoint's Claude → Ollama → keyword fallback ladder, just
  applied to every AI touchpoint in the app, not only /api/chat.
"""

import hashlib
import logging

from anthropic import Anthropic

from app.analysis import ollama_client
from app.config import settings

logger = logging.getLogger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"

_cache: dict[str, str] = {}


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _client() -> Anthropic | None:
    if not settings.anthropic_api_key:
        return None
    return Anthropic(api_key=settings.anthropic_api_key)


def _ollama_fallback(instruction: str) -> str | None:
    """Second tier, used only when `_client()` is None. Returns None (never
    raises) if Ollama isn't reachable either, in which case the caller's
    own rule-based fallback takes over — the same three-tier ladder
    routes_chat.py already uses for the chat assistant."""
    return ollama_client.chat_completion("", [{"role": "user", "content": instruction}])


def triage_and_explain(ticker: str, category: str, reason: str) -> tuple[str, bool]:
    """Returns (explanation, is_high_impact). Falls back to the raw rule
    reason with is_high_impact=False if neither Claude nor Ollama is
    available.
    """
    prompt = f"Ticker: {ticker}\nCategory: {category}\nSignal: {reason}"
    key = _cache_key(prompt)
    if key in _cache:
        return _cache[key], False

    instruction = (
        "You are a market alert triage assistant. Given a signal, "
        "write one concise sentence explaining the likely market "
        "relevance, then on a new line write HIGH_IMPACT: yes or "
        "HIGH_IMPACT: no.\n\n" + prompt
    )

    client = _client()
    if client is None:
        text = _ollama_fallback(instruction)
        if text is None:
            return reason, False
        explanation = text.split("HIGH_IMPACT:")[0].strip()
        is_high_impact = "yes" in text.split("HIGH_IMPACT:")[-1].lower()
        _cache[key] = explanation
        return explanation, is_high_impact

    try:
        triage = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=150,
            messages=[{"role": "user", "content": instruction}],
        )
        text = triage.content[0].text
        explanation = text.split("HIGH_IMPACT:")[0].strip()
        is_high_impact = "yes" in text.split("HIGH_IMPACT:")[-1].lower()
    except Exception:
        logger.exception("Claude triage call failed")
        return reason, False

    if is_high_impact:
        explanation = _deep_dive(client, prompt) or explanation

    _cache[key] = explanation
    return explanation, is_high_impact


def recommend_reason(ticker: str, label: str, rule_reason: str) -> str | None:
    """One-line, plain-English gloss on a rule-computed Buy/Hold/Sell pick.

    Only called for the handful of tickers actually displayed on the
    recommendations panel (not the full watchlist) to bound spend. Returns
    None (never raises) if neither Claude nor Ollama is available —
    callers should fall back to `rule_reason` on a None return, same
    convention as `triage_and_explain`.
    """
    prompt = f"Ticker: {ticker}\nRecommendation: {label}\nRule-based signal: {rule_reason}"
    key = _cache_key("recommend:" + prompt)
    if key in _cache:
        return _cache[key]

    instruction = (
        "You are a market analyst assistant. Given a rule-based "
        "stock recommendation and the signal behind it, write one "
        "concise, plain-English sentence (no disclaimers, no "
        "repeating the ticker name) explaining the reasoning.\n\n"
        + prompt
    )

    client = _client()
    if client is None:
        explanation = _ollama_fallback(instruction)
        if explanation is None:
            return None
        _cache[key] = explanation
        return explanation

    try:
        resp = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=60,
            messages=[{"role": "user", "content": instruction}],
        )
        explanation = resp.content[0].text.strip()
    except Exception:
        logger.exception("Claude recommend_reason call failed")
        return None

    _cache[key] = explanation
    return explanation


def generate_briefing(context: str, has_anomalies: bool) -> tuple[str, str] | None:
    """(headline, summary) plain-English market briefing from a structured
    text context assembled by OrchestratorAgent across every other agent's
    latest output. Haiku by default; escalates to Sonnet only when
    `has_anomalies` is True — same Haiku-then-Sonnet gating as
    `triage_and_explain`, just keyed off OrchestratorAgent's rule-based
    anomaly detection instead of a single alert signal. Returns None
    (never raises) if neither Claude nor Ollama is available; the caller
    falls back to a deterministic templated summary. Ollama doesn't get a
    Sonnet-equivalent escalation — it's a single local model regardless of
    `has_anomalies`.
    """
    key = _cache_key("briefing:" + context)
    if key in _cache:
        cached = _cache[key]
        headline, _, summary = cached.partition("\n")
        return headline, summary

    instruction = (
        "You are writing a market briefing for an Indian (NSE) stock "
        "dashboard from the structured data below, gathered from "
        "several independent monitoring agents. Write a short "
        "headline (under 12 words) on the first line, then on the "
        "following lines a 3-5 sentence plain-English briefing. No "
        "disclaimers, no markdown formatting.\n\n" + context
    )

    client = _client()
    if client is None:
        text = _ollama_fallback(instruction)
        if text is None:
            return None
        headline, _, summary = text.strip().partition("\n")
        summary = summary.strip() or headline
        _cache[key] = f"{headline}\n{summary}"
        return headline, summary

    model = SONNET_MODEL if has_anomalies else HAIKU_MODEL
    max_tokens = 300 if has_anomalies else 150
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": instruction}],
        )
        text = resp.content[0].text.strip()
        headline, _, summary = text.partition("\n")
        summary = summary.strip() or headline
    except Exception:
        logger.exception("Claude briefing call failed")
        return None

    _cache[key] = f"{headline}\n{summary}"
    return headline, summary


def explain_relevance(kind: str, description: str) -> str | None:
    """One-line 'why this might matter to an investor' gloss on a single
    rule-fetched event — a corporate action, a regulatory filing, or an
    economic-calendar release. Shared across those three agents rather than
    one function per agent, since the prompt shape is identical; only
    `kind` (used in the prompt, not the cache key namespace) differs.
    Callers should bound calls to a small number of most-recent items (not
    the whole feed) to keep spend down — same discipline as
    `recommend_reason`. Returns None (never raises) if neither Claude nor
    Ollama is available; callers should fall back to their own rule-based
    reason rather than leaving `ai_reason` unset.
    """
    prompt = f"{kind}: {description}"
    key = _cache_key("relevance:" + prompt)
    if key in _cache:
        return _cache[key]

    instruction = (
        "In one short, plain-English sentence (under 25 words, no "
        "disclaimers), explain why this might matter to an Indian "
        f"equity investor.\n\n{prompt}"
    )

    client = _client()
    if client is None:
        explanation = _ollama_fallback(instruction)
        if explanation is None:
            return None
        _cache[key] = explanation
        return explanation

    try:
        resp = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=60,
            messages=[{"role": "user", "content": instruction}],
        )
        explanation = resp.content[0].text.strip()
    except Exception:
        logger.exception("Claude explain_relevance call failed")
        return None

    _cache[key] = explanation
    return explanation


def summarize_context(topic: str, context: str, max_tokens: int = 150) -> str | None:
    """Short plain-English paragraph summarizing a block of structured or
    semi-structured text — used for the YouTube analyst sentiment roll-up
    and the FII/DII daily narrative. One call per agent run (or per new
    trading day for FII/DII), never per displayed row, to bound spend.
    Returns None (never raises) if neither Claude nor Ollama is available;
    callers should fall back to their own rule-based summary.
    """
    key = _cache_key(f"summarize:{topic}:{context}")
    if key in _cache:
        return _cache[key]

    instruction = (
        f"Summarize the following {topic} in 2-4 plain-English "
        "sentences for an Indian equity investor. No disclaimers, "
        f"no markdown formatting.\n\n{context}"
    )

    client = _client()
    if client is None:
        summary = _ollama_fallback(instruction)
        if summary is None:
            return None
        _cache[key] = summary
        return summary

    try:
        resp = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": instruction}],
        )
        summary = resp.content[0].text.strip()
    except Exception:
        logger.exception("Claude summarize_context call failed")
        return None

    _cache[key] = summary
    return summary


def _deep_dive(client: Anthropic, prompt: str) -> str | None:
    try:
        deep = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "This market signal was flagged as high impact. Provide a "
                        "2-3 sentence analysis of why it matters and what to watch "
                        "for next.\n\n" + prompt
                    ),
                }
            ],
        )
        return deep.content[0].text.strip()
    except Exception:
        logger.exception("Claude deep-dive call failed")
        return None
