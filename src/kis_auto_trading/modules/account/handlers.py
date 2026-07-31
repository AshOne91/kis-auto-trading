from __future__ import annotations

from kis_auto_trading.modules.account.generated.models import UserProfile
from kis_auto_trading.modules.account.generated.schemas import UpdateProfileRequest


async def get_profile() -> UserProfile:
    raise NotImplementedError("Handler를 구현해야 합니다.")


async def update_profile(
    request: UpdateProfileRequest,
) -> UserProfile:
    raise NotImplementedError("Handler를 구현해야 합니다.")
