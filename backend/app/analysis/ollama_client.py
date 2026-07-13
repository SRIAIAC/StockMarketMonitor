"""Local Ollama chat completion — the free, no-API-key path for the MAS
chat assistant (`routes_chat.py`). Same contract as `claude_client.py`:
never raises, returns None on any failure (Ollama not installed, `ollama
serve` not running, model not pulled, timeout) so the caller can fall
through to the next tier (keyword-based reply).
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def chat_completion(system_prompt: str, messages: list[dict]) -> str | None:
    """`messages` is the running conversation (user/assistant turns, most
    recent user message last) — same shape `routes_chat.py` already builds
    for Claude, reused as-is so both providers share one history format."""
    try:
        # Two Ollama-specific gotchas, not generic LLM tuning:
        # 1. `num_ctx` defaults to 2048 tokens *regardless of the model's
        #    actual supported context* — the DB-grounded system prompt here
        #    (price table + alerts + sentiment + news) routinely runs
        #    ~4000 tokens, so without raising this the model silently never
        #    sees most of its own grounding data and hallucinates instead.
        # 2. Near-zero temperature keeps it extractive (reading the provided
        #    table back accurately) rather than creative.
        resp = httpx.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": [{"role": "system", "content": system_prompt}, *messages],
                "stream": False,
                "options": {"temperature": 0.1, "num_ctx": 8192},
            },
            timeout=90,
        )
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content")
        return content.strip() if content else None
    except Exception:
        logger.warning(
            "Ollama chat completion failed — is `ollama serve` running with '%s' pulled?",
            settings.ollama_model,
        )
        return None
