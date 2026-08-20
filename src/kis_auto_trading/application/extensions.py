from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from kis_auto_trading.application.realtime_notifications import (
    realtime_notifications_lifespan,
)
from kis_auto_trading.infrastructure.kis_domestic_account import (
    KisDomesticAccountClient,
)
from kis_auto_trading.infrastructure.kis_market_data import KisMarketDataClient
from kis_auto_trading.routers.notifications import router as notifications_router
from kis_auto_trading.routers.operator_market_data import (
    router as operator_market_data_router,
)
from kis_auto_trading.routers.operator_portfolio import (
    router as operator_portfolio_router,
)
from kis_auto_trading.routers.operator_search import router as operator_search_router
from kis_auto_trading.routers.operator_signal import router as operator_signal_router
from kis_auto_trading.routers.realtime_notifications import (
    router as realtime_notifications_router,
)


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
    operator_signal_router,
    notifications_router,
    realtime_notifications_router,
)
USER_LIFESPANS = (
    kis_market_data_lifespan,
    kis_domestic_account_lifespan,
    realtime_notifications_lifespan,
)
