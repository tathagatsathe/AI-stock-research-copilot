from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Literal, Optional

import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.asset_registry import (
    AssetClass,
    InvalidSymbolError,
    classify_asset,
    display_ticker,
    is_equity_asset,
    macro_region_for_asset,
    resolve_display_name,
)
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
from app.services.stock_universe_service import StockUniverseService, get_stock_universe_service
from app.services.symbol_search_service import (
    SymbolSearchError,
    SymbolSearchService,
    get_symbol_search_service,
)
from app.services.strategy_ratings_service import DISCLAIMER, get_strategy_ratings_service
from app.services.strategy_frameworks_service import get_strategy_frameworks_service

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

SYMBOL_MAX_LENGTH = 20


class StockAnalysisResponse(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=SYMBOL_MAX_LENGTH)
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
    region: str
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


class PriceHistoryPoint(BaseModel):
    date: str = Field(..., min_length=10, max_length=10)
    close: float = Field(..., ge=0)


class FullStockAnalysisResponse(StockAnalysisResponse):
    display_ticker: str = Field(
        ...,
        min_length=1,
        description="Human-friendly ticker label (no ^, =X, =F, or .NS suffixes).",
    )
    name: str = Field(..., min_length=1, description="Full asset name from Yahoo Finance.")
    price_history: list[PriceHistoryPoint] = Field(
        default_factory=list,
        description="Daily close prices for the last 6 months.",
    )
    asset_class: str
    news_analysis: NewsAnalysisResponse
    decision_brief: DecisionBriefResponse
    fundamentals: FundamentalsSnapshotResponse
    macro: MacroContextResponse
    strategy_ratings: StrategyRatingsResponse
    strategy_frameworks: Dict[str, Any]
    disclaimer: str


class StockUniverseItemResponse(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=SYMBOL_MAX_LENGTH)
    display_ticker: str = Field(..., min_length=1, max_length=SYMBOL_MAX_LENGTH)
    name: str = Field(..., min_length=1)
    price: float = Field(..., ge=0)
    change_pct: Optional[float] = None
    market_cap: Optional[float] = Field(
        default=None,
        description="Market capitalization in listing currency when Yahoo provides it.",
    )
    volume: Optional[int] = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=6)
    exchange: Optional[str] = None
    asset_class: str
    market: str


class StockUniverseResponse(BaseModel):
    source: str
    market: str
    as_of: str
    count: int
    stocks: list[StockUniverseItemResponse]
    warnings: list[str]


class SymbolSearchResultResponse(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=SYMBOL_MAX_LENGTH)
    display_ticker: str = Field(..., min_length=1, max_length=SYMBOL_MAX_LENGTH)
    name: str = Field(..., min_length=1)
    exchange: Optional[str] = None
    in_universe: bool


class SymbolSearchResponse(BaseModel):
    query: str
    market: str
    count: int
    results: list[SymbolSearchResultResponse]


def _stub_strategy_rating() -> dict[str, Any]:
    return {
        "score_1_10": 5,
        "confidence": "low",
        "drivers": [],
        "headwinds": ["Equity strategy scores are not applicable for this asset class."],
        "score_label": "not_applicable",
    }


def _stub_strategy_ratings() -> dict[str, Any]:
    stub = _stub_strategy_rating()
    return {
        "value": stub,
        "growth": stub,
        "momentum": stub,
        "dividend": stub,
        "quality": stub,
    }


def _stub_strategy_frameworks() -> dict[str, Any]:
    return {
        "not_applicable": True,
        "buffett_quality_dcf": None,
        "magic_formula": None,
        "garp": None,
        "factor_metrics": None,
    }


def _stub_fundamentals(normalized: str, asset_class: AssetClass) -> dict[str, Any]:
    return {
        "ticker": normalized,
        "source": "yfinance",
        "currency": None,
        "as_of": None,
        "coverage": "low",
        "warnings": [f"Fundamentals are not applicable for {asset_class.value}."],
        "fields": {},
    }


def _yahoo_display_name(yft: yf.Ticker) -> str | None:
    try:
        fi = yft.fast_info
        if fi is not None:
            raw = fi.get("longName") or fi.get("shortName")
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    except Exception:
        pass
    return None


def _resolve_display_name_for_symbol(symbol: str) -> str:
    try:
        yahoo_name = _yahoo_display_name(yf.Ticker(symbol))
    except Exception:
        yahoo_name = None
    return resolve_display_name(symbol, yahoo_name)


def _build_news_payload(
    *,
    news_service: NewsAnalysisService,
    normalized_ticker: str,
    asset_class: AssetClass,
    display_name: str | None = None,
) -> dict:
    try:
        return news_service.analyze_ticker_news(
            normalized_ticker,
            asset_class=asset_class,
            display_name=display_name,
        )
    except (NewsFetchError, NewsAnalysisError) as exc:
        logger.warning("News analysis failed for ticker %s", normalized_ticker)
        return news_service.build_fallback_payload(str(exc))
    except Exception:
        logger.exception("Unexpected news analysis error for ticker %s", normalized_ticker)
        return news_service.build_fallback_payload("Unexpected error while analyzing news.")


def _fetch_analysis_bundle(
    ticker: str,
    stock_service: StockAnalysisService,
) -> tuple[dict, dict, dict, list[dict], AssetClass, str]:
    """Yahoo Finance pull routed by asset class."""
    normalized = stock_service.normalize_ticker(ticker)
    asset_class = classify_asset(normalized)
    yft = yf.Ticker(normalized)
    history = yft.history(period="6mo", interval="1d", auto_adjust=False)
    stock_payload = stock_service.technicals_from_history(normalized, history)
    price_history = stock_service.price_history_from_dataframe(history)
    display_name = resolve_display_name(normalized, _yahoo_display_name(yft))

    if is_equity_asset(asset_class):
        fundamentals_payload = get_fundamentals_service().snapshot_from_ticker(yft, normalized)
        strategy_frameworks = get_strategy_frameworks_service().build(
            ticker=yft,
            normalized_symbol=normalized,
            fundamentals=fundamentals_payload,
            stock=stock_payload,
            asset_class=asset_class,
        )
    else:
        fundamentals_payload = _stub_fundamentals(normalized, asset_class)
        strategy_frameworks = _stub_strategy_frameworks()

    return stock_payload, fundamentals_payload, strategy_frameworks, price_history, asset_class, display_name


def _fetch_equity_bundle(
    ticker: str, stock_service: StockAnalysisService
) -> tuple[dict, dict, dict, list[dict]]:
    """Backward-compatible wrapper for tests."""
    stock_payload, fundamentals_payload, strategy_frameworks, price_history, _, _ = (
        _fetch_analysis_bundle(ticker, stock_service)
    )
    return stock_payload, fundamentals_payload, strategy_frameworks, price_history


def _macro_snapshot_sync(region: str = "us") -> dict:
    """Thin wrapper for macro snapshot (tests may monkeypatch)."""
    return get_macro_instability_service().snapshot(region=region)


async def _build_full_stock_analysis(
    *,
    ticker: str,
    stock_service: StockAnalysisService,
    news_service: NewsAnalysisService,
) -> dict:
    normalized_ticker = stock_service.normalize_ticker(ticker)
    asset_class = classify_asset(normalized_ticker)
    macro_region = macro_region_for_asset(asset_class)

    async def analysis_job() -> tuple[dict, dict, dict, list[dict]]:
        return await asyncio.wait_for(
            run_in_threadpool(_fetch_equity_bundle, ticker, stock_service),
            timeout=settings.stock_analysis_timeout_seconds,
        )

    async def name_job() -> str:
        return await run_in_threadpool(
            _resolve_display_name_for_symbol,
            normalized_ticker,
        )

    async def macro_job() -> dict:
        return await asyncio.wait_for(
            run_in_threadpool(_macro_snapshot_sync, macro_region),
            timeout=settings.stock_analysis_timeout_seconds,
        )

    (
        (stock_payload, fundamentals_payload, strategy_frameworks, price_history),
        macro_payload,
        display_name,
    ) = await asyncio.gather(
        analysis_job(),
        macro_job(),
        name_job(),
    )

    news_payload = await run_in_threadpool(
        _build_news_payload,
        news_service=news_service,
        normalized_ticker=normalized_ticker,
        asset_class=asset_class,
        display_name=display_name,
    )
    resolved_class = asset_class

    merged = {
        **stock_payload,
        "asset_class": resolved_class.value,
        "news_analysis": news_payload,
        "strategy_frameworks": strategy_frameworks,
    }
    brief = get_decision_brief_service().build(
        stock=stock_payload,
        news=news_payload,
        asset_class=resolved_class,
    )
    if is_equity_asset(resolved_class):
        strategy_ratings = get_strategy_ratings_service().build(
            stock=stock_payload,
            news=news_payload,
            fundamentals=fundamentals_payload,
            macro=macro_payload,
        )
    else:
        strategy_ratings = _stub_strategy_ratings()

    return {
        **merged,
        "display_ticker": display_ticker(normalized_ticker),
        "name": display_name,
        "price_history": price_history,
        "decision_brief": brief,
        "fundamentals": fundamentals_payload,
        "macro": macro_payload,
        "strategy_ratings": strategy_ratings,
        "disclaimer": DISCLAIMER,
    }


@router.get(
    "/search",
    summary="Search Yahoo Finance symbols",
    description=(
        "Fuzzy symbol and company-name search for autocomplete. "
        "Results are filtered to the selected market tab."
    ),
    response_model=SymbolSearchResponse,
)
async def search_symbols(
    q: str = Query(..., min_length=1, max_length=64, description="Ticker or company name"),
    market: str = Query(
        default="us_stocks",
        description="Market tab used to filter results",
    ),
    limit: int = Query(default=8, ge=1, le=15),
    search_service: SymbolSearchService = Depends(get_symbol_search_service),
) -> dict:
    try:
        return await asyncio.wait_for(
            run_in_threadpool(search_service.search, q, market, limit),
            timeout=settings.stock_analysis_timeout_seconds,
        )
    except InvalidSymbolError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except SymbolSearchError as exc:
        logger.warning("Symbol search failed for query %r", q)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except asyncio.TimeoutError as exc:
        logger.warning("Symbol search timed out for query %r", q)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Symbol search timed out.",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected symbol search error for query %r", q)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while searching symbols.",
        ) from exc


@router.get(
    "/universe",
    summary="List curated market universe",
    description=(
        "Returns curated symbols for the selected market tab with latest close, prior-session "
        "percent change, market cap (when available), and volume. Markets: us_stocks, india_stocks, "
        "global_indices, forex, crypto, commodities."
    ),
    response_model=StockUniverseResponse,
)
async def get_stock_universe(
    market: str = Query(
        default="us_stocks",
        description="Market tab: us_stocks, india_stocks, global_indices, forex, crypto, commodities",
    ),
    universe_service: StockUniverseService = Depends(get_stock_universe_service),
) -> dict:
    try:
        return await asyncio.wait_for(
            run_in_threadpool(universe_service.build_snapshot, market),
            timeout=settings.stock_universe_timeout_seconds,
        )
    except InvalidSymbolError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except asyncio.TimeoutError as exc:
        logger.warning("Stock universe fetch timed out")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Stock universe fetch timed out.",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error while building stock universe")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while loading stock universe.",
        ) from exc


@router.get(
    "/analysis",
    summary="Get stock analysis",
    description="Returns a baseline analysis payload from the service layer.",
    response_model=StockAnalysisResponse,
)
async def get_stock_analysis(
    ticker: str = Query(..., min_length=1, max_length=SYMBOL_MAX_LENGTH, description="Symbol"),
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
    summary="Get multi-market analysis with news signals",
    description=(
        "Returns technical indicators, headline sentiment, macro context, and equity fundamentals "
        "when applicable. Non-equity assets receive technicals, news, and macro only."
    ),
    response_model=FullStockAnalysisResponse,
)
async def analyze_stock_with_news(
    ticker: str = Path(..., min_length=1, max_length=SYMBOL_MAX_LENGTH, description="Symbol"),
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
