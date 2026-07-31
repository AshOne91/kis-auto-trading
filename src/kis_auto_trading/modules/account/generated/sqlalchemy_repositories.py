from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from kis_auto_trading.modules.account.generated.models import UserProfile
from kis_auto_trading.modules.account.generated.sqlalchemy_models import (
    UserProfileRecord,
)


class SQLAlchemyUserProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(
        self, user_id: UUID,
    ) -> UserProfile | None:
        record = await self._session.get(
            UserProfileRecord, user_id
        )
        if record is None:
            return None
        return UserProfile(
            user_id=record.user_id,
            investment_experience=record.investment_experience,
            risk_tolerance=record.risk_tolerance,
            investment_goal=record.investment_goal,
            monthly_budget=record.monthly_budget,
            profile_completed=record.profile_completed
        )

    async def save(
        self, aggregate: UserProfile,
    ) -> None:
        record = UserProfileRecord(
            user_id=aggregate.user_id,
            investment_experience=aggregate.investment_experience,
            risk_tolerance=aggregate.risk_tolerance,
            investment_goal=aggregate.investment_goal,
            monthly_budget=aggregate.monthly_budget,
            profile_completed=aggregate.profile_completed
        )
        await self._session.merge(record)
