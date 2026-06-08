import json

import pytest

from app.services.symbol_search_service import SymbolSearchError, SymbolSearchService


def _fake_yahoo_payload() -> bytes:
    return json.dumps(
        {
            "quotes": [
                {
                    "symbol": "AAPL",
                    "shortname": "Apple Inc.",
                    "longname": "Apple Inc.",
                    "exchange": "NMS",
                    "quoteType": "EQUITY",
                },
                {
                    "symbol": "PLTR",
                    "shortname": "Palantir Technologies Inc.",
                    "longname": "Palantir Technologies Inc.",
                    "exchange": "NYQ",
                    "quoteType": "EQUITY",
                },
                {
                    "symbol": "RELIANCE.NS",
                    "shortname": "Reliance Industries Limited",
                    "exchange": "NSI",
                    "quoteType": "EQUITY",
                },
                {
                    "symbol": "BTC-USD",
                    "shortname": "Bitcoin USD",
                    "exchange": "CCC",
                    "quoteType": "CRYPTOCURRENCY",
                },
            ]
        }
    ).encode("utf-8")


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_search_filters_results_to_market(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.symbol_search_service.urlopen",
        lambda *args, **kwargs: _FakeResponse(_fake_yahoo_payload()),
    )

    svc = SymbolSearchService()
    payload = svc.search("apple", market="us_stocks", limit=5)

    assert payload["market"] == "us_stocks"
    assert payload["count"] == 2
    tickers = [row["ticker"] for row in payload["results"]]
    assert "AAPL" in tickers
    assert "PLTR" in tickers
    assert "RELIANCE.NS" not in tickers


def test_search_marks_universe_members(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.symbol_search_service.urlopen",
        lambda *args, **kwargs: _FakeResponse(_fake_yahoo_payload()),
    )

    svc = SymbolSearchService()
    payload = svc.search("apple", market="us_stocks", limit=5)
    aapl = next(row for row in payload["results"] if row["ticker"] == "AAPL")

    assert aapl["in_universe"] is True
    assert aapl["display_ticker"] == "AAPL"
    assert aapl["exchange"] == "NASDAQ"


def test_search_empty_query_returns_no_results() -> None:
    svc = SymbolSearchService()
    payload = svc.search("   ", market="us_stocks")
    assert payload["count"] == 0
    assert payload["results"] == []


def test_search_raises_when_yahoo_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*args, **kwargs):
        raise OSError("network down")

    monkeypatch.setattr("app.services.symbol_search_service.urlopen", _boom)

    svc = SymbolSearchService()
    with pytest.raises(SymbolSearchError):
        svc.search("apple", market="us_stocks")
