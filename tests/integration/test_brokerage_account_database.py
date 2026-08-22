import asyncio
import os
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.session_store.protocol import SessionData
from kis_auto_trading.modules.brokerage_account import handlers
from kis_auto_trading.modules.brokerage_account.generated.sqlalchemy_repositories import (
    SQLAlchemyBrokerageAccountConnectionRepository,
)

_DATABASE_URL_ENV = "KIS_BROKERAGE_ACCOUNT_DATABASE_URL"
_USER_ID = "00000000-0000-0000-0000-000000000001"


def test_brokerage_connection_round_trips_through_account_shard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = os.getenv(_DATABASE_URL_ENV)
    if not database_url:
        pytest.skip(f"set {_DATABASE_URL_ENV} to enable database integration")

    monkeypatch.setenv("KIS_ACCOUNT_OWNER_USER_ID", _USER_ID)
    monkeypatch.setenv("KIS_ACCOUNT_NUMBER", "12345678")
    monkeypatch.setenv("KIS_ACCOUNT_PRODUCT_CODE", "01")
    monkeypatch.setenv("KIS_ACCOUNT_ENVIRONMENT", "demo")

    async def scenario() -> None:
        engine = create_async_engine(database_url)
        registry = AsyncSessionRegistry({}, {("account", "1"): engine})
        current_session = SessionData(
            session_id="integration-session",
            user_id=_USER_ID,
            data={"shard_id": "1", "access_level": "user"},
        )
        target = ShardTarget(store="account", shard_id="1")
        try:
            first = await handlers.link_default_connection(
                current_session, registry
            )
            second = await handlers.link_default_connection(
                current_session, registry
            )
            loaded = await handlers.get_connection(current_session, registry)
            async with registry.session(target) as session:
                stored = await SQLAlchemyBrokerageAccountConnectionRepository(
                    session
                ).find_by_id(first.connection_id)
        finally:
            await engine.dispose()

        assert first == second == loaded == stored
        assert first.user_id == UUID(_USER_ID)
        assert first.account_mask == "****5678"
        assert "12345678" not in first.model_dump_json()

    asyncio.run(scenario())
