import pytest

from app.services.strategy_ratings_service import StrategyRatingsService


@pytest.fixture
def ratings_service() -> StrategyRatingsService:
    return StrategyRatingsService()


def test_strategy_ratings_clamps_news_risk_keywords(ratings_service: StrategyRatingsService) -> None:
    stock = {"current_price": 150.0, "sma_50": 140.0, "rsi": 55.0, "return_20d_pct": 5.0}
    news = {
        "overall_sentiment": "bullish",
        "risk_keywords_detected": ["lawsuit"],
        "error": None,
        "articles": [{"title": "x"}],
    }
    fundamentals = {
        "coverage": "high",
        "fields": {
            "trailing_pe": 12.0,
            "price_to_book": 2.0,
            "return_on_equity": 0.25,
            "profit_margins": 0.18,
            "debt_to_equity": 40.0,
        },
    }
    macro = {"instability_score_1_10": 4}

    out = ratings_service.build(
        stock=stock,
        news=news,
        fundamentals=fundamentals,
        macro=macro,
    )

    assert out["momentum"]["score_1_10"] <= 5
    assert out["quality"]["score_1_10"] <= 5


def test_macro_stress_applies_tilt(ratings_service: StrategyRatingsService) -> None:
    stock = {"current_price": 150.0, "sma_50": 140.0, "rsi": 55.0, "return_20d_pct": 5.0}
    news = {
        "overall_sentiment": "neutral",
        "risk_keywords_detected": [],
        "error": None,
        "articles": [{"title": "x"}, {"title": "y"}, {"title": "z"}],
    }
    fundamentals = {"coverage": "partial", "fields": {"trailing_pe": 18.0}}

    low_stress = ratings_service.build(
        stock=stock,
        news=news,
        fundamentals=fundamentals,
        macro={"instability_score_1_10": 5},
    )
    high_stress = ratings_service.build(
        stock=stock,
        news=news,
        fundamentals=fundamentals,
        macro={"instability_score_1_10": 9},
    )

    assert high_stress["value"]["score_1_10"] <= low_stress["value"]["score_1_10"]
