from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_analyzer = SentimentIntensityAnalyzer()


def score_text(text: str) -> float:
    """Returns a compound sentiment score in [-1, 1]. Free, no LLM call."""
    if not text:
        return 0.0
    return _analyzer.polarity_scores(text)["compound"]
