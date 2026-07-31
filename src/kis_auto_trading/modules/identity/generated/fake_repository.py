from uuid import UUID
from kis_auto_trading.modules.identity.generated.models import LoginAccount


class FakeLoginAccountRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, LoginAccount] = {}

    async def find_by_id(
        self, user_id: UUID,
    ) -> LoginAccount | None:
        return self._items.get(user_id)

    async def save(
        self, aggregate: LoginAccount,
    ) -> None:
        self._items[aggregate.user_id] = aggregate
