from uuid import UUID
from kis_auto_trading.modules.account.generated.models import UserProfile


class FakeUserProfileRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, UserProfile] = {}

    async def find_by_id(
        self, user_id: UUID,
    ) -> UserProfile | None:
        return self._items.get(user_id)

    async def save(
        self, aggregate: UserProfile,
    ) -> None:
        self._items[aggregate.user_id] = aggregate
