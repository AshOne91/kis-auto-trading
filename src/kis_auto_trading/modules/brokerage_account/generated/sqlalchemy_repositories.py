from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from kis_auto_trading.modules.brokerage_account.generated.models import (
    BrokerageAccountConnection,
)
from kis_auto_trading.modules.brokerage_account.generated.sqlalchemy_models import (
    BrokerageAccountConnectionRecord,
)


class SQLAlchemyBrokerageAccountConnectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(
        self, connection_id: UUID,
    ) -> BrokerageAccountConnection | None:
        record = await self._session.get(
            BrokerageAccountConnectionRecord, connection_id
        )
        if record is None:
            return None
        return BrokerageAccountConnection(
            connection_id=record.connection_id,
            user_id=record.user_id,
            provider=record.provider,
            environment=record.environment,
            display_name=record.display_name,
            account_mask=record.account_mask,
            credential_ref=record.credential_ref,
            status=record.status,
            created_at=record.created_at,
            updated_at=record.updated_at
        )

    async def save(
        self, aggregate: BrokerageAccountConnection,
    ) -> None:
        record = BrokerageAccountConnectionRecord(
            connection_id=aggregate.connection_id,
            user_id=aggregate.user_id,
            provider=aggregate.provider,
            environment=aggregate.environment,
            display_name=aggregate.display_name,
            account_mask=aggregate.account_mask,
            credential_ref=aggregate.credential_ref,
            status=aggregate.status,
            created_at=aggregate.created_at,
            updated_at=aggregate.updated_at
        )
        await self._session.merge(record)
