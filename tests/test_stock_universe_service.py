import pandas as pd
import pytest

from app.services.asset_registry import MARKET_UNIVERSES, resolve_display_name
from app.services.stock_universe_service import UNIVERSE_TICKERS, StockUniverseService


def test_universe_tickers_length_is_about_fifty() -> None:
    assert len(UNIVERSE_TICKERS) == 50


def test_market_universe_sizes() -> None:
    assert len(MARKET_UNIVERSES["india_stocks"]) >= 25
    assert len(MARKET_UNIVERSES["global_indices"]) >= 8
    assert len(MARKET_UNIVERSES["forex"]) >= 5
    assert len(MARKET_UNIVERSES["crypto"]) >= 4
    assert len(MARKET_UNIVERSES["commodities"]) >= 5


def test_build_snapshot_includes_market_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyTicker:
        def __init__(self, symbol: str) -> None:
            self._symbol = symbol

        def history(self, **kwargs):
            return pd.DataFrame({"Close": [100.0, 101.0], "Volume": [1000, 1100]})

        @property
        def fast_info(self):
            return {"shortName": "Test", "currency": "USD", "exchange": "NMS"}

    monkeypatch.setattr("app.services.stock_universe_service.yf.Ticker", DummyTicker)

    svc = StockUniverseService()
    payload = svc.build_snapshot("forex")
    assert payload["market"] == "forex"
    assert payload["count"] == len(MARKET_UNIVERSES["forex"])
    assert payload["stocks"][0]["asset_class"] == "forex"
    assert payload["stocks"][0]["market"] == "forex"


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

    row = StockUniverseService._fetch_one("AAPL", "us_stocks")
    assert row is not None
    assert row["ticker"] == "AAPL"
    assert row["asset_class"] == "us_equity"
    assert row["market"] == "us_stocks"
    assert row["name"] == "Apple Inc."
    assert row["price"] == 102.5
    assert row["change_pct"] is not None
    expected_pct = round((102.5 / 101.0 - 1.0) * 100.0, 4)
    assert row["change_pct"] == expected_pct
    assert row["market_cap"] == pytest.approx(3e12)
    assert row["volume"] == 1_200_000


def test_fetch_one_prefers_long_name(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyTicker:
        def history(self, **kwargs):
            return pd.DataFrame({"Close": [100.0], "Volume": [1000]})

        @property
        def fast_info(self):
            return {
                "shortName": "Apple",
                "longName": "Apple Inc.",
                "currency": "USD",
            }

    monkeypatch.setattr("app.services.stock_universe_service.yf.Ticker", lambda _s: DummyTicker())

    row = StockUniverseService._fetch_one("AAPL", "us_stocks")
    assert row is not None
    assert row["name"] == "Apple Inc."


def test_fetch_one_uses_curated_name_for_crypto_without_yahoo_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyTicker:
        def history(self, **kwargs):
            return pd.DataFrame({"Close": [65000.0, 66000.0], "Volume": [1000, 1100]})

        @property
        def fast_info(self):
            return {"currency": "USD"}

    monkeypatch.setattr("app.services.stock_universe_service.yf.Ticker", lambda _s: DummyTicker())

    row = StockUniverseService._fetch_one("BTC-USD", "crypto")
    assert row is not None
    assert row["ticker"] == "BTC-USD"
    assert row["display_ticker"] == "BTC"
    assert row["name"] == resolve_display_name("BTC-USD")
    assert row["name"] == "Bitcoin"
