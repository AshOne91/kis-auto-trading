from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from kis_auto_trading.infrastructure.kis_market_data import KisMarketDataClient
from kis_auto_trading.routers.operator_search import router as operator_search_router


@asynccontextmanager
async def kis_market_data_lifespan(app: FastAPI) -> AsyncIterator[None]:
    client = KisMarketDataClient.from_environment()
    app.state.kis_market_data = client
    try:
        yield
    finally:
        del app.state.kis_market_data
        await client.aclose()


USER_ROUTERS: tuple[APIRouter, ...] = (operator_search_router,)
USER_LIFESPANS = (kis_market_data_lifespan,)
