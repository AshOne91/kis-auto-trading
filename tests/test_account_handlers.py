from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast
from uuid import uuid4

import pytest
from fastapi import HTTPException

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.session_store.protocol import SessionData
from kis_auto_trading.modules.account import handlers
from kis_auto_trading.modules.account.generated.models import UserProfile
from kis_auto_trading.modules.account.generated.schemas import UpdateProfileRequest


class RecordingSessionRegistry:
    def __init__(self) -> None:
        self.targets: list[ShardTarget] = []

    @asynccontextmanager
    async def session(self, target: ShardTarget) -> AsyncIterator[object]:
        self.targets.append(target)
        yield object()


class MemoryProfileRepository:
    profile: UserProfile | None = None

    def __init__(self, session: object) -> None:
        del session

    async def find_by_id(self, user_id: object) -> UserProfile | None:
        if self.profile is None or self.profile.user_id != user_id:
            return None
        return self.profile

    async def save(self, aggregate: UserProfile) -> None:
        type(self).profile = aggregate


@pytest.fixture(autouse=True)
def use_memory_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    MemoryProfileRepository.profile = None
    monkeypatch.setattr(
        handlers,
        "SQLAlchemyUserProfileRepository",
        MemoryProfileRepository,
    )


@pytest.mark.anyio
async def test_update_and_get_profile_use_session_shard() -> None:
    user_id = uuid4()
    current_session = SessionData(
        session_id="session-id",
        user_id=str(user_id),
        data={"shard_id": "2"},
    )
    registry = RecordingSessionRegistry()
    typed_registry = cast(AsyncSessionRegistry, registry)
    request = UpdateProfileRequest(
        investment_experience="ADVANCED",
        risk_tolerance="AGGRESSIVE",
        investment_goal="INCOME",
        monthly_budget=1_000_000,
    )

    updated = await handlers.update_profile(
        request, current_session, typed_registry
    )
    loaded = await handlers.get_profile(current_session, typed_registry)

    assert updated == loaded
    assert updated.user_id == user_id
    assert updated.profile_completed is True
    assert registry.targets == [
        ShardTarget(store="account", shard_id="2"),
        ShardTarget(store="account", shard_id="2"),
    ]


@pytest.mark.anyio
async def test_get_profile_returns_not_found() -> None:
    current_session = SessionData(
        session_id="session-id",
        user_id=str(uuid4()),
        data={"shard_id": "1"},
    )
    registry = cast(AsyncSessionRegistry, RecordingSessionRegistry())

    with pytest.raises(HTTPException) as error:
        await handlers.get_profile(current_session, registry)

    assert error.value.status_code == 404


def test_profile_location_rejects_missing_shard() -> None:
    current_session = SessionData(
        session_id="session-id",
        user_id=str(uuid4()),
        data={},
    )

    with pytest.raises(HTTPException) as error:
        handlers._profile_location(current_session)

    assert error.value.status_code == 500
