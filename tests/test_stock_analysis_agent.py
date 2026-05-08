import pytest

from app.agents.stock_analysis_agent import StockAnalysisAgent


def test_stock_analysis_agent_returns_workflow_payload() -> None:
    payload = StockAnalysisAgent().run(ticker="AAPL")
    assert payload["ticker"] == "AAPL"
    assert payload["signal"] == "hold"
    assert payload["confidence"] == 0.5
    assert isinstance(payload["notes"], list)


def test_stock_analysis_agent_requires_ticker_kwarg() -> None:
    with pytest.raises(KeyError):
        StockAnalysisAgent().run()
