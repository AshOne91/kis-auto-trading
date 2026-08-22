from typing import Protocol
from uuid import UUID

from kis_auto_trading.modules.brokerage_account.generated.models import (
    BrokerageAccountConnection,
)


class BrokerageAccountConnectionRepository(Protocol):
    async def find_by_id(
        self, connection_id: UUID,
    ) -> BrokerageAccountConnection | None: ...
    async def save(
        self, aggregate: BrokerageAccountConnection,
    ) -> None: ...
