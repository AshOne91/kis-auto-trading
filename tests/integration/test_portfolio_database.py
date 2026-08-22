import asyncio
import os
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.kis_domestic_account import (
    KisDomesticAccountClient,
    KisDomesticStockHolding,
)
from kis_auto_trading.infrastructure.session_store.protocol import SessionData
from kis_auto_trading.modules.brokerage_account.generated.models import (
    BrokerageAccountConnection,
)
from kis_auto_trading.modules.portfolio import handlers
from kis_auto_trading.modules.portfolio.generated.sqlalchemy_repositories import (
    SQLAlchemyPortfolioPositionSnapshotRepository,
    SQLAlchemyPortfolioSnapshotRepository,
)

_DATABASE_URL_ENV = "KIS_PORTFOLIO_DATABASE_URL"
_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


class FakeAccountClient:
    def __init__(self) -> None:
        self.requests = 0

    async def list_domestic_stock_holdings(self) -> tuple[KisDomesticStockHolding, ...]:
        self.requests += 1
        return (
            KisDomesticStockHolding(
                stock_code="005930",
                product_name="Samsung",
                holding_quantity="10",
                orderable_quantity="8",
                current_price="70000",
            ),
        )


def test_portfolio_snapshot_round_trips_through_account_shard() -> None:
    database_url = os.getenv(_DATABASE_URL_ENV)
    if not database_url:
        pytest.skip(f"set {_DATABASE_URL_ENV} to enable database integration")

    async def scenario() -> None:
        engine = create_async_engine(database_url)
        registry = AsyncSessionRegistry({}, {("account", "1"): engine})
        current_session = SessionData(
            session_id="integration-session",
            user_id=str(_USER_ID),
            data={"shard_id": "1", "access_level": "user"},
        )
        now = datetime.now(UTC)
        connection = BrokerageAccountConnection(
            connection_id=uuid4(),
            user_id=_USER_ID,
            provider="kis",
            environment="demo",
            display_name="KIS default account",
            account_mask="****5678",
            credential_ref="kis:default",
            status="active",
            created_at=now,
            updated_at=now,
        )
        account = FakeAccountClient()
        target = ShardTarget(store="account", shard_id="1")
        try:
            first = await handlers.capture_portfolio_snapshot(
                current_session,
                registry,
                connection,
                cast(KisDomesticAccountClient, account),
                "integration",
            )
            replayed = await handlers.capture_portfolio_snapshot(
                current_session,
                registry,
                connection,
                cast(KisDomesticAccountClient, account),
                "integration",
            )
            async with registry.session(target) as session:
                stored_snapshot = await SQLAlchemyPortfolioSnapshotRepository(
                    session
                ).find_by_id(first.snapshot.snapshot_id)
                stored_positions = (
                    await SQLAlchemyPortfolioPositionSnapshotRepository(
                        session
                    ).list_by_snapshot_id(first.snapshot.snapshot_id)
                )
        finally:
            await engine.dispose()

        assert replayed == first
        assert stored_snapshot == first.snapshot
        assert stored_positions == list(first.positions)
        assert account.requests == 1

    asyncio.run(scenario())
