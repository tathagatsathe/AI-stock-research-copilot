import asyncio

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.services.news_analysis_service import NewsAnalysisService, get_news_analysis_service
from app.services.stock_analysis_service import (
    DataFetchError,
    InvalidTickerError,
    StockAnalysisService,
    get_stock_analysis_service,
)


class StubSuccessService(StockAnalysisService):
    def analyze_stock(self, ticker: str) -> dict:
        return {
            "ticker": ticker.strip().upper(),
            "current_price": 123.45,
            "sma_50": 120.0,
            "rsi": 55.0,
        }


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


class StubNewsSuccessService(NewsAnalysisService):
    def analyze_ticker_news(self, ticker: str) -> dict:
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
    def analyze_ticker_news(self, ticker: str) -> dict:
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
    response = TestClient(app).get("/api/v1/stocks/analysis", params={"ticker": "A" * 11})
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


def test_stocks_analyze_with_news_returns_combined_payload() -> None:
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


def test_stocks_analyze_with_news_uses_fallback_when_news_fails() -> None:
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
