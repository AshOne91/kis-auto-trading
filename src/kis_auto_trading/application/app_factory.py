from fastapi import FastAPI

from kis_auto_trading.application.generated.module_registry import MODULE_ROUTERS
from kis_auto_trading.routers.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="KIS Auto Trading", version="0.1.0")
    app.include_router(health_router)
    for router in MODULE_ROUTERS:
        app.include_router(router)
    return app
