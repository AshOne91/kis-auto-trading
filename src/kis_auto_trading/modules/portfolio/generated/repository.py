from typing import Protocol
from uuid import UUID

from kis_auto_trading.modules.portfolio.generated.models import (
    PortfolioPositionSnapshot,
    PortfolioSnapshot,
)


class PortfolioSnapshotRepository(Protocol):
    async def find_by_id(
        self, snapshot_id: UUID,
    ) -> PortfolioSnapshot | None: ...
    async def save(
        self, aggregate: PortfolioSnapshot,
    ) -> None: ...


class PortfolioPositionSnapshotRepository(Protocol):
    async def find_by_id(
        self, position_id: UUID,
    ) -> PortfolioPositionSnapshot | None: ...
    async def save(
        self, aggregate: PortfolioPositionSnapshot,
    ) -> None: ...
    async def list_by_snapshot_id(
        self, snapshot_id: UUID,
    ) -> list[PortfolioPositionSnapshot]: ...
