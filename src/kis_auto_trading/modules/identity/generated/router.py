from typing import Annotated

from fastapi import APIRouter, Depends

from kis_auto_trading.infrastructure.session_store.protocol import SessionStore
from kis_auto_trading.infrastructure.session_store.provider import get_session_store
from kis_auto_trading.modules.identity import handlers
from kis_auto_trading.modules.identity.generated.schemas import (
    LoginRequest,
    LoginResponse,
    SignupRequest,
    SignupResponse,
)

router = APIRouter(prefix="/api/identity", tags=["Identity"])


@router.post("/signup", response_model=SignupResponse)
async def signup(
    request: SignupRequest,
) -> SignupResponse:
    return await handlers.signup(request)


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    session_store: Annotated[SessionStore, Depends(get_session_store)],
) -> LoginResponse:
    return await handlers.login(request, session_store)
