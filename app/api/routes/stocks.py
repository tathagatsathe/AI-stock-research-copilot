from fastapi import APIRouter, Depends, Query

from app.services.stock_analysis_service import StockAnalysisService, get_stock_analysis_service

router = APIRouter()


@router.get(
    "/analysis",
    summary="Get stock analysis",
    description="Returns a baseline analysis payload from the service layer.",
)
def get_stock_analysis(
    ticker: str = Query(..., min_length=1, max_length=10, description="Stock symbol"),
    service: StockAnalysisService = Depends(get_stock_analysis_service),
) -> dict:
    return service.analyze_stock(ticker=ticker)
