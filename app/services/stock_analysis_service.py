import logging
import re
from functools import lru_cache
from typing import Final

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


class StockAnalysisError(Exception):
    """Base exception for stock analysis service errors."""


class InvalidTickerError(StockAnalysisError):
    """Raised when ticker input is invalid or unavailable."""


class DataFetchError(StockAnalysisError):
    """Raised when market data cannot be fetched."""


class StockAnalysisService:
    _TICKER_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

    def normalize_ticker(self, ticker: str) -> str:
        normalized_ticker = ticker.strip().upper()
        if not normalized_ticker:
            raise InvalidTickerError("Ticker symbol cannot be empty.")
        if not self._TICKER_PATTERN.fullmatch(normalized_ticker):
            raise InvalidTickerError(
                "Ticker symbol must start with a letter and contain only letters, digits, '.', or '-'."
            )
        return normalized_ticker

    def analyze_stock(self, ticker: str) -> dict:
        normalized_ticker = self.normalize_ticker(ticker)

        try:
            stock = yf.Ticker(normalized_ticker)
            history = stock.history(period="6mo", interval="1d", auto_adjust=False)
        except Exception as exc:
            logger.exception("Yahoo Finance request failed for ticker %s", normalized_ticker)
            raise DataFetchError("Failed to fetch stock data from Yahoo Finance.") from exc

        return self.technicals_from_history(normalized_ticker, history)

    def technicals_from_history(self, normalized_ticker: str, history: pd.DataFrame) -> dict:
        if history.empty or "Close" not in history:
            logger.info("No historical data available for ticker %s", normalized_ticker)
            raise InvalidTickerError(
                f"No historical price data found for ticker '{normalized_ticker}'."
            )

        close_series = history["Close"].dropna()
        if close_series.empty:
            raise DataFetchError("Historical close prices are unavailable for this ticker.")

        if len(close_series) < 50:
            raise DataFetchError("Not enough historical data to calculate 50-day SMA.")

        current_price = float(round(close_series.iloc[-1], 2))
        sma_50 = float(round(close_series.rolling(window=50).mean().iloc[-1], 2))
        rsi = self._calculate_rsi(close_series, period=14)

        return_20d_pct: float | None = None
        if len(close_series) >= 21:
            last = float(close_series.iloc[-1])
            prior = float(close_series.iloc[-21])
            if prior != 0:
                return_20d_pct = float(round((last / prior - 1.0) * 100.0, 2))

        payload: dict[str, float | str | None] = {
            "ticker": normalized_ticker,
            "current_price": current_price,
            "sma_50": sma_50,
            "rsi": rsi,
            "return_20d_pct": return_20d_pct,
        }
        return payload

    @staticmethod
    def _calculate_rsi(close_series: pd.Series, period: int = 14) -> float:
        if len(close_series) <= period:
            raise DataFetchError(f"Not enough data to calculate RSI-{period}.")

        delta = close_series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)

        average_gain = gain.rolling(window=period).mean()
        average_loss = loss.rolling(window=period).mean()

        latest_avg_gain = average_gain.iloc[-1]
        latest_avg_loss = average_loss.iloc[-1]

        if pd.isna(latest_avg_gain) or pd.isna(latest_avg_loss):
            raise DataFetchError("Unable to calculate RSI due to insufficient rolling data.")
        if latest_avg_loss == 0 and latest_avg_gain == 0:
            return 50.0
        if latest_avg_loss == 0:
            return 100.0

        rs = latest_avg_gain / latest_avg_loss
        rsi = 100 - (100 / (1 + rs))
        return float(round(rsi, 2))


@lru_cache
def get_stock_analysis_service() -> StockAnalysisService:
    return StockAnalysisService()
