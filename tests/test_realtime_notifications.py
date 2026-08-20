from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from kis_auto_trading.application import realtime_notifications
from kis_auto_trading.application.extensions import USER_LIFESPANS, USER_ROUTERS
from kis_auto_trading.application.realtime_notifications import (
    notification_channel,
    notification_hint,
    realtime_notifications_lifespan,
)
from kis_auto_trading.infrastructure.realtime import (
    FakeRealtimeBackplane,
    FakeRealtimeSubscriber,
    RealtimeHub,
)
from kis_auto_trading.infrastructure.session_store.protocol import SessionData
from kis_auto_trading.routers.realtime_notifications import router


class RecordingRealtimeHub:
    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []

    async def subscribe(self, channel: str, subscriber: object) -> None:
        del subscriber
        self.subscribed.append(channel)

    async def unsubscribe(self, channel: str, subscriber: object) -> None:
        del subscriber
        self.unsubscribed.append(channel)


class FakeSessionStore:
    def __init__(self, session: SessionData) -> None:
        self._session = session

    async def get(self, session_id: str) -> SessionData | None:
        return self._session if session_id == "live-session" else None


def _app(session: SessionData, hub: RecordingRealtimeHub) -> FastAPI:
    app = FastAPI()
    app.state.session_store = FakeSessionStore(session)
    app.state.notification_realtime_hub = hub
    app.include_router(router)
    return app


def test_notification_realtime_extension_is_registered() -> None:
    assert router in USER_ROUTERS
    assert realtime_notifications_lifespan in USER_LIFESPANS


@pytest.mark.anyio
async def test_notification_lifespan_owns_generated_backplane(monkeypatch) -> None:
    backplane = FakeRealtimeBackplane()
    monkeypatch.setattr(
        realtime_notifications.RedisPubSubRealtimeBackplane,
        "from_environment",
        lambda: backplane,
    )
    app = FastAPI()
    subscriber = FakeRealtimeSubscriber()
    user_id = str(uuid4())
    notification_id = uuid4()

    async with realtime_notifications_lifespan(app):
        hub = app.state.notification_realtime_hub
        await hub.subscribe(notification_channel(user_id), subscriber)
        await backplane.publish(
            notification_channel(user_id), notification_hint(notification_id)
        )

    assert subscriber.messages == [notification_hint(notification_id)]
    assert not hasattr(app.state, "notification_realtime_hub")


def test_notification_stream_rejects_missing_bearer_session() -> None:
    session = SessionData(
        session_id="live-session",
        user_id=str(uuid4()),
        data={"access_level": "user"},
    )

    with (
        TestClient(_app(session, RecordingRealtimeHub())) as client,
        pytest.raises(WebSocketDisconnect) as error,
        client.websocket_connect("/api/notifications/stream"),
    ):
        pass

    assert error.value.code == 1008


def test_notification_stream_uses_only_authenticated_user_channel() -> None:
    session = SessionData(
        session_id="live-session",
        user_id=str(uuid4()),
        data={"access_level": "user"},
    )
    hub = RecordingRealtimeHub()

    with (
        TestClient(_app(session, hub)) as client,
        client.websocket_connect(
            "/api/notifications/stream",
            headers={"Authorization": "Bearer live-session"},
        ) as websocket,
    ):
        websocket.send_text("keepalive")
        assert hub.subscribed == [notification_channel(session.user_id)]

    assert hub.unsubscribed == [notification_channel(session.user_id)]


@pytest.mark.anyio
async def test_notification_hint_reaches_only_its_user_channel() -> None:
    notification_id = uuid4()
    user_id = str(uuid4())
    current_user = FakeRealtimeSubscriber()
    other_user = FakeRealtimeSubscriber()
    hub = RealtimeHub()

    await hub.subscribe(notification_channel(user_id), current_user)
    await hub.subscribe(notification_channel(str(uuid4())), other_user)
    await hub.publish(
        notification_channel(user_id), notification_hint(notification_id)
    )

    assert [json.loads(message) for message in current_user.messages] == [
        {"notification_id": str(notification_id)}
    ]
    assert other_user.messages == []
