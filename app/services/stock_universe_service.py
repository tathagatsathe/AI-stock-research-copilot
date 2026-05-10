"""
Curated equity universe snapshot for list/grid UIs (Yahoo Finance via yfinance).

Symbols are a fixed US large-cap set (~50) — not a live index membership feed.
"""

from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Final

import yfinance as yf

logger = logging.getLogger(__name__)

SOURCE: Final[str] = "yfinance"

# ~50 liquid US names for a compact dashboard; expand later if needed.
UNIVERSE_TICKERS: Final[tuple[str, ...]] = (
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

_MAX_WORKERS: Final[int] = 12


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def _mapping_get(mapping: Any, key: str) -> Any:
    try:
        if hasattr(mapping, "get"):
            return mapping.get(key)
    except Exception:
        return None
    return None


class StockUniverseService:
    def build_snapshot(self) -> dict[str, Any]:
        warnings: list[str] = []
        rows: list[dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = {pool.submit(self._fetch_one, sym): sym for sym in UNIVERSE_TICKERS}
            for fut in as_completed(futures):
                sym = futures[fut]
                try:
                    row = fut.result()
                    if row:
                        rows.append(row)
                    else:
                        warnings.append(f"No price history returned for {sym}.")
                except Exception:
                    logger.exception("Universe row failed for %s", sym)
                    warnings.append(f"Failed to load {sym}.")

        rows.sort(
            key=lambda r: (
                0 if r.get("market_cap") is not None else 1,
                -(r.get("market_cap") or 0.0),
            )
        )

        return {
            "source": SOURCE,
            "as_of": datetime.now(timezone.utc).isoformat(),
            "count": len(rows),
            "stocks": rows,
            "warnings": warnings[:25],
        }

    @staticmethod
    def _fetch_one(symbol: str) -> dict[str, Any] | None:
        t = yf.Ticker(symbol)
        hist = t.history(period="10d", interval="1d", auto_adjust=False)

        if hist.empty or "Close" not in hist.columns:
            return None

        closes = hist["Close"].dropna()
        if closes.empty:
            return None

        price_raw = closes.iloc[-1]
        price = float(round(float(price_raw), 4))

        change_pct: float | None = None
        if len(closes) >= 2:
            prev = float(closes.iloc[-2])
            if prev != 0:
                change_pct = float(round((float(closes.iloc[-1]) / prev - 1.0) * 100.0, 4))

        volume: int | None = None
        if "Volume" in hist.columns:
            vol_series = hist["Volume"].dropna()
            if not vol_series.empty:
                volume = int(vol_series.iloc[-1])

        name = symbol
        market_cap: float | None = None
        currency = "USD"
        exchange_str: str | None = None

        try:
            fi = t.fast_info
        except Exception:
            fi = None

        if fi is not None:
            raw_name = _mapping_get(fi, "shortName") or _mapping_get(fi, "longName")
            if isinstance(raw_name, str) and raw_name.strip():
                name = raw_name.strip()

            market_cap = _safe_float(_mapping_get(fi, "market_cap"))

            raw_currency = _mapping_get(fi, "currency")
            if isinstance(raw_currency, str) and raw_currency.strip():
                currency = raw_currency.strip().upper()

            raw_exchange = _mapping_get(fi, "exchange")
            if isinstance(raw_exchange, str) and raw_exchange.strip():
                exchange_str = raw_exchange.strip()

        return {
            "ticker": symbol.upper(),
            "name": name,
            "price": price,
            "change_pct": change_pct,
            "market_cap": market_cap,
            "volume": volume,
            "currency": currency,
            "exchange": exchange_str,
        }


@lru_cache
def get_stock_universe_service() -> StockUniverseService:
    return StockUniverseService()
