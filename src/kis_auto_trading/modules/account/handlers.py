from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.session_store.protocol import SessionData
from kis_auto_trading.modules.account.generated.models import UserProfile
from kis_auto_trading.modules.account.generated.schemas import UpdateProfileRequest
from kis_auto_trading.modules.account.generated.sqlalchemy_repositories import (
    SQLAlchemyUserProfileRepository,
)


async def get_profile(
    current_session: SessionData,
    session_registry: AsyncSessionRegistry,
) -> UserProfile:
    user_id, target = _profile_location(current_session)
    async with session_registry.session(target) as session:
        repository = SQLAlchemyUserProfileRepository(session)
        profile = await repository.find_by_id(user_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile was not found",
        )
    return profile


async def update_profile(
    request: UpdateProfileRequest,
    current_session: SessionData,
    session_registry: AsyncSessionRegistry,
) -> UserProfile:
    user_id, target = _profile_location(current_session)
    profile = UserProfile(
        user_id=user_id,
        investment_experience=request.investment_experience,
        risk_tolerance=request.risk_tolerance,
        investment_goal=request.investment_goal,
        monthly_budget=request.monthly_budget,
        profile_completed=True,
    )
    async with session_registry.session(target) as session:
        repository = SQLAlchemyUserProfileRepository(session)
        await repository.save(profile)
    return profile


def _profile_location(session: SessionData) -> tuple[UUID, ShardTarget]:
    shard_id = session.data.get("shard_id")
    if not isinstance(shard_id, str) or not shard_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session shard is missing",
        )
    try:
        user_id = UUID(session.user_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session user is invalid",
        ) from error
    return user_id, ShardTarget(store="account", shard_id=shard_id)
