from __future__ import annotations

from app.services.decision_brief_service import DecisionBriefService


def _stock(price: float = 120.0, sma: float = 115.0, rsi: float = 50.0, ticker: str = "TEST") -> dict:
    return {
        "ticker": ticker,
        "current_price": price,
        "sma_50": sma,
        "rsi": rsi,
    }


def _news(
    *,
    sentiment: str = "neutral",
    articles: list | None = None,
    risk_kw: list | None = None,
    error: str | None = None,
) -> dict:
    return {
        "source": "google_news_rss",
        "articles": articles or [],
        "overall_sentiment": sentiment,
        "risk_keywords_detected": risk_kw or [],
        "error": error,
    }


def test_watch_when_aligned_bullish_and_uptrend() -> None:
    svc = DecisionBriefService()
    out = svc.build(
        stock=_stock(price=120, sma=115, rsi=55),
        news=_news(sentiment="bullish", articles=[{"title": "t", "risk_keywords": []}]),
    )
    assert out["verdict"] == "watch"
    assert out["evidence_quality"] in {"high", "medium", "low"}


def test_elevated_risk_on_keyword() -> None:
    svc = DecisionBriefService()
    out = svc.build(
        stock=_stock(),
        news=_news(
            sentiment="neutral",
            risk_kw=["lawsuit"],
            articles=[],
        ),
    )
    assert out["verdict"] == "elevated_risk"
    assert any("lawsuit" in r.lower() for r in out["top_risks"])


def test_cautious_on_news_error() -> None:
    svc = DecisionBriefService()
    out = svc.build(
        stock=_stock(),
        news=_news(error="upstream timeout"),
    )
    assert out["verdict"] == "cautious"
    assert out["evidence_quality"] == "low"


def test_cautious_on_contradiction_price_below_sma_bullish_news() -> None:
    svc = DecisionBriefService()
    out = svc.build(
        stock=_stock(price=100, sma=110, rsi=45),
        news=_news(sentiment="bullish", articles=[{}]),
    )
    assert out["verdict"] == "cautious"


def test_tension_when_bearish_news_but_above_sma() -> None:
    svc = DecisionBriefService()
    out = svc.build(
        stock=_stock(price=130, sma=110, rsi=45),
        news=_news(sentiment="bearish", articles=[{}]),
    )
    assert out["verdict"] == "cautious"
    assert any("50-day" in t.lower() or "headlines" in t.lower() for t in out["tensions"])
