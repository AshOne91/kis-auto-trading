from fastapi import APIRouter

from kis_auto_trading.modules.account.generated.router import router as account_router
from kis_auto_trading.modules.identity.generated.router import router as identity_router
from kis_auto_trading.modules.market_data.generated.router import (
    router as market_data_router,
)
from kis_auto_trading.modules.news.generated.router import router as news_router
from kis_auto_trading.modules.notification.generated.router import (
    router as notification_router,
)
from kis_auto_trading.modules.signal.generated.router import router as signal_router

MODULE_ROUTERS: tuple[APIRouter, ...] = (
    identity_router,
    account_router,
    news_router,
    market_data_router,
    signal_router,
    notification_router,
)
