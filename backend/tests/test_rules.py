from app.analysis import rules


def test_price_move_with_volume_spike_needs_ai():
    signal = rules.evaluate_price("AAPL", pct_change=5.0, volume=2_000_000, avg_volume=500_000)
    assert signal is not None
    assert signal.needs_ai is True
    assert signal.severity == "critical"


def test_price_move_without_volume_spike_is_warning():
    signal = rules.evaluate_price("AAPL", pct_change=4.0, volume=500_000, avg_volume=500_000)
    assert signal is not None
    assert signal.needs_ai is False
    assert signal.severity == "warning"


def test_small_price_move_is_ignored():
    signal = rules.evaluate_price("AAPL", pct_change=0.5, volume=500_000, avg_volume=500_000)
    assert signal is None


def test_negative_news_sentiment_triggers_signal():
    signal = rules.evaluate_news("TSLA", "Company faces major lawsuit", sentiment=-0.7)
    assert signal is not None
    assert signal.category == "news"


def test_neutral_news_sentiment_no_signal():
    signal = rules.evaluate_news("TSLA", "Company releases quarterly update", sentiment=0.1)
    assert signal is None


def test_news_without_ticker_match_no_signal():
    signal = rules.evaluate_news(None, "Generic market commentary", sentiment=-0.9)
    assert signal is None


def test_trending_social_post_triggers_signal():
    signal = rules.evaluate_social("RELIANCE.NS", "To the moon", score=1, sentiment=0.5)
    assert signal is not None
    assert signal.needs_ai is False


def test_highly_trending_social_post_needs_ai():
    signal = rules.evaluate_social("RELIANCE.NS", "To the moon", score=2, sentiment=0.5)
    assert signal is not None
    assert signal.needs_ai is True
