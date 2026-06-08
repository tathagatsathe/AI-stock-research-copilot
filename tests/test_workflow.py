from app.agents.workflow import WorkflowOrchestrator


def _sample_state() -> dict:
    return {
        "ticker": "AAPL",
        "stock": {
            "ticker": "AAPL",
            "current_price": 190.0,
            "sma_50": 185.0,
            "rsi": 55.0,
        },
        "news": {
            "source": "google_news_rss",
            "articles": [],
            "overall_sentiment": "neutral",
            "risk_keywords_detected": [],
            "error": None,
        },
        "fundamentals": {"coverage": "partial", "warnings": [], "fields": {}},
        "macro": {
            "source": "yfinance",
            "symbol": "^VIX",
            "volatility_regime": "normal",
            "instability_score_1_10": 5,
            "coverage": "high",
            "error": None,
        },
        "strategy_frameworks": {
            "garp": {"signal": "hold", "peg_ratio": None, "warnings": []},
        },
    }


def test_workflow_execute_returns_agent_signal_and_brief() -> None:
    orchestrator = WorkflowOrchestrator()
    result = orchestrator.execute(_sample_state())
    assert result["ticker"] == "AAPL"
    assert result["decision_brief"]["verdict"] in {"watch", "cautious", "elevated_risk"}
    assert result["agent_signal"]["signal"] in {"buy", "hold", "sell"}
    assert isinstance(result["agent_signal"]["trace"], list)
