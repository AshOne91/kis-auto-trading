from typing import Annotated

from fastapi import APIRouter, Depends

from kis_auto_trading.infrastructure.access_control import (
    AccessLevel,
    require_access_level,
)
from kis_auto_trading.infrastructure.database.provider import get_session_registry
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.session_store.protocol import (
    SessionData,
    SessionStore,
)
from kis_auto_trading.infrastructure.session_store.provider import (
    get_current_session,
    get_session_store,
)
from kis_auto_trading.modules.identity import handlers
from kis_auto_trading.modules.identity.generated.schemas import (
    GetOperatorSessionResponse,
    LoginRequest,
    LoginResponse,
    SignupRequest,
    SignupResponse,
    ValidateSessionRequest,
    ValidateSessionResponse,
)

router = APIRouter(prefix="/api/identity", tags=["Identity"])


@router.post("/signup", response_model=SignupResponse)
async def signup(
    request: SignupRequest,
    session_registry: Annotated[AsyncSessionRegistry, Depends(get_session_registry)],
) -> SignupResponse:
    return await handlers.signup(request, session_registry)


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    session_store: Annotated[SessionStore, Depends(get_session_store)],
    session_registry: Annotated[AsyncSessionRegistry, Depends(get_session_registry)],
) -> LoginResponse:
    return await handlers.login(request, session_store, session_registry)


@router.post("/session/validate", response_model=ValidateSessionResponse)
async def validate_session(
    request: ValidateSessionRequest,
    session_store: Annotated[SessionStore, Depends(get_session_store)],
) -> ValidateSessionResponse:
    return await handlers.validate_session(request, session_store)


@router.get("/operator/session", response_model=GetOperatorSessionResponse, dependencies=[Depends(require_access_level(AccessLevel.OPERATOR))])
async def get_operator_session(
    current_session: Annotated[SessionData, Depends(get_current_session)],
) -> GetOperatorSessionResponse:
    return await handlers.get_operator_session(current_session)
