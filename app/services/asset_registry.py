"""
Asset classification, symbol normalization, and curated market universes.

Single source of truth for multi-market Yahoo Finance symbols.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Final

MAX_SYMBOL_LENGTH: Final[int] = 20

_SYMBOL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?:\^[A-Z0-9][A-Z0-9.\-]{0,18}|[A-Z][A-Z0-9.^=\-]{0,19})$"
)

CRYPTO_SYMBOLS: Final[frozenset[str]] = frozenset(
    {"BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "DOGE-USD"}
)


class AssetClass(str, Enum):
    US_EQUITY = "us_equity"
    INDIA_EQUITY = "india_equity"
    GLOBAL_INDEX = "global_index"
    FOREX = "forex"
    CRYPTO = "crypto"
    COMMODITY = "commodity"


class InvalidSymbolError(ValueError):
    """Raised when a symbol fails normalization or validation."""


US_UNIVERSE_TICKERS: Final[tuple[str, ...]] = (
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "NVDA",
    "META",
    "TSLA",
    "BRK-B",
    "UNH",
    "JNJ",
    "JPM",
    "V",
    "PG",
    "XOM",
    "MA",
    "HD",
    "CVX",
    "MRK",
    "ABBV",
    "BAC",
    "COST",
    "AVGO",
    "KO",
    "PEP",
    "TMO",
    "WMT",
    "MCD",
    "CSCO",
    "DIS",
    "WFC",
    "C",
    "ORCL",
    "ACN",
    "DHR",
    "VZ",
    "ADBE",
    "PM",
    "NKE",
    "TXN",
    "NEE",
    "CRM",
    "QCOM",
    "LLY",
    "AMGN",
    "HON",
    "LOW",
    "INTU",
    "IBM",
    "AMAT",
    "GE",
)

INDIA_UNIVERSE_TICKERS: Final[tuple[str, ...]] = (
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "INFY.NS",
    "ICICIBANK.NS",
    "BHARTIARTL.NS",
    "ITC.NS",
    "SBIN.NS",
    "LT.NS",
    "HINDUNILVR.NS",
    "AXISBANK.NS",
    "KOTAKBANK.NS",
    "BAJFINANCE.NS",
    "ASIANPAINT.NS",
    "MARUTI.NS",
    "TITAN.NS",
    "SUNPHARMA.NS",
    "WIPRO.NS",
    "ULTRACEMCO.NS",
    "NESTLEIND.NS",
    "POWERGRID.NS",
    "NTPC.NS",
    "ONGC.NS",
    "TATAMOTORS.NS",
    "ADANIENT.NS",
    "JSWSTEEL.NS",
    "HCLTECH.NS",
    "TECHM.NS",
    "INDUSINDBK.NS",
    "BAJAJFINSV.NS",
)

GLOBAL_INDEX_TICKERS: Final[tuple[str, ...]] = (
    "^GSPC",
    "^IXIC",
    "^DJI",
    "^FTSE",
    "^N225",
    "^NSEI",
    "^BSESN",
    "^HSI",
    "^STOXX50E",
)

FOREX_TICKERS: Final[tuple[str, ...]] = (
    "EURUSD=X",
    "GBPUSD=X",
    "USDJPY=X",
    "USDINR=X",
    "EURINR=X",
    "AUDUSD=X",
    "USDCAD=X",
    "USDCHF=X",
)

CRYPTO_TICKERS: Final[tuple[str, ...]] = (
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "BNB-USD",
)

COMMODITY_TICKERS: Final[tuple[str, ...]] = (
    "GC=F",
    "CL=F",
    "SI=F",
    "NG=F",
    "HG=F",
)

MARKET_UNIVERSES: Final[dict[str, tuple[str, ...]]] = {
    "us_stocks": US_UNIVERSE_TICKERS,
    "india_stocks": INDIA_UNIVERSE_TICKERS,
    "global_indices": GLOBAL_INDEX_TICKERS,
    "forex": FOREX_TICKERS,
    "crypto": CRYPTO_TICKERS,
    "commodities": COMMODITY_TICKERS,
}

VALID_MARKETS: Final[frozenset[str]] = frozenset(MARKET_UNIVERSES.keys())
DEFAULT_MARKET: Final[str] = "us_stocks"

# Human-readable names when Yahoo Finance omits longName/shortName (indices, forex, crypto, commodities).
SYMBOL_DISPLAY_NAMES: Final[dict[str, str]] = {
    "^GSPC": "S&P 500",
    "^IXIC": "NASDAQ Composite",
    "^DJI": "Dow Jones Industrial Average",
    "^FTSE": "FTSE 100",
    "^N225": "Nikkei 225",
    "^NSEI": "Nifty 50",
    "^BSESN": "BSE SENSEX",
    "^HSI": "Hang Seng Index",
    "^STOXX50E": "EURO STOXX 50",
    "EURUSD=X": "Euro / US Dollar",
    "GBPUSD=X": "British Pound / US Dollar",
    "USDJPY=X": "US Dollar / Japanese Yen",
    "USDINR=X": "US Dollar / Indian Rupee",
    "EURINR=X": "Euro / Indian Rupee",
    "AUDUSD=X": "Australian Dollar / US Dollar",
    "USDCAD=X": "US Dollar / Canadian Dollar",
    "USDCHF=X": "US Dollar / Swiss Franc",
    "BTC-USD": "Bitcoin",
    "ETH-USD": "Ethereum",
    "SOL-USD": "Solana",
    "BNB-USD": "BNB",
    "GC=F": "Gold",
    "CL=F": "Crude Oil",
    "SI=F": "Silver",
    "NG=F": "Natural Gas",
    "HG=F": "Copper",
}

# Friendlier exchange labels from Yahoo Finance codes.
EXCHANGE_DISPLAY_NAMES: Final[dict[str, str]] = {
    "NMS": "NASDAQ",
    "NGM": "NASDAQ",
    "NCM": "NASDAQ",
    "NYQ": "NYSE",
    "PCX": "NYSE Arca",
    "CCC": "Crypto",
    "NSI": "NSE",
    "BSE": "BSE",
    "CBT": "CME",
    "CMX": "COMEX",
    "NYM": "NYMEX",
}


def normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if not normalized:
        raise InvalidSymbolError("Ticker symbol cannot be empty.")
    if len(normalized) > MAX_SYMBOL_LENGTH:
        raise InvalidSymbolError(
            f"Ticker symbol must be at most {MAX_SYMBOL_LENGTH} characters."
        )
    if not _SYMBOL_PATTERN.fullmatch(normalized):
        raise InvalidSymbolError(
            "Ticker symbol must be a valid Yahoo symbol: letter-start (e.g. AAPL, BTC-USD) "
            "or index prefix (e.g. ^NSEI), using letters, digits, '.', '-', '^', or '='."
        )
    return normalized


def classify_asset(symbol: str) -> AssetClass:
    normalized = normalize_symbol(symbol)
    if normalized.endswith(".NS") or normalized.endswith(".BO"):
        return AssetClass.INDIA_EQUITY
    if normalized.startswith("^"):
        return AssetClass.GLOBAL_INDEX
    if normalized.endswith("=X"):
        return AssetClass.FOREX
    if normalized.endswith("=F"):
        return AssetClass.COMMODITY
    if normalized in CRYPTO_SYMBOLS or (
        normalized.endswith("-USD") and "-" in normalized
    ):
        return AssetClass.CRYPTO
    return AssetClass.US_EQUITY


def is_equity_asset(asset_class: AssetClass) -> bool:
    return asset_class in (AssetClass.US_EQUITY, AssetClass.INDIA_EQUITY)


def macro_region_for_asset(asset_class: AssetClass) -> str:
    if asset_class == AssetClass.INDIA_EQUITY:
        return "india"
    if asset_class == AssetClass.GLOBAL_INDEX:
        return "global"
    return "us"


def market_for_asset_class(asset_class: AssetClass) -> str:
    mapping = {
        AssetClass.US_EQUITY: "us_stocks",
        AssetClass.INDIA_EQUITY: "india_stocks",
        AssetClass.GLOBAL_INDEX: "global_indices",
        AssetClass.FOREX: "forex",
        AssetClass.CRYPTO: "crypto",
        AssetClass.COMMODITY: "commodities",
    }
    return mapping[asset_class]


def display_ticker(symbol: str) -> str:
    """Human-friendly ticker for UI; raw Yahoo symbol stays in `ticker` for API calls."""
    normalized = symbol.strip().upper()
    if normalized.startswith("^"):
        return normalized[1:]
    if normalized.endswith(".NS") or normalized.endswith(".BO"):
        return normalized.rsplit(".", 1)[0]
    if normalized.endswith("=X"):
        pair = normalized[:-2]
        if len(pair) == 6:
            return f"{pair[:3]}/{pair[3:]}"
        return pair
    if normalized.endswith("=F"):
        return normalized[:-2]
    if normalized.endswith("-USD"):
        return normalized[:-4]
    return normalized


def display_exchange(exchange: str | None) -> str | None:
    if exchange is None or not exchange.strip():
        return None
    key = exchange.strip().upper()
    return EXCHANGE_DISPLAY_NAMES.get(key, key)


def resolve_display_name(symbol: str, yahoo_name: str | None = None) -> str:
    """Return a human-readable asset name; keeps the ticker separate in API payloads."""
    normalized = symbol.strip().upper()
    if yahoo_name and yahoo_name.strip():
        cleaned = yahoo_name.strip()
        if cleaned.upper() != normalized:
            return cleaned
    return SYMBOL_DISPLAY_NAMES.get(normalized, normalized)


def resolve_market(market: str | None) -> str:
    if market is None or market == "":
        return DEFAULT_MARKET
    key = market.strip().lower()
    if key not in VALID_MARKETS:
        raise InvalidSymbolError(
            f"Unknown market '{market}'. Valid values: {', '.join(sorted(VALID_MARKETS))}."
        )
    return key
