import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.modules.notification.generated.models import InAppNotification
from kis_auto_trading.modules.notification.generated.sqlalchemy_repositories import (
    SQLAlchemyInAppNotificationRepository,
)

_DATABASE_URL_ENV = "KIS_NOTIFICATION_DATABASE_URL"


def test_notification_round_trips_through_account_shard_database() -> None:
    database_url = os.getenv(_DATABASE_URL_ENV)
    if not database_url:
        pytest.skip(f"set {_DATABASE_URL_ENV} to enable database integration")

    async def scenario() -> None:
        engine = create_async_engine(database_url)
        registry = AsyncSessionRegistry({}, {("account", "1"): engine})
        user_id = uuid4()
        now = datetime.now(UTC)
        older = InAppNotification(
            notification_id=uuid4(),
            delivery_intent_id=uuid4(),
            user_id=user_id,
            signal_id=uuid4(),
            stock_code="005930",
            created_at=now - timedelta(seconds=1),
            read_at=None,
        )
        newer = older.model_copy(
            update={
                "notification_id": uuid4(),
                "delivery_intent_id": uuid4(),
                "signal_id": uuid4(),
                "created_at": now,
            }
        )
        target = ShardTarget(store="account", shard_id="1")
        try:
            async with registry.session(target) as session:
                repository = SQLAlchemyInAppNotificationRepository(session)
                await repository.save(older)
                await repository.save(newer)

            async with registry.session(target) as session:
                repository = SQLAlchemyInAppNotificationRepository(session)
                stored = await repository.find_by_id(newer.notification_id)
                notifications = await repository.list_by_user_id(user_id)
        finally:
            await engine.dispose()

        assert stored == newer
        assert notifications == [newer, older]

    asyncio.run(scenario())
