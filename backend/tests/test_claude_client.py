from app.analysis import claude_client


def test_triage_without_api_key_or_ollama_falls_back_to_raw_reason(monkeypatch):
    """Third tier: neither Claude (no key) nor Ollama (unreachable, mocked
    here rather than depending on a real local server being up — this test
    must be deterministic on any machine, CI included)."""
    monkeypatch.setattr(claude_client.settings, "anthropic_api_key", "")
    monkeypatch.setattr(claude_client, "_ollama_fallback", lambda instruction: None)
    claude_client._cache.clear()
    explanation, is_high_impact = claude_client.triage_and_explain("AAPL", "market", "raw reason text")
    assert explanation == "raw reason text"
    assert is_high_impact is False


def test_triage_without_api_key_uses_ollama_when_available(monkeypatch):
    """Second tier: no Claude key, but Ollama answers — verifies the
    HIGH_IMPACT parsing works the same way against an Ollama response as
    it does against a Claude one, without hitting a real Ollama server."""
    monkeypatch.setattr(claude_client.settings, "anthropic_api_key", "")
    monkeypatch.setattr(
        claude_client, "_ollama_fallback",
        lambda instruction: "Ollama-generated explanation.\nHIGH_IMPACT: yes",
    )
    claude_client._cache.clear()
    explanation, is_high_impact = claude_client.triage_and_explain("AAPL", "market", "raw reason text")
    assert explanation == "Ollama-generated explanation."
    assert is_high_impact is True


def test_triage_cache_hit_avoids_second_call(monkeypatch):
    monkeypatch.setattr(claude_client.settings, "anthropic_api_key", "fake-key")
    claude_client._cache.clear()
    key = claude_client._cache_key("Ticker: AAPL\nCategory: market\nSignal: cached reason")
    claude_client._cache[key] = "cached explanation"

    explanation, is_high_impact = claude_client.triage_and_explain("AAPL", "market", "cached reason")
    assert explanation == "cached explanation"
    assert is_high_impact is False
