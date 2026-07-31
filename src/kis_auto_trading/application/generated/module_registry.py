from fastapi import APIRouter

from kis_auto_trading.modules.account.generated.router import router as account_router
from kis_auto_trading.modules.identity.generated.router import router as identity_router

MODULE_ROUTERS: tuple[APIRouter, ...] = (
    identity_router,
    account_router,
)
