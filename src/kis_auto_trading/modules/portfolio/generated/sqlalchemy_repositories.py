from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kis_auto_trading.modules.portfolio.generated.models import (
    PortfolioPositionSnapshot,
    PortfolioSnapshot,
)
from kis_auto_trading.modules.portfolio.generated.sqlalchemy_models import (
    PortfolioPositionSnapshotRecord,
    PortfolioSnapshotRecord,
)


class SQLAlchemyPortfolioSnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(
        self, snapshot_id: UUID,
    ) -> PortfolioSnapshot | None:
        record = await self._session.get(
            PortfolioSnapshotRecord, snapshot_id
        )
        if record is None:
            return None
        return PortfolioSnapshot(
            snapshot_id=record.snapshot_id,
            connection_id=record.connection_id,
            user_id=record.user_id,
            captured_at=record.captured_at,
            position_count=record.position_count
        )

    async def save(
        self, aggregate: PortfolioSnapshot,
    ) -> None:
        record = PortfolioSnapshotRecord(
            snapshot_id=aggregate.snapshot_id,
            connection_id=aggregate.connection_id,
            user_id=aggregate.user_id,
            captured_at=aggregate.captured_at,
            position_count=aggregate.position_count
        )
        await self._session.merge(record)


class SQLAlchemyPortfolioPositionSnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(
        self, position_id: UUID,
    ) -> PortfolioPositionSnapshot | None:
        record = await self._session.get(
            PortfolioPositionSnapshotRecord, position_id
        )
        if record is None:
            return None
        return PortfolioPositionSnapshot(
            position_id=record.position_id,
            snapshot_id=record.snapshot_id,
            user_id=record.user_id,
            stock_code=record.stock_code,
            product_name=record.product_name,
            holding_quantity=record.holding_quantity,
            orderable_quantity=record.orderable_quantity,
            current_price=record.current_price
        )

    async def save(
        self, aggregate: PortfolioPositionSnapshot,
    ) -> None:
        record = PortfolioPositionSnapshotRecord(
            position_id=aggregate.position_id,
            snapshot_id=aggregate.snapshot_id,
            user_id=aggregate.user_id,
            stock_code=aggregate.stock_code,
            product_name=aggregate.product_name,
            holding_quantity=aggregate.holding_quantity,
            orderable_quantity=aggregate.orderable_quantity,
            current_price=aggregate.current_price
        )
        await self._session.merge(record)

    async def list_by_snapshot_id(
        self, snapshot_id: UUID,
    ) -> list[PortfolioPositionSnapshot]:
        result = await self._session.execute(
            select(PortfolioPositionSnapshotRecord).where(
                PortfolioPositionSnapshotRecord.snapshot_id == snapshot_id
            ).order_by(
                PortfolioPositionSnapshotRecord.stock_code.asc()
            ).limit(1000)
        )
        records = result.scalars().all()
        return [
            PortfolioPositionSnapshot(
            position_id=record.position_id,
            snapshot_id=record.snapshot_id,
            user_id=record.user_id,
            stock_code=record.stock_code,
            product_name=record.product_name,
            holding_quantity=record.holding_quantity,
            orderable_quantity=record.orderable_quantity,
            current_price=record.current_price
            )
            for record in records
        ]
