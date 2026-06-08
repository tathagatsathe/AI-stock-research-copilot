"""LangGraph orchestration for multi-step stock research."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.state import ResearchState
from app.agents.tools import (
    build_strategy_frameworks,
    build_strategy_ratings,
    fetch_fundamentals,
    fetch_macro,
    fetch_news,
    fetch_technicals,
)
from app.core.config import get_settings
from app.services.decision_brief_service import get_decision_brief_service

logger = logging.getLogger(__name__)


def _append_trace(state: ResearchState, *, node: str, message: str) -> list[dict[str, Any]]:
    trace = list(state.get("trace") or [])
    trace.append({"node": node, "message": message})
    return trace


def _parallel_tools_node(state: ResearchState) -> ResearchState:
    ticker = state["ticker"]
    stock = fetch_technicals(ticker, stock_payload=state.get("stock"))
    news = fetch_news(ticker, news_payload=state.get("news"))
    macro = fetch_macro(macro_payload=state.get("macro"))
    fundamentals = fetch_fundamentals(ticker, fundamentals_payload=state.get("fundamentals"))
    frameworks = build_strategy_frameworks(
        ticker=ticker,
        stock=stock,
        fundamentals=fundamentals,
        frameworks_payload=state.get("strategy_frameworks"),
    )
    ratings = build_strategy_ratings(
        stock=stock,
        news=news,
        fundamentals=fundamentals,
        macro=macro,
        ratings_payload=state.get("strategy_ratings"),
    )
    trace = _append_trace(state, node="parallel_tools", message="Fetched technicals, news, macro, fundamentals, strategies.")
    return {
        **state,
        "stock": stock,
        "news": news,
        "macro": macro,
        "fundamentals": fundamentals,
        "strategy_frameworks": frameworks,
        "strategy_ratings": ratings,
        "trace": trace,
    }


def _news_grounding_node(state: ResearchState) -> ResearchState:
    from app.services.rag_service import get_rag_service

    ticker = state["ticker"]
    news = state.get("news") or {}
    chunks: list[dict[str, Any]] = list(state.get("retrieved_chunks") or [])

    rag = get_rag_service()
    rag.ingest_news(ticker=ticker, articles=news.get("articles") or [])
    query = f"{ticker} stock research risks and catalysts"
    retrieved = rag.retrieve(ticker=ticker, query=query)
    chunks.extend(retrieved)

    trace = _append_trace(
        state,
        node="news_grounding",
        message=f"Retrieved {len(retrieved)} grounded chunks for synthesis.",
    )
    return {**state, "retrieved_chunks": chunks, "trace": trace}


def _synthesis_node(state: ResearchState) -> ResearchState:
    stock = state.get("stock") or {}
    news = state.get("news") or {}
    context = {
        "macro": state.get("macro"),
        "fundamentals": state.get("fundamentals"),
        "strategy_frameworks": state.get("strategy_frameworks"),
        "retrieved_chunks": state.get("retrieved_chunks") or [],
    }
    brief = get_decision_brief_service().build(stock=stock, news=news, context=context)
    trace = _append_trace(state, node="synthesis", message=f"Synthesized decision brief via {brief.get('synthesis_source', 'rules')}.")
    return {**state, "decision_brief": brief, "trace": trace}


def _guardrail_node(state: ResearchState) -> ResearchState:
    brief = dict(state.get("decision_brief") or {})
    frameworks = state.get("strategy_frameworks") or {}
    garp_signal = (frameworks.get("garp") or {}).get("signal")
    risk_keywords = (state.get("news") or {}).get("risk_keywords_detected") or []

    if garp_signal == "buy" and brief.get("verdict") == "elevated_risk":
        signal = "hold"
        confidence = 0.45
        notes = ["GARP buy signal conflicts with elevated-risk brief—defaulting to hold."]
    elif garp_signal == "sell" or risk_keywords:
        signal = "sell" if garp_signal == "sell" else "hold"
        confidence = 0.6 if signal == "sell" else 0.5
        notes = ["Signal derived from GARP framework and headline risk themes."]
    elif garp_signal == "buy":
        signal = "buy"
        confidence = 0.65
        notes = ["GARP buy signal with no elevated headline risk flags."]
    else:
        signal = "hold"
        confidence = 0.5
        notes = ["No strong directional alignment across frameworks."]

    if not brief.get("summary_bullets"):
        from app.services.decision_brief_service import DecisionBriefService

        brief = DecisionBriefService().build(stock=state.get("stock") or {}, news=state.get("news") or {})
        brief["synthesis_source"] = "rules"

    agent_signal = {
        "ticker": state["ticker"],
        "signal": signal,
        "confidence": confidence,
        "notes": notes,
        "langgraph_enabled": get_settings().langgraph_enabled,
    }
    trace = _append_trace(state, node="guardrail", message=f"Agent signal: {signal} (confidence {confidence:.2f}).")
    return {**state, "decision_brief": brief, "agent_signal": agent_signal, "trace": trace}


def _build_graph():
    graph = StateGraph(ResearchState)
    graph.add_node("parallel_tools", _parallel_tools_node)
    graph.add_node("news_grounding", _news_grounding_node)
    graph.add_node("synthesis", _synthesis_node)
    graph.add_node("guardrail", _guardrail_node)
    graph.add_edge(START, "parallel_tools")
    graph.add_edge("parallel_tools", "news_grounding")
    graph.add_edge("news_grounding", "synthesis")
    graph.add_edge("synthesis", "guardrail")
    graph.add_edge("guardrail", END)
    return graph.compile()


class WorkflowOrchestrator:
    """LangGraph orchestration layer with graceful sequential fallback."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._graph = None

    @property
    def graph(self):
        if self._graph is None:
            self._graph = _build_graph()
        return self._graph

    def execute(self, state: dict) -> dict:
        initial: ResearchState = {
            "ticker": state["ticker"].strip().upper(),
            "stock": state.get("stock"),
            "news": state.get("news"),
            "fundamentals": state.get("fundamentals"),
            "macro": state.get("macro"),
            "strategy_frameworks": state.get("strategy_frameworks"),
            "strategy_ratings": state.get("strategy_ratings"),
            "retrieved_chunks": state.get("retrieved_chunks") or [],
            "trace": [],
        }
        try:
            if self.settings.langgraph_enabled:
                final_state = self.graph.invoke(initial)
            else:
                final_state = _guardrail_node(
                    _synthesis_node(_news_grounding_node(_parallel_tools_node(initial)))
                )
            agent_signal = dict(final_state.get("agent_signal") or {})
            agent_signal["trace"] = final_state.get("trace") or []
            return {
                "ticker": final_state["ticker"],
                "decision_brief": final_state.get("decision_brief"),
                "agent_signal": agent_signal,
                "trace": final_state.get("trace") or [],
                "strategy_ratings": final_state.get("strategy_ratings"),
            }
        except Exception:
            logger.exception("Workflow execution failed for %s", state.get("ticker"))
            ticker = initial["ticker"]
            return {
                "ticker": ticker,
                "signal": "hold",
                "confidence": 0.5,
                "notes": ["Workflow execution failed; using baseline hold signal."],
                "langgraph_enabled": self.settings.langgraph_enabled,
                "trace": [{"node": "error", "message": "Workflow failed"}],
            }


@lru_cache
def get_workflow_orchestrator() -> WorkflowOrchestrator:
    return WorkflowOrchestrator()
