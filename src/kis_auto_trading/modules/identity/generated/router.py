from fastapi import APIRouter

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
) -> LoginResponse:
    return await handlers.login(request)
