import pytest

from app.agents.stock_analysis_agent import StockAnalysisAgent
from app.agents.workflow import WorkflowOrchestrator


def test_stock_analysis_agent_returns_workflow_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_execute(self, state: dict) -> dict:
        return {
            "ticker": state["ticker"],
            "agent_signal": {
                "ticker": state["ticker"],
                "signal": "hold",
                "confidence": 0.5,
                "notes": ["test"],
                "langgraph_enabled": False,
                "trace": [],
            },
        }

    monkeypatch.setattr(WorkflowOrchestrator, "execute", fake_execute)
    payload = StockAnalysisAgent().run(ticker="AAPL")
    assert payload["ticker"] == "AAPL"
    assert payload["agent_signal"]["signal"] == "hold"
    assert payload["agent_signal"]["confidence"] == 0.5
    assert isinstance(payload["agent_signal"]["notes"], list)


def test_stock_analysis_agent_requires_ticker_kwarg() -> None:
    with pytest.raises(KeyError):
        StockAnalysisAgent().run()
