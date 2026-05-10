import pandas as pd
import pytest

from app.services.stock_universe_service import UNIVERSE_TICKERS, StockUniverseService


def test_universe_tickers_length_is_about_fifty() -> None:
    assert len(UNIVERSE_TICKERS) == 50


def test_fetch_one_returns_change_pct(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyTicker:
        def __init__(self, symbol: str) -> None:
            self._symbol = symbol

        def history(self, **kwargs):
            return pd.DataFrame(
                {
                    "Close": [100.0, 101.0, 102.5],
                    "Volume": [1_000_000, 1_100_000, 1_200_000],
                }
            )

        @property
        def fast_info(self):
            return {
                "shortName": "Apple Inc.",
                "market_cap": 3_000_000_000_000.0,
                "currency": "USD",
                "exchange": "NMS",
            }

    monkeypatch.setattr("app.services.stock_universe_service.yf.Ticker", DummyTicker)

    row = StockUniverseService._fetch_one("AAPL")
    assert row is not None
    assert row["ticker"] == "AAPL"
    assert row["name"] == "Apple Inc."
    assert row["price"] == 102.5
    assert row["change_pct"] is not None
    expected_pct = round((102.5 / 101.0 - 1.0) * 100.0, 4)
    assert row["change_pct"] == expected_pct
    assert row["market_cap"] == pytest.approx(3e12)
    assert row["volume"] == 1_200_000
