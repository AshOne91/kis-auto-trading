import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from kis_auto_trading.infrastructure.kis_market_data import (
    KisDomesticStockPrice,
    KisMarketDataClient,
    KisMarketDataError,
)
from kis_auto_trading.infrastructure.kis_token_coordinator import (
    KisTokenCoordinatorError,
)
from kis_auto_trading.infrastructure.service_tokens import require_service_token

logger = logging.getLogger(__name__)


class DomesticStockPriceResponse(BaseModel):
    stock_code: str
    current_price: str


def get_kis_market_data(request: Request) -> KisMarketDataClient:
    try:
        return request.app.state.kis_market_data
    except AttributeError as error:
        raise HTTPException(
            status_code=503,
            detail="KIS market data is not configured",
        ) from error


router = APIRouter(
    prefix="/internal/operator/market-data",
    tags=["operator-market-data"],
    dependencies=[Depends(require_service_token("operator"))],
)


@router.get("/domestic-stock-price", response_model=DomesticStockPriceResponse)
async def get_domestic_stock_price(
    stock_code: Annotated[str, Query(pattern=r"^[0-9]{6}$")],
    market_data: Annotated[KisMarketDataClient, Depends(get_kis_market_data)],
) -> KisDomesticStockPrice:
    try:
        return await market_data.get_domestic_stock_price(stock_code)
    except KisMarketDataError as error:
        logger.warning("operator KIS market data rejected: %s", error)
        raise HTTPException(
            status_code=502,
            detail="KIS market data is unavailable",
        ) from error
    except (KisTokenCoordinatorError, httpx.HTTPError) as error:
        logger.warning("operator KIS market data transport failed: %s", type(error).__name__)
        raise HTTPException(
            status_code=503,
            detail="KIS market data is unavailable",
        ) from error
