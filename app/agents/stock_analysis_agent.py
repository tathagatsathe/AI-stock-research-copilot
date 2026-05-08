from app.agents.base import BaseAgent
from app.agents.workflow import WorkflowOrchestrator


class StockAnalysisAgent(BaseAgent):
    def __init__(self) -> None:
        self.orchestrator = WorkflowOrchestrator()

    def run(self, **kwargs) -> dict:
        ticker = kwargs["ticker"]
        return self.orchestrator.execute({"ticker": ticker})
