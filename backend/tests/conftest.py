import pytest

from app.analysis import claude_client


@pytest.fixture(autouse=True)
def _no_real_ollama_calls(monkeypatch):
    """Tests must be deterministic and fast on any machine — including one
    with no local Ollama server running at all, and including CI. Without
    this, any test that exercises an agent's AI-touching code path (with
    no ANTHROPIC_API_KEY, the default in this test environment) silently
    falls through to a real network call against localhost:11434, which is
    slow and non-deterministic (confirmed live: two agent tests picked up
    ~15s combined once Ollama was added as a second tier to claude_client.py).
    Individual tests that want to exercise the Ollama path explicitly
    re-patch `_ollama_fallback` themselves (see test_claude_client.py)."""
    monkeypatch.setattr(claude_client, "_ollama_fallback", lambda instruction: None)
