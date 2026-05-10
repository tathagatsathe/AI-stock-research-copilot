"""
Deterministic multi-strategy scores (1–10) from technicals, fundamentals, news, and macro context.

Not investment advice — research-assistance labels only.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any, Final, Literal

Confidence = Literal["high", "medium", "low"]

DISCLAIMER: Final[str] = (
    "Scores are heuristic blends of public-market data and headlines for research assistance only; "
    "they are not investment advice, forecasts, or suitability judgments."
)


def _clamp_score(value: float) -> int:
    return max(1, min(10, int(round(value))))


def _score_label(score: int) -> str:
    if score >= 8:
        return "strong_signal"
    if score >= 6:
        return "moderate_candidate"
    if score >= 4:
        return "mixed_setup"
    return "weak_setup"


class StrategyRatingsService:
    """Preset strategies: Value, Growth, Momentum, Dividend, Quality."""

    _MACRO_STRESS_THRESHOLD: Final[int] = 8
    _NEWS_RISK_CAP: Final[int] = 5

    def build(
        self,
        *,
        stock: dict[str, Any],
        news: dict[str, Any],
        fundamentals: dict[str, Any],
        macro: dict[str, Any],
    ) -> dict[str, Any]:
        fields = fundamentals.get("fields") or {}
        fund_cov = str(fundamentals.get("coverage") or "low")

        macro_instability = macro.get("instability_score_1_10")
        instability_int = int(macro_instability) if isinstance(macro_instability, int) else 5

        sentiment = str(news.get("overall_sentiment") or "neutral")
        risk_kw = list(news.get("risk_keywords_detected") or [])
        news_error = news.get("error")
        articles = news.get("articles") or []

        strategies = {
            "value": self._rate_value(fields, fund_cov, sentiment),
            "growth": self._rate_growth(fields, fund_cov, sentiment),
            "momentum": self._rate_momentum(stock, sentiment),
            "dividend": self._rate_dividend(fields, fund_cov, sentiment),
            "quality": self._rate_quality(fields, fund_cov, sentiment, risk_kw),
        }

        for payload in strategies.values():
            self._apply_cross_cut_adjustments(
                payload,
                instability_int=instability_int,
                risk_keywords=risk_kw,
                sentiment=sentiment,
                news_error=news_error is not None,
                article_count=len(articles),
            )

        return strategies

    def _rate_value(
        self,
        fields: dict[str, Any],
        fund_cov: str,
        sentiment: str,
    ) -> dict[str, Any]:
        drivers: list[str] = []
        headwinds: list[str] = []

        score = 5.0
        pe = _finite(fields.get("trailing_pe"))
        pb = _finite(fields.get("price_to_book"))
        de = _finite(fields.get("debt_to_equity"))

        if pe is not None:
            if pe > 0 and pe < 18:
                score += 2.0
                drivers.append("Trailing P/E looks moderate versus a generic fair-value lens.")
            elif pe > 35:
                score -= 2.0
                headwinds.append("Trailing P/E is elevated—value lens is less forgiving.")
        else:
            headwinds.append("Trailing P/E unavailable—value read is incomplete.")

        if pb is not None:
            if pb > 0 and pb < 3:
                score += 1.0
                drivers.append("Price/book is not extreme on headline multiples.")
            elif pb > 8:
                score -= 1.5
                headwinds.append("Price/book is high—paying a steep premium to book.")

        if de is not None:
            if de > 200:
                score -= 2.0
                headwinds.append("Debt/equity looks high—balance sheet risk pressures deep value.")
            elif de < 80:
                score += 1.0
                drivers.append("Leverage proxy appears moderate.")

        score = self._sentiment_tilt(score, sentiment, bullish=0.5, bearish=-0.5)

        confidence = self._confidence(fund_cov, pe is not None and pb is not None)

        raw = _clamp_score(score)
        return self._pack(raw, confidence, drivers, headwinds)

    def _rate_growth(
        self,
        fields: dict[str, Any],
        fund_cov: str,
        sentiment: str,
    ) -> dict[str, Any]:
        drivers: list[str] = []
        headwinds: list[str] = []

        score = 5.0
        rev_g = _finite(fields.get("revenue_growth"))
        earn_g = _finite(fields.get("earnings_growth"))
        q_earn = _finite(fields.get("earnings_quarterly_growth"))

        growth_signals = 0
        if rev_g is not None:
            if rev_g > 0.08:
                score += 2.0
                growth_signals += 1
                drivers.append("Revenue growth proxy is positive.")
            elif rev_g < 0:
                score -= 1.5
                headwinds.append("Revenue growth proxy is negative.")

        if earn_g is not None:
            if earn_g > 0.10:
                score += 1.5
                growth_signals += 1
                drivers.append("Earnings growth proxy supports the narrative.")
            elif earn_g < 0:
                score -= 1.5
                headwinds.append("Earnings growth proxy is negative.")

        if q_earn is not None and q_earn > 0.12:
            score += 0.5
            growth_signals += 1

        if growth_signals == 0 and rev_g is None and earn_g is None:
            headwinds.append("Growth metrics missing—cannot validate expansion story from fundamentals.")

        score = self._sentiment_tilt(score, sentiment, bullish=0.7, bearish=-0.7)

        confidence = self._confidence(fund_cov, growth_signals > 0)

        raw = _clamp_score(score)
        return self._pack(raw, confidence, drivers, headwinds)

    def _rate_momentum(self, stock: dict[str, Any], sentiment: str) -> dict[str, Any]:
        drivers: list[str] = []
        headwinds: list[str] = []

        rsi = float(stock["rsi"])
        price = float(stock["current_price"])
        sma = float(stock["sma_50"])
        ret20 = stock.get("return_20d_pct")
        ret = float(ret20) if ret20 is not None else None

        score = 5.0

        if rsi >= 45 and rsi <= 62:
            score += 1.5
            drivers.append("RSI is in a constructive band—no obvious exhaustion vs recent history.")
        elif rsi > 72:
            score -= 1.5
            headwinds.append("RSI is stretched—chasing strength can mean worse risk/reward short term.")
        elif rsi < 35:
            score += 0.5
            drivers.append("RSI is weak—could reflect pullback pressure or oversold mean-reversion setups.")

        if price >= sma:
            score += 2.0
            drivers.append("Price is at/above the 50-day average—medium-term trend supports momentum.")
        else:
            score -= 1.5
            headwinds.append("Price is below the 50-day average—trend filter is not confirming.")

        if ret is not None:
            if ret > 6:
                score += 1.0
                drivers.append("20-day performance is positive—short-term impulse aligns.")
            elif ret < -8:
                score -= 1.5
                headwinds.append("20-day performance is weak—momentum evidence is mixed.")

        score = self._sentiment_tilt(score, sentiment, bullish=0.6, bearish=-0.6)

        raw = _clamp_score(score)
        return self._pack(raw, "high", drivers, headwinds)

    def _rate_dividend(
        self,
        fields: dict[str, Any],
        fund_cov: str,
        sentiment: str,
    ) -> dict[str, Any]:
        drivers: list[str] = []
        headwinds: list[str] = []

        score = 5.0
        div_yield = _finite(fields.get("dividend_yield"))
        payout = _finite(fields.get("payout_ratio"))

        if div_yield is not None:
            if div_yield > 0.015:
                score += 2.0
                drivers.append("Dividend yield is materially above zero—cash return channel exists.")
            elif div_yield <= 0:
                score -= 1.0
                headwinds.append("No dividend yield detected—strategy fit is weaker.")
        else:
            headwinds.append("Dividend yield unavailable.")

        if payout is not None:
            if payout > 0.85:
                score -= 2.0
                headwinds.append("Payout ratio looks high—distribution may crowd reinvestment.")
            elif 0 < payout < 0.65:
                score += 0.5
                drivers.append("Payout ratio looks moderate versus a sustainability sniff test.")

        score = self._sentiment_tilt(score, sentiment, bullish=0.4, bearish=-0.4)

        confidence = self._confidence(fund_cov, div_yield is not None)

        raw = _clamp_score(score)
        return self._pack(raw, confidence, drivers, headwinds)

    def _rate_quality(
        self,
        fields: dict[str, Any],
        fund_cov: str,
        sentiment: str,
        risk_kw: list[str],
    ) -> dict[str, Any]:
        drivers: list[str] = []
        headwinds: list[str] = []

        score = 5.0
        roe = _finite(fields.get("return_on_equity"))
        margin = _finite(fields.get("profit_margins"))
        de = _finite(fields.get("debt_to_equity"))

        if roe is not None:
            if roe > 0.18:
                score += 2.0
                drivers.append("Return on equity proxy looks strong.")
            elif roe < 0.08:
                score -= 1.5
                headwinds.append("Return on equity proxy looks weak.")

        if margin is not None:
            if margin > 0.12:
                score += 1.0
                drivers.append("Profit margin proxy suggests durable economics.")
            elif margin < 0:
                score -= 2.0
                headwinds.append("Negative profit margin proxy—quality lens is skeptical.")

        if de is not None:
            if de < 90:
                score += 1.0
                drivers.append("Leverage proxy appears manageable.")
            elif de > 250:
                score -= 2.0
                headwinds.append("Leverage proxy looks elevated.")

        if risk_kw:
            score -= 1.0
            headwinds.append("Recent headline risk themes detected—quality profiles can still suffer.")

        score = self._sentiment_tilt(score, sentiment, bullish=0.4, bearish=-0.6)

        confidence = self._confidence(fund_cov, roe is not None and margin is not None)

        raw = _clamp_score(score)
        return self._pack(raw, confidence, drivers, headwinds)

    @staticmethod
    def _sentiment_tilt(score: float, sentiment: str, *, bullish: float, bearish: float) -> float:
        if sentiment == "bullish":
            return score + bullish
        if sentiment == "bearish":
            return score + bearish
        return score

    @staticmethod
    def _confidence(fund_cov: str, has_core_signal: bool) -> Confidence:
        if fund_cov == "high" and has_core_signal:
            return "high"
        if fund_cov == "low" and not has_core_signal:
            return "low"
        return "medium"

    @staticmethod
    def _pack(score: int, confidence: Confidence, drivers: list[str], headwinds: list[str]) -> dict[str, Any]:
        return {
            "score_1_10": score,
            "confidence": confidence,
            "drivers": drivers[:5],
            "headwinds": headwinds[:5],
            "score_label": _score_label(score),
        }

    def _apply_cross_cut_adjustments(
        self,
        payload: dict[str, Any],
        *,
        instability_int: int,
        risk_keywords: list[str],
        sentiment: str,
        news_error: bool,
        article_count: int,
    ) -> None:
        score = float(payload["score_1_10"])

        # Macro stress: fade enthusiasm uniformly (documented tilt).
        if instability_int >= self._MACRO_STRESS_THRESHOLD:
            score -= 1.0
            payload.setdefault("headwinds", []).append(
                "Macro volatility backdrop is elevated (high VIX instability score)—sizes risk budgets tighter."
            )

        # Headline risk themes: never ignore obvious governance/legal tail risks.
        if risk_keywords:
            score = min(score, float(self._NEWS_RISK_CAP))
            payload.setdefault("headwinds", []).append(
                "Risk keywords flagged in recent headlines—scores are capped pending verification."
            )

        # Thin news evidence: gently widen uncertainty for sentiment-sensitive reads.
        if news_error or article_count == 0:
            if payload["confidence"] == "high":
                payload["confidence"] = "medium"
            payload.setdefault("headwinds", []).append(
                "News evidence is thin or unavailable—narrative tilts are discounted."
            )

        # Bearish narrative + macro stress double penalty (still capped by risk_keywords rule above).
        if sentiment == "bearish" and instability_int >= 7:
            score -= 0.5

        payload["score_1_10"] = _clamp_score(score)
        payload["score_label"] = _score_label(int(payload["score_1_10"]))


def _finite(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(x) or math.isinf(x):
        return None
    return x


@lru_cache
def get_strategy_ratings_service() -> StrategyRatingsService:
    return StrategyRatingsService()
