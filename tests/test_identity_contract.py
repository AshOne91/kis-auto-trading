from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import ClassVar, cast

import pytest
from fastapi import HTTPException

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.session_store.fake import FakeSessionStore
from kis_auto_trading.modules.identity import handlers
from kis_auto_trading.modules.identity.generated.models import LoginAccount
from kis_auto_trading.modules.identity.generated.schemas import (
    LoginRequest,
    SignupRequest,
    ValidateSessionRequest,
)


class RecordingSessionRegistry:
    def __init__(self) -> None:
        self.targets: list[ShardTarget] = []

    @asynccontextmanager
    async def session(self, target: ShardTarget) -> AsyncIterator[object]:
        self.targets.append(target)
        yield object()


class MemoryLoginAccountRepository:
    accounts_by_email: ClassVar[dict[str, LoginAccount]] = {}

    def __init__(self, session: object) -> None:
        del session

    async def find_by_email(self, email: str) -> LoginAccount | None:
        return self.accounts_by_email.get(email)

    async def save(self, aggregate: LoginAccount) -> None:
        type(self).accounts_by_email[aggregate.email] = aggregate


@pytest.fixture(autouse=True)
def use_memory_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    MemoryLoginAccountRepository.accounts_by_email = {}
    monkeypatch.setattr(
        handlers,
        "SQLAlchemyLoginAccountRepository",
        MemoryLoginAccountRepository,
    )


@pytest.mark.anyio
async def test_identity_routes_use_the_global_store_and_session_store() -> None:
    registry = RecordingSessionRegistry()
    typed_registry = cast(AsyncSessionRegistry, registry)
    session_store = FakeSessionStore(ttl_seconds=3600)

    signup = await handlers.signup(
        SignupRequest(email="User@example.com", password="not-a-secret"),
        typed_registry,
    )
    login = await handlers.login(
        LoginRequest(email="user@example.com", password="not-a-secret"),
        session_store,
        typed_registry,
    )
    session = await handlers.validate_session(
        ValidateSessionRequest(access_token=login.access_token),
        session_store,
    )

    assert signup.email == "user@example.com"
    assert login.user_id == signup.user_id
    assert login.token_type == "bearer"
    assert session.user_id == signup.user_id
    assert session.shard_id in {"1", "2"}
    assert registry.targets == [
        ShardTarget(store="identity"),
        ShardTarget(store="identity"),
    ]


@pytest.mark.anyio
async def test_login_rejects_unknown_credentials() -> None:
    registry = cast(AsyncSessionRegistry, RecordingSessionRegistry())

    with pytest.raises(HTTPException) as error:
        await handlers.login(
            LoginRequest(email="user@example.com", password="not-a-secret"),
            FakeSessionStore(ttl_seconds=3600),
            registry,
        )

    assert error.value.status_code == 401
