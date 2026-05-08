from functools import lru_cache

from app.agents.stock_analysis_agent import StockAnalysisAgent


class StockAnalysisService:
    def __init__(self, agent: StockAnalysisAgent) -> None:
        self.agent = agent

    def analyze_stock(self, ticker: str) -> dict:
        normalized_ticker = ticker.strip().upper()
        if not normalized_ticker:
            raise ValueError("Ticker symbol cannot be empty.")
        return self.agent.run(ticker=normalized_ticker)


@lru_cache
def get_stock_analysis_service() -> StockAnalysisService:
    return StockAnalysisService(agent=StockAnalysisAgent())
