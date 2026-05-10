"""Fundamentals snapshot from yfinance (info + latest reported statements)."""

from __future__ import annotations

import logging
import math
from functools import lru_cache
from typing import Any, Final

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

SOURCE: Final[str] = "yfinance"

# Yahoo `info` keys -> stable API field names
INFO_FIELD_NAMES: Final[dict[str, str]] = {
    "trailingPE": "trailing_pe",
    "forwardPE": "forward_pe",
    "priceToBook": "price_to_book",
    "debtToEquity": "debt_to_equity",
    "returnOnEquity": "return_on_equity",
    "profitMargins": "profit_margins",
    "operatingMargins": "operating_margins",
    "dividendYield": "dividend_yield",
    "revenueGrowth": "revenue_growth",
    "earningsGrowth": "earnings_growth",
    "earningsQuarterlyGrowth": "earnings_quarterly_growth",
    "currentRatio": "current_ratio",
    "quickRatio": "quick_ratio",
    "beta": "beta",
    "marketCap": "market_cap",
    "enterpriseValue": "enterprise_value",
    "payoutRatio": "payout_ratio",
    "bookValue": "book_value",
    "totalDebt": "total_debt_info",
    "totalCash": "total_cash_info",
    "freeCashflow": "free_cashflow",
    "operatingCashflow": "operating_cashflow",
}


def _num(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (bool,)):
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def _ratio_pair(numer_key: str, denom_key: str, row_map: dict[str, float]) -> float | None:
    n = row_map.get(numer_key)
    d = row_map.get(denom_key)
    if n is None or d is None or d == 0:
        return None
    return float(n / d)


class FundamentalsService:
    """Extract JSON-safe fundamentals using an existing yfinance Ticker instance."""

    _INFO_KEYS: Final[tuple[str, ...]] = (
        "trailingPE",
        "forwardPE",
        "priceToBook",
        "debtToEquity",
        "returnOnEquity",
        "profitMargins",
        "operatingMargins",
        "dividendYield",
        "revenueGrowth",
        "earningsGrowth",
        "earningsQuarterlyGrowth",
        "currentRatio",
        "quickRatio",
        "beta",
        "marketCap",
        "enterpriseValue",
        "payoutRatio",
        "bookValue",
        "totalDebt",
        "totalCash",
        "freeCashflow",
        "operatingCashflow",
    )

    _BS_ROW_ALIASES: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
        ("total_debt", ("Total Debt", "Total Debt Net")),
        ("cash_and_equivalents", ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments")),
        ("current_assets", ("Current Assets",)),
        ("current_liabilities", ("Current Liabilities",)),
        ("stockholders_equity", ("Stockholders Equity", "Common Stock Equity")),
        ("total_assets", ("Total Assets",)),
    )

    _IS_ROW_ALIASES: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
        ("total_revenue", ("Total Revenue",)),
        ("net_income", ("Net Income", "Net Income Common Stockholders")),
        ("operating_income", ("Operating Income",)),
    )

    def snapshot_from_ticker(self, ticker: yf.Ticker, normalized_symbol: str) -> dict[str, Any]:
        warnings: list[str] = []
        fields: dict[str, float | None] = {}
        currency: str | None = None
        as_of: str | None = None

        info: dict[str, Any] = {}
        try:
            info = ticker.info or {}
        except Exception:
            logger.warning("yfinance info() failed for %s", normalized_symbol)
            warnings.append("Could not load ticker info from Yahoo Finance.")

        if isinstance(info, dict):
            raw_currency = info.get("financialCurrency") or info.get("currency")
            if isinstance(raw_currency, str) and raw_currency.strip():
                currency = raw_currency.strip().upper()
            for key in self._INFO_KEYS:
                fields[INFO_FIELD_NAMES[key]] = _num(info.get(key))

        bs_rows = self._statement_rows(ticker.balance_sheet, "balance_sheet", warnings)
        is_rows = self._statement_rows(ticker.financials, "financials", warnings)

        for canonical, aliases in self._BS_ROW_ALIASES:
            val = self._first_row_value(bs_rows, aliases)
            if val is not None:
                fields[canonical] = val

        for canonical, aliases in self._IS_ROW_ALIASES:
            val = self._first_row_value(is_rows, aliases)
            if val is not None:
                fields[canonical] = val

        derived_current_ratio = _ratio_pair("current_assets", "current_liabilities", {**bs_rows})
        if fields.get("current_ratio") is None and derived_current_ratio is not None:
            fields["derived_current_ratio"] = derived_current_ratio

        coverage = self._coverage_score(fields, bs_rows, is_rows, warnings)

        return {
            "ticker": normalized_symbol,
            "source": SOURCE,
            "currency": currency,
            "as_of": as_of,
            "coverage": coverage,
            "warnings": warnings,
            "fields": {k: fields[k] for k in sorted(fields)},
        }

    @staticmethod
    def _statement_rows(
        frame: pd.DataFrame | None,
        label: str,
        warnings: list[str],
    ) -> dict[str, float]:
        if frame is None or frame.empty:
            warnings.append(f"{label} statement unavailable or empty.")
            return {}
        try:
            last_col = frame.columns[-1]
            series = frame[last_col]
        except Exception:
            warnings.append(f"{label} statement could not be parsed.")
            return {}
        out: dict[str, float] = {}
        for idx, val in series.items():
            key = str(idx).strip()
            num = _num(val)
            if num is not None:
                out[key] = num
        return out

    @staticmethod
    def _first_row_value(rows: dict[str, float], aliases: tuple[str, ...]) -> float | None:
        for name in aliases:
            if name in rows:
                return rows[name]
        return None

    @staticmethod
    def _coverage_score(
        fields: dict[str, float | None],
        bs_rows: dict[str, float],
        is_rows: dict[str, float],
        warnings: list[str],
    ) -> str:
        core_info = sum(
            1
            for k in ("trailing_pe", "forward_pe", "price_to_book", "return_on_equity", "profit_margins")
            if fields.get(k) is not None
        )
        has_bs = len(bs_rows) > 0
        has_is = len(is_rows) > 0

        score = core_info + (3 if has_bs else 0) + (2 if has_is else 0)
        if warnings:
            score = max(0, score - 1)

        if score >= 8:
            return "high"
        if score >= 4:
            return "partial"
        return "low"


@lru_cache
def get_fundamentals_service() -> FundamentalsService:
    return FundamentalsService()
