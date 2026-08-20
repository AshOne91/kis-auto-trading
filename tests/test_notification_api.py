from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from kis_auto_trading.application.extensions import USER_ROUTERS
from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.session_store.protocol import SessionData
from kis_auto_trading.infrastructure.session_store.provider import get_current_session
from kis_auto_trading.modules.notification import handlers
from kis_auto_trading.modules.notification.generated.models import InAppNotification
from kis_auto_trading.routers.notifications import router


def _app(access_level: str) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_current_session] = lambda: SessionData(
        session_id="session",
        user_id="00000000-0000-0000-0000-000000000001",
        data={"access_level": access_level, "shard_id": "2"},
    )
    app.state.session_registry = object()
    app.include_router(router)
    return app


def test_notification_route_is_registered_and_requires_user_access() -> None:
    assert router in USER_ROUTERS

    with TestClient(_app("invalid")) as client:
        response = client.get("/api/notifications")

    assert response.status_code == 403


def test_notification_route_returns_only_current_user_records(monkeypatch) -> None:
    notification = InAppNotification(
        notification_id=uuid4(),
        delivery_intent_id=uuid4(),
        user_id=uuid4(),
        signal_id=uuid4(),
        stock_code="005930",
        created_at=datetime.now(UTC),
    )

    async def fake_list(current_session, session_registry):
        assert current_session.user_id == "00000000-0000-0000-0000-000000000001"
        assert session_registry is not None
        return [notification]

    monkeypatch.setattr(
        "kis_auto_trading.routers.notifications.list_user_notifications",
        fake_list,
    )
    with TestClient(_app("user")) as client:
        response = client.get("/api/notifications")

    assert response.status_code == 200
    assert response.json() == [notification.model_dump(mode="json")]


def test_notification_route_hides_storage_failure(monkeypatch) -> None:
    async def fake_list(current_session, session_registry):
        del current_session, session_registry
        raise SQLAlchemyError("database detail")

    monkeypatch.setattr(
        "kis_auto_trading.routers.notifications.list_user_notifications",
        fake_list,
    )
    with TestClient(_app("user")) as client:
        response = client.get("/api/notifications")

    assert response.status_code == 503
    assert response.json() == {"detail": "notifications are unavailable"}


class _FakeRepository:
    user_ids: ClassVar[list[object]] = []
    notifications: ClassVar[dict[UUID, InAppNotification]] = {}
    saved: ClassVar[list[InAppNotification]] = []

    def __init__(self, session: object) -> None:
        del session

    async def list_by_user_id(self, user_id: object) -> list[InAppNotification]:
        type(self).user_ids.append(user_id)
        return []

    async def find_by_id(self, notification_id: UUID) -> InAppNotification | None:
        return type(self).notifications.get(notification_id)

    async def save(self, notification: InAppNotification) -> None:
        type(self).saved.append(notification)
        type(self).notifications[notification.notification_id] = notification


class _FakeRegistry:
    def __init__(self) -> None:
        self.targets: list[ShardTarget] = []

    @asynccontextmanager
    async def session(self, target: ShardTarget):
        self.targets.append(target)
        yield object()


@pytest.mark.anyio
async def test_notification_handler_uses_current_session_account_shard(
    monkeypatch,
) -> None:
    _FakeRepository.user_ids.clear()
    monkeypatch.setattr(
        handlers,
        "SQLAlchemyInAppNotificationRepository",
        _FakeRepository,
    )
    registry = _FakeRegistry()
    current_session = SessionData(
        session_id="session",
        user_id="00000000-0000-0000-0000-000000000001",
        data={"shard_id": "2"},
    )

    notifications = await handlers.list_user_notifications(current_session, registry)  # type: ignore[arg-type]

    assert notifications == []
    assert _FakeRepository.user_ids == [UUID(current_session.user_id)]
    assert registry.targets == [ShardTarget(store="account", shard_id="2")]


@pytest.mark.anyio
async def test_notification_handler_marks_only_current_user_record_read(
    monkeypatch,
) -> None:
    _FakeRepository.notifications.clear()
    _FakeRepository.saved.clear()
    notification = InAppNotification(
        notification_id=uuid4(),
        delivery_intent_id=uuid4(),
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        signal_id=uuid4(),
        stock_code="005930",
        created_at=datetime.now(UTC),
    )
    _FakeRepository.notifications[notification.notification_id] = notification
    monkeypatch.setattr(
        handlers,
        "SQLAlchemyInAppNotificationRepository",
        _FakeRepository,
    )
    registry = _FakeRegistry()
    current_session = SessionData(
        session_id="session",
        user_id=str(notification.user_id),
        data={"shard_id": "2"},
    )

    updated = await handlers.mark_user_notification_read(
        notification.notification_id,
        current_session,
        registry,  # type: ignore[arg-type]
    )

    assert updated.read_at is not None
    assert _FakeRepository.saved == [updated]
    assert registry.targets == [ShardTarget(store="account", shard_id="2")]


@pytest.mark.anyio
async def test_notification_handler_hides_other_user_record(monkeypatch) -> None:
    _FakeRepository.notifications.clear()
    _FakeRepository.saved.clear()
    notification = InAppNotification(
        notification_id=uuid4(),
        delivery_intent_id=uuid4(),
        user_id=uuid4(),
        signal_id=uuid4(),
        stock_code="005930",
        created_at=datetime.now(UTC),
    )
    _FakeRepository.notifications[notification.notification_id] = notification
    monkeypatch.setattr(
        handlers,
        "SQLAlchemyInAppNotificationRepository",
        _FakeRepository,
    )
    current_session = SessionData(
        session_id="session",
        user_id="00000000-0000-0000-0000-000000000001",
        data={"shard_id": "2"},
    )

    with pytest.raises(HTTPException) as error:
        await handlers.mark_user_notification_read(
            notification.notification_id,
            current_session,
            _FakeRegistry(),  # type: ignore[arg-type]
        )

    assert error.value.status_code == 404
    assert _FakeRepository.saved == []


def test_notification_read_route_returns_updated_record(monkeypatch) -> None:
    notification = InAppNotification(
        notification_id=uuid4(),
        delivery_intent_id=uuid4(),
        user_id=uuid4(),
        signal_id=uuid4(),
        stock_code="005930",
        created_at=datetime.now(UTC),
        read_at=datetime.now(UTC),
    )

    async def fake_mark(notification_id, current_session, session_registry):
        assert notification_id == notification.notification_id
        assert current_session.user_id == "00000000-0000-0000-0000-000000000001"
        assert session_registry is not None
        return notification

    monkeypatch.setattr(
        "kis_auto_trading.routers.notifications.mark_user_notification_read",
        fake_mark,
    )
    with TestClient(_app("user")) as client:
        response = client.patch(f"/api/notifications/{notification.notification_id}/read")

    assert response.status_code == 200
    assert response.json() == notification.model_dump(mode="json")
