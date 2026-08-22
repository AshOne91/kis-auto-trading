from uuid import UUID

from kis_auto_trading.modules.portfolio.generated.models import (
    PortfolioPositionSnapshot,
    PortfolioSnapshot,
)


class FakePortfolioSnapshotRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, PortfolioSnapshot] = {}

    async def find_by_id(
        self, snapshot_id: UUID,
    ) -> PortfolioSnapshot | None:
        return self._items.get(snapshot_id)

    async def save(
        self, aggregate: PortfolioSnapshot,
    ) -> None:
        self._items[aggregate.snapshot_id] = aggregate


class FakePortfolioPositionSnapshotRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, PortfolioPositionSnapshot] = {}

    async def find_by_id(
        self, position_id: UUID,
    ) -> PortfolioPositionSnapshot | None:
        return self._items.get(position_id)

    async def save(
        self, aggregate: PortfolioPositionSnapshot,
    ) -> None:
        self._items[aggregate.position_id] = aggregate

    async def list_by_snapshot_id(
        self, snapshot_id: UUID,
    ) -> list[PortfolioPositionSnapshot]:
        items = [
            item for item in self._items.values()
            if item.snapshot_id == snapshot_id
        ]
        return sorted(
            items,
            key=lambda item: item.stock_code,
            reverse=False,
        )[:1000]
