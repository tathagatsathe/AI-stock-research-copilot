import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.core.config import get_settings
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

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()


class StockAnalysisResponse(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    current_price: float = Field(..., ge=0)
    sma_50: float = Field(..., ge=0)
    rsi: float = Field(..., ge=0, le=100)


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
    error: str | None = None


class FullStockAnalysisResponse(StockAnalysisResponse):
    news_analysis: NewsAnalysisResponse


def _build_news_payload(
    *,
    news_service: NewsAnalysisService,
    normalized_ticker: str,
) -> dict:
    try:
        return news_service.analyze_ticker_news(normalized_ticker)
    except NewsFetchError as exc:
        logger.warning("News fetch failed for ticker %s", normalized_ticker)
        return news_service.build_fallback_payload(str(exc))
    except NewsAnalysisError as exc:
        logger.warning("News analysis failed for ticker %s", normalized_ticker)
        return news_service.build_fallback_payload(str(exc))
    except Exception:
        logger.exception("Unexpected news analysis error for ticker %s", normalized_ticker)
        return news_service.build_fallback_payload("Unexpected error while analyzing news.")


async def _build_full_stock_analysis(
    *,
    ticker: str,
    stock_service: StockAnalysisService,
    news_service: NewsAnalysisService,
) -> dict:
    normalized_ticker = ticker.strip().upper()
    stock_payload = await asyncio.wait_for(
        run_in_threadpool(stock_service.analyze_stock, ticker=ticker),
        timeout=settings.stock_analysis_timeout_seconds,
    )
    news_payload = await run_in_threadpool(
        _build_news_payload,
        news_service=news_service,
        normalized_ticker=normalized_ticker,
    )
    return {
        **stock_payload,
        "news_analysis": news_payload,
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
    description="Returns technical indicators and latest news sentiment/risk signals.",
    response_model=FullStockAnalysisResponse,
)
async def analyze_stock_with_news(
    ticker: str,
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
