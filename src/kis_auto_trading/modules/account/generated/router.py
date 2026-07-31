from fastapi import APIRouter

from kis_auto_trading.modules.account import handlers
from kis_auto_trading.modules.account.generated.models import UserProfile
from kis_auto_trading.modules.account.generated.schemas import UpdateProfileRequest

router = APIRouter(prefix="/api/account", tags=["Account"])


@router.get("/profile", response_model=UserProfile)
async def get_profile() -> UserProfile:
    return await handlers.get_profile()


@router.put("/profile", response_model=UserProfile)
async def update_profile(
    request: UpdateProfileRequest,
) -> UserProfile:
    return await handlers.update_profile(request)
