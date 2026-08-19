from typing import Annotated

from fastapi import APIRouter, Depends

from kis_auto_trading.infrastructure.access_control import (
    AccessLevel,
    require_access_level,
)
from kis_auto_trading.infrastructure.database.provider import get_session_registry
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.session_store.protocol import SessionData
from kis_auto_trading.infrastructure.session_store.provider import get_current_session
from kis_auto_trading.modules.account import handlers
from kis_auto_trading.modules.account.generated.models import UserProfile
from kis_auto_trading.modules.account.generated.schemas import UpdateProfileRequest

router = APIRouter(prefix="/api/account", tags=["Account"])


@router.get("/profile", response_model=UserProfile, dependencies=[Depends(require_access_level(AccessLevel.USER))])
async def get_profile(
    current_session: Annotated[SessionData, Depends(get_current_session)],
    session_registry: Annotated[AsyncSessionRegistry, Depends(get_session_registry)],
) -> UserProfile:
    return await handlers.get_profile(current_session, session_registry)


@router.put("/profile", response_model=UserProfile, dependencies=[Depends(require_access_level(AccessLevel.USER))])
async def update_profile(
    request: UpdateProfileRequest,
    current_session: Annotated[SessionData, Depends(get_current_session)],
    session_registry: Annotated[AsyncSessionRegistry, Depends(get_session_registry)],
) -> UserProfile:
    return await handlers.update_profile(request, current_session, session_registry)
