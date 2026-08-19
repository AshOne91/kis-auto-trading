import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from kis_auto_trading.application.market_price_snapshots import (
    save_market_price_snapshot,
)
from kis_auto_trading.infrastructure.database.provider import get_session_registry
from kis_auto_trading.infrastructure.database.routing import ShardRoutingError
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.kis_market_data import (
    KisDomesticStockPrice,
    KisMarketDataClient,
    KisMarketDataError,
)
from kis_auto_trading.infrastructure.kis_token_coordinator import (
    KisTokenCoordinatorError,
)
from kis_auto_trading.infrastructure.service_tokens import require_service_token
from kis_auto_trading.modules.market_data.generated.models import MarketPriceSnapshot

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
    return await _get_domestic_stock_price(market_data, stock_code)


@router.post(
    "/domestic-stock-price/snapshots",
    response_model=MarketPriceSnapshot,
)
async def create_domestic_stock_price_snapshot(
    stock_code: Annotated[str, Query(pattern=r"^[0-9]{6}$")],
    market_data: Annotated[KisMarketDataClient, Depends(get_kis_market_data)],
    session_registry: Annotated[
        AsyncSessionRegistry, Depends(get_session_registry)
    ],
) -> MarketPriceSnapshot:
    price = await _get_domestic_stock_price(market_data, stock_code)
    try:
        return await save_market_price_snapshot(session_registry, price)
    except (ShardRoutingError, SQLAlchemyError) as error:
        logger.warning("operator market price snapshot persistence failed: %s", type(error).__name__)
        raise HTTPException(
            status_code=503,
            detail="KIS market data persistence is unavailable",
        ) from error


async def _get_domestic_stock_price(
    market_data: KisMarketDataClient,
    stock_code: str,
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
