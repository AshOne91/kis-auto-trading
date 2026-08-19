from fastapi import APIRouter

from kis_auto_trading.routers.operator_search import router as operator_search_router

USER_ROUTERS: tuple[APIRouter, ...] = (operator_search_router,)
