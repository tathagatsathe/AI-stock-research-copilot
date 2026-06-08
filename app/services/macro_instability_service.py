"""
Macro / risk-climate context from public indices via yfinance.

Primary signal: CBOE VIX (^VIX). Thresholds are heuristic research defaults, not trading rules.
"""

from __future__ import annotations

import logging
import math
from functools import lru_cache
from typing import Any, Final, Literal

import yfinance as yf

logger = logging.getLogger(__name__)

SOURCE: Final[str] = "yfinance"
VIX_SYMBOL: Final[str] = "^VIX"
INDIA_VIX_SYMBOL: Final[str] = "^INDIAVIX"
NIFTY_SYMBOL: Final[str] = "^NSEI"

REGION_VOLATILITY_SYMBOLS: Final[dict[str, str]] = {
    "us": VIX_SYMBOL,
    "india": INDIA_VIX_SYMBOL,
    "global": VIX_SYMBOL,
}

# Regime buckets (VIX spot, last close). Documented for transparency:
# - compressed: complacency / low fear (often coincides with tight credit / carry regimes)
# - normal: typical equity volatility backdrop
# - elevated: fear / stress materially above long-run median (~18–20)
VolatilityRegime = Literal["compressed", "normal", "elevated"]


class MacroInstabilityService:
    _HISTORY_PERIOD: Final[str] = "3mo"
    _HISTORY_INTERVAL: Final[str] = "1d"

    def snapshot(self, region: str = "us") -> dict[str, Any]:
        """
        Fetch regional volatility index history and derive a 1–10 instability score.

        On failure, returns neutral-ish defaults + coverage low (mirrors news fallback pattern).
        """
        region_key = region.strip().lower() if region else "us"
        symbol = REGION_VOLATILITY_SYMBOLS.get(region_key, VIX_SYMBOL)

        payload = self._snapshot_for_symbol(symbol, region_key)
        if payload["coverage"] == "high":
            return payload

        if region_key == "india" and symbol == INDIA_VIX_SYMBOL:
            fallback = self._snapshot_for_symbol(NIFTY_SYMBOL, region_key, is_index_fallback=True)
            if fallback["coverage"] == "high":
                return fallback

        return payload

    def _snapshot_for_symbol(
        self,
        symbol: str,
        region: str,
        *,
        is_index_fallback: bool = False,
    ) -> dict[str, Any]:
        try:
            vix = yf.Ticker(symbol)
            history = vix.history(
                period=self._HISTORY_PERIOD,
                interval=self._HISTORY_INTERVAL,
                auto_adjust=False,
            )
        except Exception as exc:
            logger.warning("Volatility history fetch failed for %s: %s", symbol, exc)
            return self._fallback_payload(
                f"Failed to fetch volatility history for {symbol}.",
                symbol=symbol,
                region=region,
            )

        if history.empty or "Close" not in history:
            return self._fallback_payload(
                f"History was empty for {symbol}.",
                symbol=symbol,
                region=region,
            )

        close = history["Close"].dropna()
        if close.empty:
            return self._fallback_payload(
                f"Close series was empty for {symbol}.",
                symbol=symbol,
                region=region,
            )

        last = float(close.iloc[-1])
        level = float(round(last, 2))

        change_5d_pct: float | None = None
        if len(close) >= 6:
            prior = float(close.iloc[-6])
            if prior != 0 and not math.isnan(prior):
                change_5d_pct = float(round((last / prior - 1.0) * 100.0, 2))

        if is_index_fallback:
            regime = self._index_regime(change_5d_pct)
            instability = self._index_instability_score(change_5d_pct=change_5d_pct)
        else:
            regime = self._regime(level)
            instability = self._instability_score(level=level, change_5d_pct=change_5d_pct)

        return {
            "source": SOURCE,
            "region": region,
            "symbol": symbol,
            "vix_level": level,
            "vix_change_5d_pct": change_5d_pct,
            "volatility_regime": regime,
            "instability_score_1_10": instability,
            "coverage": "high",
            "error": None,
        }

    @staticmethod
    def _regime(level: float) -> VolatilityRegime:
        if level < 15.0:
            return "compressed"
        if level > 25.0:
            return "elevated"
        return "normal"

    @staticmethod
    def _instability_score(*, level: float, change_5d_pct: float | None) -> int:
        """
        Map VIX level + short-term change into 1–10 instability (higher = more fragile backdrop).

        Baseline from spot VIX (annualized implied vol on SPX, not a stock score):
        - ~12  -> 3
        - ~18  -> 5
        - ~25  -> 7
        - ~35+ -> 9–10
        """
        base = 1.0 + (level / 5.0)
        base = max(1.0, min(10.0, base))

        if change_5d_pct is not None:
            if change_5d_pct >= 15.0:
                base += 1.0
            elif change_5d_pct <= -15.0:
                base -= 0.5

        score = int(round(base))
        return max(1, min(10, score))

    @staticmethod
    def _index_regime(change_5d_pct: float | None) -> VolatilityRegime:
        if change_5d_pct is None:
            return "normal"
        if change_5d_pct <= -3.0:
            return "compressed"
        if change_5d_pct >= 3.0:
            return "elevated"
        return "normal"

    @staticmethod
    def _index_instability_score(*, change_5d_pct: float | None) -> int:
        base = 5.0
        if change_5d_pct is not None:
            if change_5d_pct >= 5.0:
                base += 2.0
            elif change_5d_pct >= 2.0:
                base += 1.0
            elif change_5d_pct <= -5.0:
                base -= 1.0
            elif change_5d_pct <= -2.0:
                base -= 0.5
        return max(1, min(10, int(round(base))))

    @staticmethod
    def _fallback_payload(
        error_message: str,
        *,
        symbol: str = VIX_SYMBOL,
        region: str = "us",
    ) -> dict[str, Any]:
        return {
            "source": SOURCE,
            "region": region,
            "symbol": symbol,
            "vix_level": None,
            "vix_change_5d_pct": None,
            "volatility_regime": "normal",
            "instability_score_1_10": 5,
            "coverage": "low",
            "error": error_message,
        }


@lru_cache
def get_macro_instability_service() -> MacroInstabilityService:
    return MacroInstabilityService()
