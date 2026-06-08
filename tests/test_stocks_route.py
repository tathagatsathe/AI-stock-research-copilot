from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

import app.api.routes.stocks as stocks_route
from app.main import app
from app.services.news_analysis_service import NewsAnalysisService, get_news_analysis_service
from app.services.stock_analysis_service import (
    DataFetchError,
    InvalidTickerError,
    StockAnalysisService,
    get_stock_analysis_service,
)
from app.services.stock_universe_service import get_stock_universe_service
from app.services.symbol_search_service import get_symbol_search_service


class StubSuccessService(StockAnalysisService):
    def analyze_stock(self, ticker: str) -> dict:
        return {
            "ticker": ticker.strip().upper(),
            "current_price": 123.45,
            "sma_50": 120.0,
            "rsi": 55.0,
            "return_20d_pct": 2.0,
        }


def _fake_price_history() -> list[dict]:
    return [
        {"date": f"2026-01-{day:02d}", "close": 100.0 + day * 0.4}
        for day in range(1, 31)
    ] + [
        {"date": f"2026-02-{day:02d}", "close": 112.0 + day * 0.4}
        for day in range(1, 29)
    ]


def _fake_equity_bundle(ticker: str, stock_service: StockAnalysisService) -> tuple[dict, dict, dict, list]:
    sym = ticker.strip().upper()
    strategy_frameworks = {
        "buffett_quality_dcf": {
            "moat_check": {
                "five_year_avg_gross_margin_pct": None,
                "gross_margin_std_pct_points": None,
                "yearly_gross_margins_pct": [],
                "pass": None,
                "warnings": [],
            },
            "return_check": {"by_period": [], "pass_roic_above_wacc_recent": None, "warnings": []},
            "valuation_dcf": {"warnings": [], "intrinsic_value_per_share": None, "target_buy_price": None},
        },
        "magic_formula": {"earnings_yield_pct": None, "return_on_capital_pct": None},
        "garp": {"peg_ratio": None, "signal": None, "warnings": []},
        "factor_metrics": {"price_to_book": None, "momentum_6m_pct": None},
    }
    return (
        {
            "ticker": sym,
            "current_price": 123.45,
            "sma_50": 120.0,
            "rsi": 55.0,
            "return_20d_pct": 2.0,
        },
        {
            "ticker": sym,
            "source": "yfinance",
            "currency": "USD",
            "as_of": None,
            "coverage": "partial",
            "warnings": [],
            "fields": {"trailing_pe": 20.0, "dividend_yield": 0.02},
        },
        strategy_frameworks,
        _fake_price_history(),
    )


def _fake_macro_snapshot(region: str = "us") -> dict:
    return {
        "source": "yfinance",
        "region": region,
        "symbol": "^VIX",
        "vix_level": 17.5,
        "vix_change_5d_pct": -2.0,
        "volatility_regime": "normal",
        "instability_score_1_10": 5,
        "coverage": "high",
        "error": None,
    }


_DISPLAY_NAMES = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "BTC-USD": "Bitcoin",
}


def _fake_display_name(symbol: str) -> str | None:
    return _DISPLAY_NAMES.get(symbol.strip().upper())


def _patch_analyze_upstream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stocks_route, "_fetch_equity_bundle", _fake_equity_bundle)
    monkeypatch.setattr(stocks_route, "_macro_snapshot_sync", _fake_macro_snapshot)
    monkeypatch.setattr(stocks_route, "_resolve_display_name_for_symbol", _fake_display_name)


class StubInvalidTickerService(StockAnalysisService):
    def analyze_stock(self, ticker: str) -> dict:
        raise InvalidTickerError("Bad ticker")


class StubUpstreamFailureService(StockAnalysisService):
    def analyze_stock(self, ticker: str) -> dict:
        raise DataFetchError("Upstream unavailable")


class StubUnexpectedFailureService(StockAnalysisService):
    def analyze_stock(self, ticker: str) -> dict:
        raise RuntimeError("Unhandled crash")


class StubInvalidResponseService(StockAnalysisService):
    def analyze_stock(self, ticker: str) -> dict:
        return {
            "ticker": ticker.strip().upper(),
            "current_price": 123.45,
            "sma_50": 120.0,
            "rsi": 150.0,
        }


class StubNegativePriceService(StockAnalysisService):
    def analyze_stock(self, ticker: str) -> dict:
        return {
            "ticker": ticker.strip().upper(),
            "current_price": -1.0,
            "sma_50": 120.0,
            "rsi": 45.0,
        }


class StubSuccessNewsService(NewsAnalysisService):
    def analyze_ticker_news(self, ticker: str, **kwargs) -> dict:
        return {
            "source": "google_news_rss",
            "articles": [
                {
                    "title": f"{ticker} beats expectations",
                    "source": "Example News",
                    "publish_date": "",
                    "summary": "Profit growth and upgrade chatter.",
                    "sentiment": "bullish",
                    "risk_keywords": [],
                }
            ],
            "overall_sentiment": "bullish",
            "risk_keywords_detected": [],
            "error": None,
        }


class StubFallbackNewsService(NewsAnalysisService):
    def analyze_ticker_news(self, ticker: str, **kwargs) -> dict:
        return self.build_fallback_payload("Failed to fetch latest news from Google News RSS.")


class StubNewsSuccessService(NewsAnalysisService):
    def analyze_ticker_news(self, ticker: str, **kwargs) -> dict:
        return {
            "source": "google_news_rss",
            "articles": [
                {
                    "title": f"{ticker.upper()} posts profit growth",
                    "source": "Example News",
                    "publish_date": "2026-05-08T10:00:00+00:00",
                    "summary": "Strong quarter with improved guidance.",
                    "sentiment": "bullish",
                    "risk_keywords": [],
                }
            ],
            "overall_sentiment": "bullish",
            "risk_keywords_detected": [],
            "error": None,
        }


class StubNewsFailureService(NewsAnalysisService):
    def analyze_ticker_news(self, ticker: str, **kwargs) -> dict:
        raise RuntimeError("News upstream timeout")

    def build_fallback_payload(self, error_message: str) -> dict:
        return {
            "source": "google_news_rss",
            "articles": [],
            "overall_sentiment": "neutral",
            "risk_keywords_detected": [],
            "error": error_message,
        }


def test_stocks_analysis_success() -> None:
    app.dependency_overrides[get_stock_analysis_service] = lambda: StubSuccessService()
    try:
        response = TestClient(app).get("/api/v1/stocks/analysis", params={"ticker": "msft"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "MSFT"
    assert data["current_price"] == 123.45
    assert 0 <= data["rsi"] <= 100


def test_stocks_analysis_invalid_ticker_maps_to_400() -> None:
    app.dependency_overrides[get_stock_analysis_service] = lambda: StubInvalidTickerService()
    try:
        response = TestClient(app).get("/api/v1/stocks/analysis", params={"ticker": "bad"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "Bad ticker"


def test_stocks_analysis_data_fetch_error_maps_to_502() -> None:
    app.dependency_overrides[get_stock_analysis_service] = lambda: StubUpstreamFailureService()
    try:
        response = TestClient(app).get("/api/v1/stocks/analysis", params={"ticker": "AAPL"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.json()["detail"] == "Upstream unavailable"


def test_stocks_analysis_missing_ticker_query_param_returns_422() -> None:
    response = TestClient(app).get("/api/v1/stocks/analysis")
    assert response.status_code == 422


def test_stocks_analysis_ticker_too_long_returns_422() -> None:
    response = TestClient(app).get("/api/v1/stocks/analysis", params={"ticker": "A" * 21})
    assert response.status_code == 422


def test_stocks_analysis_unexpected_error_maps_to_500() -> None:
    app.dependency_overrides[get_stock_analysis_service] = lambda: StubUnexpectedFailureService()
    try:
        response = TestClient(app).get("/api/v1/stocks/analysis", params={"ticker": "AAPL"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json()["detail"] == "Unexpected error while analyzing stock."


def test_stocks_analysis_response_model_rejects_invalid_rsi_scoring_output() -> None:
    app.dependency_overrides[get_stock_analysis_service] = lambda: StubInvalidResponseService()
    try:
        response = TestClient(app, raise_server_exceptions=False).get(
            "/api/v1/stocks/analysis", params={"ticker": "AAPL"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500


def test_stocks_analysis_timeout_maps_to_504(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_in_threadpool(func, *args, **kwargs):
        await asyncio.sleep(0.02)
        return func(*args, **kwargs)

    import app.api.routes.stocks as stocks_route

    monkeypatch.setattr(stocks_route, "run_in_threadpool", fake_run_in_threadpool)
    monkeypatch.setattr(stocks_route.settings, "stock_analysis_timeout_seconds", 0.001)
    app.dependency_overrides[get_stock_analysis_service] = lambda: StubSuccessService()
    try:
        response = TestClient(app).get("/api/v1/stocks/analysis", params={"ticker": "AAPL"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 504
    assert response.json()["detail"] == "Stock analysis timed out."


def test_stocks_analysis_whitespace_ticker_maps_to_400() -> None:
    response = TestClient(app).get("/api/v1/stocks/analysis", params={"ticker": "   "})
    assert response.status_code == 400
    assert response.json()["detail"] == "Ticker symbol cannot be empty."


def test_stocks_analysis_response_model_rejects_invalid_negative_price_output() -> None:
    app.dependency_overrides[get_stock_analysis_service] = lambda: StubNegativePriceService()
    try:
        response = TestClient(app, raise_server_exceptions=False).get(
            "/api/v1/stocks/analysis", params={"ticker": "AAPL"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500


def test_stocks_analysis_runs_service_in_threadpool(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    async def fake_run_in_threadpool(func, *args, **kwargs):
        captured["func_name"] = func.__name__
        captured["kwargs"] = kwargs
        return func(*args, **kwargs)

    import app.api.routes.stocks as stocks_route

    monkeypatch.setattr(stocks_route, "run_in_threadpool", fake_run_in_threadpool)
    app.dependency_overrides[get_stock_analysis_service] = lambda: StubSuccessService()
    try:
        response = TestClient(app).get("/api/v1/stocks/analysis", params={"ticker": "aapl"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert captured["func_name"] == "analyze_stock"
    assert captured["kwargs"] == {"ticker": "aapl"}


def test_analyze_endpoint_integration_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_analyze_upstream(monkeypatch)
    app.dependency_overrides[get_stock_analysis_service] = lambda: StubSuccessService()
    app.dependency_overrides[get_news_analysis_service] = lambda: StubSuccessNewsService()
    try:
        response = TestClient(app).get("/api/v1/stocks/analyze/AAPL")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "AAPL"
    assert payload["name"] == "Apple Inc."
    assert payload["display_ticker"] == "AAPL"
    assert len(payload["price_history"]) > 0
    assert payload["price_history"][0]["date"]
    assert payload["price_history"][0]["close"] > 0
    assert payload["news_analysis"]["overall_sentiment"] == "bullish"
    assert payload["news_analysis"]["error"] is None
    assert payload["decision_brief"]["verdict"] in {"watch", "cautious", "elevated_risk"}
    assert len(payload["decision_brief"]["summary_bullets"]) == 3
    assert payload["fundamentals"]["coverage"] == "partial"
    assert payload["macro"]["instability_score_1_10"] == 5
    assert "strategy_ratings" in payload
    assert set(payload["strategy_ratings"].keys()) == {
        "value",
        "growth",
        "momentum",
        "dividend",
        "quality",
    }
    assert "strategy_frameworks" in payload
    assert "buffett_quality_dcf" in payload["strategy_frameworks"]
    assert "disclaimer" in payload and payload["disclaimer"]


def test_analyze_endpoint_integration_with_news_fallback_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_analyze_upstream(monkeypatch)
    app.dependency_overrides[get_stock_analysis_service] = lambda: StubSuccessService()
    app.dependency_overrides[get_news_analysis_service] = lambda: StubFallbackNewsService()
    try:
        response = TestClient(app).get("/api/v1/stocks/analyze/AAPL")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "AAPL"
    assert payload["news_analysis"]["articles"] == []
    assert payload["news_analysis"]["overall_sentiment"] == "neutral"
    assert payload["news_analysis"]["error"] == "Failed to fetch latest news from Google News RSS."
    assert payload["decision_brief"]["evidence_quality"] == "low"


def test_analyze_endpoint_invalid_ticker_maps_to_400(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_bundle(_ticker: str, _stock_service: StockAnalysisService) -> tuple[dict, dict, dict]:
        raise InvalidTickerError("Bad ticker")

    monkeypatch.setattr(stocks_route, "_fetch_equity_bundle", failing_bundle)
    monkeypatch.setattr(stocks_route, "_macro_snapshot_sync", _fake_macro_snapshot)

    app.dependency_overrides[get_stock_analysis_service] = lambda: StubSuccessService()
    app.dependency_overrides[get_news_analysis_service] = lambda: StubSuccessNewsService()
    try:
        response = TestClient(app).get("/api/v1/stocks/analyze/AAPL")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "Bad ticker"


def test_analyze_endpoint_ticker_too_long_returns_422() -> None:
    response = TestClient(app).get(f"/api/v1/stocks/analyze/{'A' * 21}")
    assert response.status_code == 422


def test_stocks_analyze_with_news_returns_combined_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_analyze_upstream(monkeypatch)
    app.dependency_overrides[get_stock_analysis_service] = lambda: StubSuccessService()
    app.dependency_overrides[get_news_analysis_service] = lambda: StubNewsSuccessService()
    try:
        response = TestClient(app).get("/api/v1/stocks/analyze/AAPL")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert data["news_analysis"]["overall_sentiment"] == "bullish"
    assert len(data["news_analysis"]["articles"]) == 1
    assert data["news_analysis"]["articles"][0]["title"].startswith("AAPL")
    assert "decision_brief" in data


def test_stocks_analyze_with_news_uses_fallback_when_news_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_analyze_upstream(monkeypatch)
    app.dependency_overrides[get_stock_analysis_service] = lambda: StubSuccessService()
    app.dependency_overrides[get_news_analysis_service] = lambda: StubNewsFailureService()
    try:
        response = TestClient(app).get("/api/v1/stocks/analyze/MSFT")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "MSFT"
    assert data["news_analysis"]["articles"] == []
    assert data["news_analysis"]["overall_sentiment"] == "neutral"
    assert data["news_analysis"]["error"] == "Unexpected error while analyzing news."
    assert data["decision_brief"]["verdict"] == "cautious"


def test_stocks_analyze_with_news_ticker_too_long_returns_422() -> None:
    response = TestClient(app).get("/api/v1/stocks/analyze/" + ("A" * 21))
    assert response.status_code == 422


class StubUniverseService:
    def build_snapshot(self, market: str | None = None) -> dict:
        market_key = market or "us_stocks"
        return {
            "source": "yfinance",
            "market": market_key,
            "as_of": "2026-05-10T12:00:00+00:00",
            "count": 1,
            "stocks": [
                {
                    "ticker": "AAPL",
                    "display_ticker": "AAPL",
                    "name": "Apple Inc.",
                    "price": 197.12,
                    "change_pct": 0.42,
                    "market_cap": 3e12,
                    "volume": 50_000_000,
                    "currency": "USD",
                    "exchange": "NASDAQ",
                    "asset_class": "us_equity",
                    "market": "us_stocks",
                }
            ],
            "warnings": [],
        }


class StubSearchService:
    def search(self, query: str, market: str | None = None, limit: int = 8) -> dict:
        return {
            "query": query,
            "market": market or "us_stocks",
            "count": 1,
            "results": [
                {
                    "ticker": "PLTR",
                    "display_ticker": "PLTR",
                    "name": "Palantir Technologies Inc.",
                    "exchange": "NYSE",
                    "in_universe": False,
                }
            ],
        }


def test_stock_search_endpoint_returns_suggestions() -> None:
    app.dependency_overrides[get_symbol_search_service] = lambda: StubSearchService()
    try:
        response = TestClient(app).get(
            "/api/v1/stocks/search",
            params={"q": "palantir", "market": "us_stocks"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["results"][0]["ticker"] == "PLTR"
    assert data["results"][0]["name"].startswith("Palantir")


def test_stock_universe_endpoint_returns_summary_rows() -> None:
    app.dependency_overrides[get_stock_universe_service] = lambda: StubUniverseService()
    try:
        response = TestClient(app).get("/api/v1/stocks/universe")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["stocks"][0]["ticker"] == "AAPL"
    assert data["stocks"][0]["price"] == 197.12
    assert data["stocks"][0]["market_cap"] == 3e12
    assert data["market"] == "us_stocks"


def _fake_non_equity_bundle(ticker: str, stock_service: StockAnalysisService) -> tuple[dict, dict, dict, list]:
    sym = ticker.strip().upper()
    return (
        {
            "ticker": sym,
            "current_price": 65000.0,
            "sma_50": 62000.0,
            "rsi": 58.0,
            "return_20d_pct": 4.5,
        },
        {
            "ticker": sym,
            "source": "yfinance",
            "currency": None,
            "as_of": None,
            "coverage": "low",
            "warnings": ["Fundamentals are not applicable for crypto."],
            "fields": {},
        },
        {"not_applicable": True},
        _fake_price_history(),
    )


def test_analyze_endpoint_non_equity_returns_stub_fundamentals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stocks_route, "_fetch_equity_bundle", _fake_non_equity_bundle)
    monkeypatch.setattr(stocks_route, "_macro_snapshot_sync", _fake_macro_snapshot)
    monkeypatch.setattr(stocks_route, "_resolve_display_name_for_symbol", _fake_display_name)

    app.dependency_overrides[get_stock_analysis_service] = lambda: StubSuccessService()
    app.dependency_overrides[get_news_analysis_service] = lambda: StubSuccessNewsService()
    try:
        response = TestClient(app).get("/api/v1/stocks/analyze/BTC-USD")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Bitcoin"
    assert payload["display_ticker"] == "BTC"
    assert payload["asset_class"] == "crypto"
    assert payload["fundamentals"]["coverage"] == "low"
    assert payload["strategy_frameworks"]["not_applicable"] is True
    assert payload["strategy_ratings"]["value"]["score_label"] == "not_applicable"


def test_stock_universe_invalid_market_returns_400() -> None:
    response = TestClient(app).get("/api/v1/stocks/universe", params={"market": "invalid"})
    assert response.status_code == 400
