from typing import Protocol
from uuid import UUID

from kis_auto_trading.modules.account.generated.models import UserProfile


class UserProfileRepository(Protocol):
    async def find_by_id(
        self, user_id: UUID,
    ) -> UserProfile | None: ...
    async def save(
        self, aggregate: UserProfile,
    ) -> None: ...
