"""LangGraph state definitions for stock research workflow."""

from __future__ import annotations

from typing import Any, Optional, TypedDict


class ResearchState(TypedDict, total=False):
    ticker: str
    stock: dict[str, Any]
    news: dict[str, Any]
    fundamentals: dict[str, Any]
    macro: dict[str, Any]
    strategy_frameworks: dict[str, Any]
    strategy_ratings: dict[str, Any]
    retrieved_chunks: list[dict[str, Any]]
    decision_brief: dict[str, Any]
    agent_signal: dict[str, Any]
    trace: list[dict[str, Any]]
    error: Optional[str]
