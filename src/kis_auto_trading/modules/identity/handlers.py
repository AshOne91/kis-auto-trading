from __future__ import annotations

from kis_auto_trading.modules.identity.generated.schemas import (
    LoginRequest,
    LoginResponse,
    SignupRequest,
    SignupResponse,
)


async def signup(request: SignupRequest) -> SignupResponse:
    raise NotImplementedError("회원가입 Handler를 구현해야 합니다.")


async def login(request: LoginRequest) -> LoginResponse:
    raise NotImplementedError("로그인 Handler를 구현해야 합니다.")
