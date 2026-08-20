from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from kis_auto_trading.infrastructure.kis_domestic_account import (
    KisDomesticAccountClient,
)
from kis_auto_trading.infrastructure.kis_market_data import KisMarketDataClient
from kis_auto_trading.routers.operator_market_data import (
    router as operator_market_data_router,
)
from kis_auto_trading.routers.operator_portfolio import (
    router as operator_portfolio_router,
)
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


@asynccontextmanager
async def kis_domestic_account_lifespan(app: FastAPI) -> AsyncIterator[None]:
    client = KisDomesticAccountClient.from_environment()
    app.state.kis_domestic_account = client
    try:
        yield
    finally:
        del app.state.kis_domestic_account
        await client.aclose()


USER_ROUTERS: tuple[APIRouter, ...] = (
    operator_market_data_router,
    operator_portfolio_router,
    operator_search_router,
)
USER_LIFESPANS = (kis_market_data_lifespan, kis_domestic_account_lifespan)
