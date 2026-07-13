from app.analysis.youtube_analysis import (
    extract_companies,
    extract_recommendation,
    extract_topics,
    extract_tone,
)


def test_extract_companies_matches_known_names():
    text = "I think Reliance Industries looks strong here, and HDFC Bank is also worth watching."
    assert extract_companies(text) == ["RELIANCE.NS", "HDFCBANK.NS"]


def test_extract_companies_prefers_longer_phrase_over_substring():
    text = "Bajaj Auto announced a buyback, unlike Bajaj Finance which stayed quiet."
    tickers = extract_companies(text)
    assert "BAJAJ-AUTO.NS" in tickers
    assert "BAJFINANCE.NS" in tickers


def test_extract_companies_no_match_returns_empty():
    assert extract_companies("The weather today is sunny with light winds.") == []


def test_extract_recommendation_buy():
    assert extract_recommendation("I would say buy this stock, it's a strong accumulate here.") == "BUY"


def test_extract_recommendation_sell():
    assert extract_recommendation("Time to exit this position, I'd sell and avoid adding more.") == "SELL"


def test_extract_recommendation_none_when_no_keywords():
    assert extract_recommendation("This company reported quarterly results yesterday.") is None


def test_extract_topics_finds_earnings_and_rbi():
    text = "The company's quarterly result beat estimates. Separately, RBI kept the repo rate unchanged."
    topics = extract_topics(text)
    assert "Earnings" in topics
    assert "RBI Policy" in topics


def test_extract_tone_bullish_vs_bearish():
    bullish_tone, bullish_score = extract_tone("This stock is a fantastic buy, excellent growth, great management.")
    bearish_tone, bearish_score = extract_tone("This stock is a terrible sell, awful results, horrible outlook.")
    assert bullish_tone == "Bullish"
    assert bearish_tone == "Bearish"
    assert bullish_score > bearish_score
