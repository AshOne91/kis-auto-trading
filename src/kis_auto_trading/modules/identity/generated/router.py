from fastapi import APIRouter

from kis_auto_trading.modules.identity import handlers

router = APIRouter(prefix="/api/identity", tags=["Identity"])
