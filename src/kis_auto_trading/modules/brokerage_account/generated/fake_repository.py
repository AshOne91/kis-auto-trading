from uuid import UUID

from kis_auto_trading.modules.brokerage_account.generated.models import (
    BrokerageAccountConnection,
)


class FakeBrokerageAccountConnectionRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, BrokerageAccountConnection] = {}

    async def find_by_id(
        self, connection_id: UUID,
    ) -> BrokerageAccountConnection | None:
        return self._items.get(connection_id)

    async def save(
        self, aggregate: BrokerageAccountConnection,
    ) -> None:
        self._items[aggregate.connection_id] = aggregate
