from __future__ import annotations

import asyncio
import logging
from typing import Dict, Literal, Optional

import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.decision_brief_service import get_decision_brief_service
from app.services.fundamentals_service import get_fundamentals_service
from app.services.macro_instability_service import get_macro_instability_service
from app.services.news_analysis_service import (
    NewsAnalysisError,
    NewsFetchError,
    NewsAnalysisService,
    get_news_analysis_service,
)
from app.services.stock_analysis_service import (
    DataFetchError,
    InvalidTickerError,
    StockAnalysisService,
    get_stock_analysis_service,
)
from app.services.strategy_ratings_service import DISCLAIMER, get_strategy_ratings_service

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()


class StockAnalysisResponse(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    current_price: float = Field(..., ge=0)
    sma_50: float = Field(..., ge=0)
    rsi: float = Field(..., ge=0, le=100)
    return_20d_pct: Optional[float] = None


class NewsArticleResponse(BaseModel):
    title: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    publish_date: str
    summary: str = Field(..., min_length=1)
    sentiment: Literal["bullish", "bearish", "neutral"]
    risk_keywords: list[str]


class NewsAnalysisResponse(BaseModel):
    source: str
    articles: list[NewsArticleResponse]
    overall_sentiment: Literal["bullish", "bearish", "neutral"]
    risk_keywords_detected: list[str]
    error: Optional[str] = None


class DecisionBriefResponse(BaseModel):
    verdict: Literal["watch", "cautious", "elevated_risk"]
    summary_bullets: list[str]
    top_risks: list[str]
    tensions: list[str]
    evidence_quality: Literal["high", "medium", "low"]
    synthesized_at: str
    news_coverage_note: str


class FundamentalsSnapshotResponse(BaseModel):
    ticker: str
    source: str
    currency: Optional[str] = None
    as_of: Optional[str] = None
    coverage: Literal["high", "partial", "low"]
    warnings: list[str]
    fields: Dict[str, Optional[float]]


class MacroContextResponse(BaseModel):
    source: str
    symbol: str
    vix_level: Optional[float] = None
    vix_change_5d_pct: Optional[float] = None
    volatility_regime: Literal["compressed", "normal", "elevated"]
    instability_score_1_10: int = Field(..., ge=1, le=10)
    coverage: Literal["high", "low"]
    error: Optional[str] = None


class StrategyRatingEntry(BaseModel):
    score_1_10: int = Field(..., ge=1, le=10)
    confidence: Literal["high", "medium", "low"]
    drivers: list[str]
    headwinds: list[str]
    score_label: str


class StrategyRatingsResponse(BaseModel):
    value: StrategyRatingEntry
    growth: StrategyRatingEntry
    momentum: StrategyRatingEntry
    dividend: StrategyRatingEntry
    quality: StrategyRatingEntry


class FullStockAnalysisResponse(StockAnalysisResponse):
    news_analysis: NewsAnalysisResponse
    decision_brief: DecisionBriefResponse
    fundamentals: FundamentalsSnapshotResponse
    macro: MacroContextResponse
    strategy_ratings: StrategyRatingsResponse
    disclaimer: str


def _build_news_payload(
    *,
    news_service: NewsAnalysisService,
    normalized_ticker: str,
) -> dict:
    try:
        return news_service.analyze_ticker_news(normalized_ticker)
    except (NewsFetchError, NewsAnalysisError) as exc:
        logger.warning("News analysis failed for ticker %s", normalized_ticker)
        return news_service.build_fallback_payload(str(exc))
    except Exception:
        logger.exception("Unexpected news analysis error for ticker %s", normalized_ticker)
        return news_service.build_fallback_payload("Unexpected error while analyzing news.")


def _fetch_equity_bundle(ticker: str, stock_service: StockAnalysisService) -> tuple[dict, dict]:
    """Single Yahoo Finance ticker pull: technicals + fundamentals (avoids duplicate symbol fetch)."""
    normalized = stock_service.normalize_ticker(ticker)
    yft = yf.Ticker(normalized)
    history = yft.history(period="6mo", interval="1d", auto_adjust=False)
    stock_payload = stock_service.technicals_from_history(normalized, history)
    fundamentals_payload = get_fundamentals_service().snapshot_from_ticker(yft, normalized)
    return stock_payload, fundamentals_payload


def _macro_snapshot_sync() -> dict:
    """Thin wrapper for macro snapshot (tests may monkeypatch)."""
    return get_macro_instability_service().snapshot()


async def _build_full_stock_analysis(
    *,
    ticker: str,
    stock_service: StockAnalysisService,
    news_service: NewsAnalysisService,
) -> dict:
    normalized_ticker = ticker.strip().upper()

    async def equity_job() -> tuple[dict, dict]:
        return await asyncio.wait_for(
            run_in_threadpool(_fetch_equity_bundle, ticker, stock_service),
            timeout=settings.stock_analysis_timeout_seconds,
        )

    async def news_job() -> dict:
        return await run_in_threadpool(
            _build_news_payload,
            news_service=news_service,
            normalized_ticker=normalized_ticker,
        )

    async def macro_job() -> dict:
        return await asyncio.wait_for(
            run_in_threadpool(_macro_snapshot_sync),
            timeout=settings.stock_analysis_timeout_seconds,
        )

    (stock_payload, fundamentals_payload), news_payload, macro_payload = await asyncio.gather(
        equity_job(),
        news_job(),
        macro_job(),
    )

    merged = {
        **stock_payload,
        "news_analysis": news_payload,
    }
    brief = get_decision_brief_service().build(stock=stock_payload, news=news_payload)
    strategy_ratings = get_strategy_ratings_service().build(
        stock=stock_payload,
        news=news_payload,
        fundamentals=fundamentals_payload,
        macro=macro_payload,
    )
    return {
        **merged,
        "decision_brief": brief,
        "fundamentals": fundamentals_payload,
        "macro": macro_payload,
        "strategy_ratings": strategy_ratings,
        "disclaimer": DISCLAIMER,
    }


@router.get(
    "/analysis",
    summary="Get stock analysis",
    description="Returns a baseline analysis payload from the service layer.",
    response_model=StockAnalysisResponse,
)
async def get_stock_analysis(
    ticker: str = Query(..., min_length=1, max_length=10, description="Stock symbol"),
    service: StockAnalysisService = Depends(get_stock_analysis_service),
) -> dict:
    normalized_ticker = ticker.strip().upper()
    try:
        return await asyncio.wait_for(
            run_in_threadpool(service.analyze_stock, ticker=ticker),
            timeout=settings.stock_analysis_timeout_seconds,
        )
    except InvalidTickerError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except DataFetchError as exc:
        logger.warning("Data fetch failure during stock analysis for ticker %s", normalized_ticker)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except asyncio.TimeoutError as exc:
        logger.warning("Stock analysis timed out for ticker %s", normalized_ticker)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Stock analysis timed out.",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected stock analysis error for ticker %s", normalized_ticker)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while analyzing stock.",
        ) from exc


@router.get(
    "/analyze/{ticker}",
    summary="Get stock analysis with news signals",
    description=(
        "Returns technical indicators, headline sentiment, fundamentals snapshot, VIX-based macro "
        "context, and deterministic 1–10 strategy scores (not investment advice)."
    ),
    response_model=FullStockAnalysisResponse,
)
async def analyze_stock_with_news(
    ticker: str = Path(..., min_length=1, max_length=10, description="Stock symbol"),
    stock_service: StockAnalysisService = Depends(get_stock_analysis_service),
    news_service: NewsAnalysisService = Depends(get_news_analysis_service),
) -> dict:
    normalized_ticker = ticker.strip().upper()
    try:
        return await _build_full_stock_analysis(
            ticker=ticker,
            stock_service=stock_service,
            news_service=news_service,
        )
    except InvalidTickerError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except DataFetchError as exc:
        logger.warning("Data fetch failure during stock analysis for ticker %s", normalized_ticker)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except asyncio.TimeoutError as exc:
        logger.warning("Stock analysis timed out for ticker %s", normalized_ticker)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Stock analysis timed out.",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected stock analysis error for ticker %s", normalized_ticker)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while analyzing stock.",
        ) from exc
