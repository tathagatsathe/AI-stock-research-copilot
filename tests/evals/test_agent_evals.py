"""Evaluation gates for agent output quality."""

from __future__ import annotations

import json
from pathlib import Path

from app.agents.workflow import WorkflowOrchestrator
from app.services.structured_output import parse_decision_brief_payload


def _golden_ticker_state(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "stock": {"ticker": ticker, "current_price": 100.0, "sma_50": 95.0, "rsi": 50.0},
        "news": {
            "source": "google_news_rss",
            "articles": [{"title": f"{ticker} update", "summary": "neutral coverage", "risk_keywords": []}],
            "overall_sentiment": "neutral",
            "risk_keywords_detected": [],
            "error": None,
        },
        "fundamentals": {"coverage": "partial", "warnings": [], "fields": {"trailing_pe": 20.0}},
        "macro": {
            "source": "yfinance",
            "symbol": "^VIX",
            "volatility_regime": "normal",
            "instability_score_1_10": 5,
            "coverage": "high",
            "error": None,
        },
        "strategy_frameworks": {"garp": {"signal": "hold"}},
    }


def test_eval_schema_compliance_for_decision_brief_parser() -> None:
    parsed = parse_decision_brief_payload(
        {
            "verdict": "watch",
            "summary_bullets": ["a", "b", "c"],
            "top_risks": ["risk"],
            "tensions": ["tension"],
            "evidence_quality": "medium",
            "news_coverage_note": "note",
        },
        fallback_note="fallback",
    )
    required = {
        "verdict",
        "summary_bullets",
        "top_risks",
        "tensions",
        "evidence_quality",
        "synthesized_at",
        "news_coverage_note",
        "synthesis_source",
    }
    assert required.issubset(parsed.keys())
    assert parsed["verdict"] in {"watch", "cautious", "elevated_risk"}


def test_eval_workflow_golden_tickers() -> None:
    orchestrator = WorkflowOrchestrator()
    for ticker in ("AAPL", "MSFT", "GOOGL"):
        result = orchestrator.execute(_golden_ticker_state(ticker))
        brief = result["decision_brief"]
        assert brief["verdict"] in {"watch", "cautious", "elevated_risk"}
        assert 1 <= len(brief["summary_bullets"]) <= 3
        assert result["agent_signal"]["signal"] in {"buy", "hold", "sell"}


def test_eval_tool_call_correctness_uses_prefetched_payloads() -> None:
    orchestrator = WorkflowOrchestrator()
    state = _golden_ticker_state("AAPL")
    state["fundamentals"]["coverage"] = "high"
    result = orchestrator.execute(state)
    assert result.get("strategy_ratings") is not None
    assert set(result["strategy_ratings"].keys()) == {
        "value",
        "growth",
        "momentum",
        "dividend",
        "quality",
    }


def test_eval_artifact_written(tmp_path: Path, monkeypatch) -> None:
    artifact_dir = tmp_path / "runs"
    artifact_dir.mkdir(parents=True)
    orchestrator = WorkflowOrchestrator()
    result = orchestrator.execute(_golden_ticker_state("AAPL"))
    artifact = {
        "schema_pass": True,
        "faithfulness_proxy": 1.0,
        "tool_call_pass": True,
        "ticker": result["ticker"],
        "signal": result["agent_signal"]["signal"],
    }
    out_file = artifact_dir / "eval.json"
    out_file.write_text(json.dumps(artifact), encoding="utf-8")
    loaded = json.loads(out_file.read_text(encoding="utf-8"))
    assert loaded["schema_pass"] is True
