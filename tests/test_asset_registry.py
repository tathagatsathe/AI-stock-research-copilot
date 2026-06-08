import pytest

from app.services.asset_registry import (
    COMMODITY_TICKERS,
    CRYPTO_TICKERS,
    FOREX_TICKERS,
    GLOBAL_INDEX_TICKERS,
    AssetClass,
    INDIA_UNIVERSE_TICKERS,
    InvalidSymbolError,
    MARKET_UNIVERSES,
    SYMBOL_DISPLAY_NAMES,
    US_UNIVERSE_TICKERS,
    classify_asset,
    display_exchange,
    display_ticker,
    is_equity_asset,
    macro_region_for_asset,
    normalize_symbol,
    resolve_display_name,
    resolve_market,
)


@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("AAPL", AssetClass.US_EQUITY),
        ("RELIANCE.NS", AssetClass.INDIA_EQUITY),
        ("TCS.BO", AssetClass.INDIA_EQUITY),
        ("^NSEI", AssetClass.GLOBAL_INDEX),
        ("EURUSD=X", AssetClass.FOREX),
        ("BTC-USD", AssetClass.CRYPTO),
        ("GC=F", AssetClass.COMMODITY),
    ],
)
def test_classify_asset(symbol: str, expected: AssetClass) -> None:
    assert classify_asset(symbol) == expected


@pytest.mark.parametrize(
    "symbol",
    ["^NSEI", "BTC-USD", "USDINR=X", "RELIANCE.NS", "HDFCBANK.NS", "GC=F"],
)
def test_normalize_symbol_accepts_multi_market_symbols(symbol: str) -> None:
    assert normalize_symbol(symbol) == symbol.upper()
    assert normalize_symbol(f" {symbol.lower()} ") == symbol.upper()


@pytest.mark.parametrize("symbol", ["", "   ", "A" * 21, "AAPL$", "1234"])
def test_normalize_symbol_rejects_invalid(symbol: str) -> None:
    with pytest.raises(InvalidSymbolError):
        normalize_symbol(symbol)


def test_resolve_market_defaults_to_us_stocks() -> None:
    assert resolve_market(None) == "us_stocks"
    assert resolve_market("") == "us_stocks"


def test_resolve_market_rejects_unknown() -> None:
    with pytest.raises(InvalidSymbolError):
        resolve_market("mars_stocks")


def test_market_universes_cover_all_tabs() -> None:
    assert len(US_UNIVERSE_TICKERS) == 50
    assert len(INDIA_UNIVERSE_TICKERS) >= 25
    assert set(MARKET_UNIVERSES.keys()) == {
        "us_stocks",
        "india_stocks",
        "global_indices",
        "forex",
        "crypto",
        "commodities",
    }


def test_is_equity_asset() -> None:
    assert is_equity_asset(AssetClass.US_EQUITY)
    assert is_equity_asset(AssetClass.INDIA_EQUITY)
    assert not is_equity_asset(AssetClass.CRYPTO)


def test_macro_region_for_asset() -> None:
    assert macro_region_for_asset(AssetClass.INDIA_EQUITY) == "india"
    assert macro_region_for_asset(AssetClass.GLOBAL_INDEX) == "global"
    assert macro_region_for_asset(AssetClass.US_EQUITY) == "us"


@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("^NSEI", "Nifty 50"),
        ("USDINR=X", "US Dollar / Indian Rupee"),
        ("BTC-USD", "Bitcoin"),
        ("GC=F", "Gold"),
    ],
)
def test_resolve_display_name_uses_curated_non_equity_names(symbol: str, expected: str) -> None:
    assert resolve_display_name(symbol) == expected


def test_resolve_display_name_prefers_yahoo_name() -> None:
    assert resolve_display_name("AAPL", "Apple Inc.") == "Apple Inc."


@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("AAPL", "AAPL"),
        ("^NSEI", "NSEI"),
        ("RELIANCE.NS", "RELIANCE"),
        ("USDINR=X", "USD/INR"),
        ("EURUSD=X", "EUR/USD"),
        ("GC=F", "GC"),
        ("BTC-USD", "BTC"),
        ("BRK-B", "BRK-B"),
    ],
)
def test_display_ticker_strips_yahoo_artifacts(symbol: str, expected: str) -> None:
    assert display_ticker(symbol) == expected


def test_display_exchange_maps_yahoo_codes() -> None:
    assert display_exchange("NMS") == "NASDAQ"
    assert display_exchange("NYQ") == "NYSE"
    assert display_exchange("CCC") == "Crypto"
    assert display_exchange("UNKNOWN") == "UNKNOWN"


def test_resolve_display_name_ignores_symbol_like_yahoo_name() -> None:
    assert resolve_display_name("BTC-USD", "BTC-USD") == "Bitcoin"
    assert resolve_display_name("^NSEI", "^NSEI") == "Nifty 50"


def test_all_non_equity_universe_symbols_have_display_names() -> None:
    for symbol in (
        *GLOBAL_INDEX_TICKERS,
        *FOREX_TICKERS,
        *CRYPTO_TICKERS,
        *COMMODITY_TICKERS,
    ):
        assert symbol in SYMBOL_DISPLAY_NAMES
        assert resolve_display_name(symbol) != symbol
