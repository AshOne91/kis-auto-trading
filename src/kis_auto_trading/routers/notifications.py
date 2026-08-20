import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from kis_auto_trading.infrastructure.access_control import (
    AccessLevel,
    require_access_level,
)
from kis_auto_trading.infrastructure.database.provider import get_session_registry
from kis_auto_trading.infrastructure.database.routing import ShardRoutingError
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.session_store.protocol import SessionData
from kis_auto_trading.infrastructure.session_store.provider import get_current_session
from kis_auto_trading.modules.notification.generated.models import InAppNotification
from kis_auto_trading.modules.notification.handlers import list_user_notifications

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/notifications",
    tags=["notifications"],
    dependencies=[Depends(require_access_level(AccessLevel.USER))],
)


@router.get("", response_model=list[InAppNotification])
async def list_notifications(
    current_session: Annotated[SessionData, Depends(get_current_session)],
    session_registry: Annotated[
        AsyncSessionRegistry, Depends(get_session_registry)
    ],
) -> list[InAppNotification]:
    try:
        return await list_user_notifications(current_session, session_registry)
    except (ShardRoutingError, SQLAlchemyError) as error:
        logger.warning("user notification lookup failed: %s", type(error).__name__)
        raise HTTPException(
            status_code=503,
            detail="notifications are unavailable",
        ) from error
