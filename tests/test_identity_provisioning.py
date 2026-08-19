from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import ClassVar, cast
from uuid import uuid4

import pytest

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.session_store.fake import FakeSessionStore
from kis_auto_trading.infrastructure.session_store.protocol import SessionData
from kis_auto_trading.modules.identity import provisioning
from kis_auto_trading.modules.identity.generated.models import (
    AccessLevelAudit,
    LoginAccount,
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


class MemoryAccessLevelAuditRepository:
    audits: ClassVar[list[AccessLevelAudit]] = []

    def __init__(self, session: object) -> None:
        del session

    async def save(self, aggregate: AccessLevelAudit) -> None:
        type(self).audits.append(aggregate)


@pytest.fixture(autouse=True)
def use_memory_repositories(monkeypatch: pytest.MonkeyPatch) -> None:
    MemoryLoginAccountRepository.accounts_by_email = {}
    MemoryAccessLevelAuditRepository.audits = []
    monkeypatch.setattr(
        provisioning,
        "SQLAlchemyLoginAccountRepository",
        MemoryLoginAccountRepository,
    )
    monkeypatch.setattr(
        provisioning,
        "SQLAlchemyAccessLevelAuditRepository",
        MemoryAccessLevelAuditRepository,
    )


def _account(*, access_level: str = "user") -> LoginAccount:
    return LoginAccount(
        user_id=uuid4(),
        email="operator@example.com",
        password_hash="unused",
        is_active=True,
        access_level=access_level,
        shard_id="1",
        created_at=datetime.now(UTC),
    )


@pytest.mark.anyio
async def test_grant_operator_access_audits_and_revokes_existing_sessions() -> None:
    account = _account()
    MemoryLoginAccountRepository.accounts_by_email[account.email] = account
    registry = RecordingSessionRegistry()
    session_store = FakeSessionStore(ttl_seconds=3600)
    await session_store.create(
        SessionData(
            session_id="{operator}.session",
            user_id=str(account.user_id),
            data={"access_level": "user"},
        )
    )

    result = await provisioning.grant_operator_access(
        email=" OPERATOR@example.com ",
        actor="local-bootstrap",
        session_registry=cast(AsyncSessionRegistry, registry),
        session_store=session_store,
    )

    assert result.user_id == account.user_id
    assert result.changed is True
    assert result.revoked_session_count == 1
    assert MemoryLoginAccountRepository.accounts_by_email[account.email].access_level == "operator"
    assert await session_store.get("{operator}.session") is None
    assert registry.targets == [ShardTarget(store="identity")]
    assert len(MemoryAccessLevelAuditRepository.audits) == 1
    audit = MemoryAccessLevelAuditRepository.audits[0]
    assert audit.subject_user_id == account.user_id
    assert audit.actor == "local-bootstrap"
    assert audit.previous_access_level == "user"
    assert audit.new_access_level == "operator"


@pytest.mark.anyio
async def test_existing_operator_retries_session_revocation_without_second_audit() -> None:
    account = _account(access_level="operator")
    MemoryLoginAccountRepository.accounts_by_email[account.email] = account

    result = await provisioning.grant_operator_access(
        email=account.email,
        actor="local-bootstrap",
        session_registry=cast(AsyncSessionRegistry, RecordingSessionRegistry()),
        session_store=FakeSessionStore(ttl_seconds=3600),
    )

    assert result.changed is False
    assert result.revoked_session_count == 0
    assert MemoryAccessLevelAuditRepository.audits == []


@pytest.mark.anyio
async def test_grant_operator_access_rejects_non_user_account_levels() -> None:
    account = _account(access_level="administrator")
    MemoryLoginAccountRepository.accounts_by_email[account.email] = account

    with pytest.raises(ValueError, match="user-to-operator"):
        await provisioning.grant_operator_access(
            email=account.email,
            actor="local-bootstrap",
            session_registry=cast(AsyncSessionRegistry, RecordingSessionRegistry()),
            session_store=FakeSessionStore(ttl_seconds=3600),
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("email", "actor"),
    [("", "local-bootstrap"), ("operator@example.com", "")],
)
async def test_grant_operator_access_requires_explicit_subject_and_actor(
    email: str,
    actor: str,
) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        await provisioning.grant_operator_access(
            email=email,
            actor=actor,
            session_registry=cast(AsyncSessionRegistry, RecordingSessionRegistry()),
            session_store=FakeSessionStore(ttl_seconds=3600),
        )
