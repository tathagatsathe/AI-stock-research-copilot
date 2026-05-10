"""
Retail-facing decision brief: merges technical + news signals into a short verdict.

Implements the Product MVP ask for a one-screen interpretation layer (rule-based v1;
swap internals for an LLM later without changing API shapes).
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import Final, Literal

DecisionVerdict = Literal["watch", "cautious", "elevated_risk"]
EvidenceQuality = Literal["high", "medium", "low"]


class DecisionBriefService:
    """Turn structured stock + news payloads into plain-language decision context."""

    _RSI_STRETCHED_HIGH: Final[float] = 68.0
    _RSI_STRETCHED_LOW: Final[float] = 32.0
    _RSI_WEAK: Final[float] = 38.0

    def build(self, *, stock: dict, news: dict) -> dict:
        ticker = str(stock.get("ticker", "")).strip().upper()
        price = float(stock["current_price"])
        sma = float(stock["sma_50"])
        rsi = float(stock["rsi"])

        overall_sentiment = news.get("overall_sentiment") or "neutral"
        articles = news.get("articles") or []
        risk_kw = list(news.get("risk_keywords_detected") or [])
        news_error = news.get("error")

        evidence_quality = self._evidence_quality(
            article_count=len(articles),
            has_news_error=news_error is not None,
        )
        verdict = self._verdict(
            rsi=rsi,
            price=price,
            sma=sma,
            overall_sentiment=overall_sentiment,
            risk_keywords=risk_kw,
            has_news_error=news_error is not None,
        )
        bullets = self._summary_bullets(
            ticker=ticker,
            rsi=rsi,
            price=price,
            sma=sma,
            overall_sentiment=overall_sentiment,
            news_error=news_error,
        )
        tensions = self._tensions(
            rsi=rsi,
            overall_sentiment=overall_sentiment,
            price=price,
            sma=sma,
        )
        top_risks = self._top_risks(risk_keywords=risk_kw, articles=articles)
        synthesized_at = datetime.now(timezone.utc).isoformat()

        return {
            "verdict": verdict,
            "summary_bullets": bullets[:3],
            "top_risks": top_risks[:5],
            "tensions": tensions[:3],
            "evidence_quality": evidence_quality,
            "synthesized_at": synthesized_at,
            "news_coverage_note": self._news_note(news_error=news_error, article_count=len(articles)),
        }

    @staticmethod
    def _evidence_quality(*, article_count: int, has_news_error: bool) -> EvidenceQuality:
        if has_news_error or article_count == 0:
            return "low"
        if article_count >= 3:
            return "high"
        return "medium"

    def _verdict(
        self,
        *,
        rsi: float,
        price: float,
        sma: float,
        overall_sentiment: str,
        risk_keywords: list[str],
        has_news_error: bool,
    ) -> DecisionVerdict:
        if risk_keywords:
            return "elevated_risk"
        if overall_sentiment == "bearish" and rsi < self._RSI_WEAK:
            return "elevated_risk"
        if has_news_error:
            return "cautious"
        if rsi >= self._RSI_STRETCHED_HIGH or rsi <= self._RSI_STRETCHED_LOW:
            return "cautious"
        if overall_sentiment == "bearish":
            return "cautious"
        bullish_news = overall_sentiment == "bullish"
        trend_up = price >= sma
        if bullish_news != trend_up:
            return "cautious"
        return "watch"

    def _summary_bullets(
        self,
        *,
        ticker: str,
        rsi: float,
        price: float,
        sma: float,
        overall_sentiment: str,
        news_error: str | None,
    ) -> list[str]:
        if price >= sma:
            trend = f"{ticker} is trading at or above its 50-day average—medium-term trend leans supportive."
        else:
            trend = f"{ticker} is below its 50-day average—medium-term trend is soft until price reclaims that level."

        if rsi >= 70:
            mom = f"RSI is elevated ({rsi:.1f}), which often means short-term momentum is stretched and pullbacks are more likely."
        elif rsi <= 30:
            mom = f"RSI is depressed ({rsi:.1f}), which can reflect near-term selling pressure or a potential oversold bounce setup."
        else:
            mom = f"RSI is in a middle band ({rsi:.1f})—no extreme momentum read vs recent history."

        if news_error:
            news_line = f"Latest headlines could not be loaded ({news_error}); lean on price action until news refreshes."
        else:
            sent_phrase = {
                "bullish": "Recent headlines skew positive on balance.",
                "bearish": "Recent headlines skew negative on balance.",
                "neutral": "Recent headlines are mixed or neutral on balance.",
            }.get(overall_sentiment, "Recent headlines are mixed or neutral on balance.")
            news_line = sent_phrase

        return [trend, mom, news_line]

    def _tensions(
        self,
        *,
        rsi: float,
        overall_sentiment: str,
        price: float,
        sma: float,
    ) -> list[str]:
        out: list[str] = []
        stretched_high = rsi >= self._RSI_STRETCHED_HIGH
        stretched_low = rsi <= self._RSI_STRETCHED_LOW
        bullish_news = overall_sentiment == "bullish"
        bearish_news = overall_sentiment == "bearish"
        trend_up = price >= sma

        if stretched_high and bullish_news:
            out.append(
                "Momentum looks stretched (elevated RSI) while headlines skew positive—near-term risk of mean reversion."
            )
        if stretched_low and bearish_news:
            out.append(
                "RSI is weak while headlines skew negative—sentiment and momentum agree, but watch for oversold bounces."
            )
        if trend_up and bearish_news:
            out.append(
                "Price still holds the 50-day trend line, but headlines tilt negative—monitor whether sentiment spills into trend."
            )
        if not trend_up and bullish_news:
            out.append(
                "Headlines lean constructive, but price sits below the 50-day average—recovery vs relief rally is unclear."
            )
        return out

    @staticmethod
    def _top_risks(
        *,
        risk_keywords: list[str],
        articles: list[dict],
    ) -> list[str]:
        risks: list[str] = []
        for kw in risk_keywords:
            risks.append(
                f"Risk theme: “{kw}” appears in recent coverage—verify facts in primary sources."
            )
        for article in articles:
            if article.get("risk_keywords"):
                title = (article.get("title") or "Headline")[:100]
                risks.append(f"Flagged item: {title}")
        return risks

    @staticmethod
    def _news_note(*, news_error: str | None, article_count: int) -> str:
        if news_error:
            return "News evidence is unavailable—verdict leans on technicals only."
        if article_count == 0:
            return "No headlines returned for this query—treat the narrative as thin."
        if article_count < 3:
            return f"Only {article_count} recent headline(s)—interpretation is directional, not exhaustive."
        return f"Synthesized from {article_count} recent headlines (keyword sentiment, not deep NLP)."


@lru_cache
def get_decision_brief_service() -> DecisionBriefService:
    return DecisionBriefService()
