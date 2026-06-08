"""LangGraph tool wrappers around existing deterministic services."""

from __future__ import annotations

from typing import Any

from app.services.fundamentals_service import get_fundamentals_service
from app.services.macro_instability_service import get_macro_instability_service
from app.services.news_analysis_service import get_news_analysis_service
from app.services.stock_analysis_service import get_stock_analysis_service
from app.services.strategy_frameworks_service import get_strategy_frameworks_service
from app.services.strategy_ratings_service import get_strategy_ratings_service


def fetch_technicals(ticker: str, *, stock_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if stock_payload is not None:
        return stock_payload
    return get_stock_analysis_service().analyze_stock(ticker)


def fetch_news(ticker: str, *, news_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if news_payload is not None:
        return news_payload
    service = get_news_analysis_service()
    try:
        return service.analyze_ticker_news(ticker)
    except Exception as exc:
        return service.build_fallback_payload(str(exc))


def fetch_macro(*, macro_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if macro_payload is not None:
        return macro_payload
    return get_macro_instability_service().snapshot()


def fetch_fundamentals(
    ticker: str,
    *,
    fundamentals_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if fundamentals_payload is not None:
        return fundamentals_payload
    import yfinance as yf

    normalized = get_stock_analysis_service().normalize_ticker(ticker)
    yft = yf.Ticker(normalized)
    return get_fundamentals_service().snapshot_from_ticker(yft, normalized)


def build_strategy_frameworks(
    *,
    ticker: str,
    stock: dict[str, Any],
    fundamentals: dict[str, Any],
    frameworks_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if frameworks_payload is not None:
        return frameworks_payload
    import yfinance as yf

    normalized = get_stock_analysis_service().normalize_ticker(ticker)
    yft = yf.Ticker(normalized)
    return get_strategy_frameworks_service().build(
        ticker=yft,
        normalized_symbol=normalized,
        fundamentals=fundamentals,
        stock=stock,
    )


def build_strategy_ratings(
    *,
    stock: dict[str, Any],
    news: dict[str, Any],
    fundamentals: dict[str, Any],
    macro: dict[str, Any],
    ratings_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if ratings_payload is not None:
        return ratings_payload
    return get_strategy_ratings_service().build(
        stock=stock,
        news=news,
        fundamentals=fundamentals,
        macro=macro,
    )
