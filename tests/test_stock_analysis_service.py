import pandas as pd
import pytest

from app.services.stock_analysis_service import (
    DataFetchError,
    InvalidTickerError,
    StockAnalysisService,
    get_stock_analysis_service,
)


@pytest.fixture
def service() -> StockAnalysisService:
    return StockAnalysisService()


def _history_from_closes(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"Close": closes})


@pytest.mark.parametrize("ticker", ["AAPL;DROP", "1234", "AAPL$", "AAPL/A", "", "   "])
def test_analyze_stock_rejects_invalid_ticker_formats(
    service: StockAnalysisService, ticker: str
) -> None:
    with pytest.raises(InvalidTickerError):
        service.analyze_stock(ticker)


def test_analyze_stock_requires_enough_data_for_sma(
    service: StockAnalysisService, monkeypatch: pytest.MonkeyPatch
) -> None:
    class DummyTicker:
        def history(self, **kwargs):
            return _history_from_closes([float(i) for i in range(40)])

    monkeypatch.setattr("app.services.stock_analysis_service.yf.Ticker", lambda _: DummyTicker())

    with pytest.raises(DataFetchError):
        service.analyze_stock("AAPL")


def test_rsi_returns_50_for_flat_prices(service: StockAnalysisService) -> None:
    close_series = pd.Series([100.0] * 20)
    rsi = service._calculate_rsi(close_series, period=14)
    assert rsi == 50.0


def test_analyze_stock_success_payload_shape(service: StockAnalysisService, monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyTicker:
        def history(self, **kwargs):
            closes = [100.0 + i for i in range(60)]
            return _history_from_closes(closes)

    monkeypatch.setattr("app.services.stock_analysis_service.yf.Ticker", lambda _: DummyTicker())

    payload = service.analyze_stock("aapl")
    assert payload["ticker"] == "AAPL"
    assert isinstance(payload["current_price"], float)
    assert isinstance(payload["sma_50"], float)
    assert 0 <= payload["rsi"] <= 100


def test_analyze_stock_uses_uppercase_and_rounds_outputs(
    service: StockAnalysisService, monkeypatch: pytest.MonkeyPatch
) -> None:
    class DummyTicker:
        def history(self, **kwargs):
            closes = [100 + i * 0.3333 for i in range(60)]
            return _history_from_closes(closes)

    monkeypatch.setattr("app.services.stock_analysis_service.yf.Ticker", lambda _: DummyTicker())
    payload = service.analyze_stock(" msFt ")

    assert payload["ticker"] == "MSFT"
    assert round(payload["current_price"], 2) == payload["current_price"]
    assert round(payload["sma_50"], 2) == payload["sma_50"]


def test_analyze_stock_calculates_50_day_sma_correctly(
    service: StockAnalysisService, monkeypatch: pytest.MonkeyPatch
) -> None:
    closes = [float(i) for i in range(1, 61)]

    class DummyTicker:
        def history(self, **kwargs):
            return _history_from_closes(closes)

    monkeypatch.setattr("app.services.stock_analysis_service.yf.Ticker", lambda _: DummyTicker())
    payload = service.analyze_stock("AAPL")

    expected_sma_50 = round(sum(closes[-50:]) / 50, 2)
    assert payload["sma_50"] == expected_sma_50


def test_analyze_stock_raises_invalid_ticker_when_history_empty(
    service: StockAnalysisService, monkeypatch: pytest.MonkeyPatch
) -> None:
    class DummyTicker:
        def history(self, **kwargs):
            return pd.DataFrame()

    monkeypatch.setattr("app.services.stock_analysis_service.yf.Ticker", lambda _: DummyTicker())

    with pytest.raises(InvalidTickerError):
        service.analyze_stock("AAPL")


def test_analyze_stock_raises_invalid_ticker_when_close_column_missing(
    service: StockAnalysisService, monkeypatch: pytest.MonkeyPatch
) -> None:
    class DummyTicker:
        def history(self, **kwargs):
            return pd.DataFrame({"Open": [1.0, 2.0], "High": [1.0, 2.0]})

    monkeypatch.setattr("app.services.stock_analysis_service.yf.Ticker", lambda _: DummyTicker())

    with pytest.raises(InvalidTickerError):
        service.analyze_stock("AAPL")


def test_analyze_stock_raises_data_fetch_error_when_close_values_are_all_nan(
    service: StockAnalysisService, monkeypatch: pytest.MonkeyPatch
) -> None:
    class DummyTicker:
        def history(self, **kwargs):
            return pd.DataFrame({"Close": [float("nan")] * 60})

    monkeypatch.setattr("app.services.stock_analysis_service.yf.Ticker", lambda _: DummyTicker())

    with pytest.raises(DataFetchError):
        service.analyze_stock("AAPL")


def test_analyze_stock_raises_data_fetch_error_on_yfinance_exception(
    service: StockAnalysisService, monkeypatch: pytest.MonkeyPatch
) -> None:
    class DummyTicker:
        def history(self, **kwargs):
            raise RuntimeError("service unavailable")

    monkeypatch.setattr("app.services.stock_analysis_service.yf.Ticker", lambda _: DummyTicker())

    with pytest.raises(DataFetchError):
        service.analyze_stock("AAPL")


def test_calculate_rsi_returns_100_for_strong_uptrend(service: StockAnalysisService) -> None:
    close_series = pd.Series([float(i) for i in range(1, 40)])
    rsi = service._calculate_rsi(close_series, period=14)
    assert rsi == 100.0


def test_calculate_rsi_returns_0_for_strong_downtrend(service: StockAnalysisService) -> None:
    close_series = pd.Series([float(i) for i in range(40, 0, -1)])
    rsi = service._calculate_rsi(close_series, period=14)
    assert rsi == 0.0


def test_calculate_rsi_requires_sufficient_points(service: StockAnalysisService) -> None:
    close_series = pd.Series([100.0] * 10)
    with pytest.raises(DataFetchError):
        service._calculate_rsi(close_series, period=14)


@pytest.mark.parametrize("ticker", ["BRK.B", "RDS-A", "A1B2"])
def test_analyze_stock_accepts_supported_ticker_characters(
    service: StockAnalysisService, monkeypatch: pytest.MonkeyPatch, ticker: str
) -> None:
    class DummyTicker:
        def history(self, **kwargs):
            closes = [100.0 + i for i in range(60)]
            return _history_from_closes(closes)

    monkeypatch.setattr("app.services.stock_analysis_service.yf.Ticker", lambda _: DummyTicker())
    payload = service.analyze_stock(ticker)
    assert payload["ticker"] == ticker


def test_analyze_stock_accepts_maximum_ticker_length_of_ten(
    service: StockAnalysisService, monkeypatch: pytest.MonkeyPatch
) -> None:
    class DummyTicker:
        def history(self, **kwargs):
            closes = [100.0 + i for i in range(60)]
            return _history_from_closes(closes)

    monkeypatch.setattr("app.services.stock_analysis_service.yf.Ticker", lambda _: DummyTicker())
    payload = service.analyze_stock("ABCDEFGHIJ")
    assert payload["ticker"] == "ABCDEFGHIJ"


def test_calculate_rsi_returns_bounded_two_decimal_output_for_mixed_trend(
    service: StockAnalysisService,
) -> None:
    close_series = pd.Series(
        [100.0, 102.0, 101.0, 103.0, 104.0, 102.5, 103.5, 105.0, 104.0, 106.0, 107.0, 106.5]
    )
    rsi = service._calculate_rsi(close_series, period=5)
    assert 0 <= rsi <= 100
    assert round(rsi, 2) == rsi


def test_get_stock_analysis_service_is_cached_singleton() -> None:
    get_stock_analysis_service.cache_clear()
    first = get_stock_analysis_service()
    second = get_stock_analysis_service()
    assert first is second
