from fastapi import APIRouter, FastAPI

from kis_auto_trading.application.extensions import USER_ROUTERS
from kis_auto_trading.application.generated.lifespan import lifespan
from kis_auto_trading.application.generated.module_registry import MODULE_ROUTERS
from kis_auto_trading.application.observability import (
    configure_logging,
    install_request_logging,
)
from kis_auto_trading.routers.durable_jobs import router as durable_jobs_router
from kis_auto_trading.routers.health import router as health_router


def create_app(
    *,
    module_routers: tuple[APIRouter, ...] = MODULE_ROUTERS,
    include_user_routers: bool = True,
) -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="KIS Auto Trading",
        version="0.1.0",
        lifespan=lifespan,
    )
    install_request_logging(app)
    app.include_router(health_router)
    app.include_router(durable_jobs_router)
    if include_user_routers:
        for router in USER_ROUTERS:
            app.include_router(router)
    for router in module_routers:
        app.include_router(router)
    return app
