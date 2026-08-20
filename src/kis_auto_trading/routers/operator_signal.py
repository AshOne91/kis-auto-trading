import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from kis_auto_trading.application.signal_subscriptions import (
    list_enabled_signal_subscriptions,
)
from kis_auto_trading.infrastructure.database.provider import get_session_registry
from kis_auto_trading.infrastructure.database.routing import ShardRoutingError
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.service_tokens import require_service_token
from kis_auto_trading.modules.signal.generated.models import (
    SignalSubscriptionProjection,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal/operator/signal",
    tags=["operator-signal"],
    dependencies=[Depends(require_service_token("operator"))],
)


@router.get("/subscriptions", response_model=list[SignalSubscriptionProjection])
async def list_signal_subscriptions(
    stock_code: Annotated[str, Query(pattern=r"^[0-9]{6}$")],
    session_registry: Annotated[
        AsyncSessionRegistry, Depends(get_session_registry)
    ],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[SignalSubscriptionProjection]:
    try:
        return await list_enabled_signal_subscriptions(
            session_registry,
            stock_code,
            limit=limit,
        )
    except (ShardRoutingError, SQLAlchemyError) as error:
        logger.warning(
            "operator signal subscription lookup failed: %s", type(error).__name__
        )
        raise HTTPException(
            status_code=503,
            detail="signal subscription projection is unavailable",
        ) from error
