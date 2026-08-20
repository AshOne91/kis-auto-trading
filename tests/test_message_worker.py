from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import ClassVar, cast
from uuid import uuid4

import pytest

from kis_auto_trading.application.realtime_notifications import (
    notification_channel,
    notification_hint,
)
from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.messaging.protocol import EventMessage
from kis_auto_trading.infrastructure.realtime import (
    RealtimeBackplane,
    RealtimeBackplaneError,
)
from kis_auto_trading.modules.notification.generated.models import InAppNotification
from kis_auto_trading.modules.signal.generated.models import (
    SignalDeliveryIntent,
    SignalSubscriptionProjection,
)
from scripts import run_message_worker


class RecordingSessionRegistry:
    def __init__(self) -> None:
        self.targets: list[ShardTarget] = []
        self.completed_targets: list[ShardTarget] = []

    @asynccontextmanager
    async def session(self, target: ShardTarget) -> AsyncIterator[object]:
        self.targets.append(target)
        try:
            yield object()
        finally:
            self.completed_targets.append(target)


class AfterCommitRealtimeBackplane:
    def __init__(self, registry: RecordingSessionRegistry, *, fail: bool) -> None:
        self._registry = registry
        self._fail = fail
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> None:
        assert self._registry.completed_targets
        self.published.append((channel, message))
        if self._fail:
            raise RealtimeBackplaneError("Redis unavailable")


class FakeInbox:
    claimed_event_ids: ClassVar[set[str]] = set()

    def __init__(self, session: object) -> None:
        del session

    async def claim(self, event_id: str) -> bool:
        if event_id in self.claimed_event_ids:
            return False
        self.claimed_event_ids.add(event_id)
        return True


class FakeSignalSubscriptionProjectionRepository:
    projections: ClassVar[dict[object, SignalSubscriptionProjection]] = {}

    def __init__(self, session: object) -> None:
        del session

    async def find_by_id(
        self, subscription_id: object
    ) -> SignalSubscriptionProjection | None:
        return type(self).projections.get(subscription_id)

    async def save(self, projection: SignalSubscriptionProjection) -> None:
        type(self).projections[projection.subscription_id] = projection


class FakeSignalDeliveryIntentRepository:
    intents: ClassVar[dict[object, SignalDeliveryIntent]] = {}

    def __init__(self, session: object) -> None:
        del session

    async def find_by_id(self, intent_id: object) -> SignalDeliveryIntent | None:
        return type(self).intents.get(intent_id)

    async def save(self, intent: SignalDeliveryIntent) -> None:
        type(self).intents[intent.intent_id] = intent


class FakeInAppNotificationRepository:
    notifications: ClassVar[dict[object, InAppNotification]] = {}

    def __init__(self, session: object) -> None:
        del session

    async def find_by_id(
        self, notification_id: object
    ) -> InAppNotification | None:
        return type(self).notifications.get(notification_id)

    async def save(self, notification: InAppNotification) -> None:
        type(self).notifications[notification.notification_id] = notification


class FakeOutboxWriter:
    messages: ClassVar[list[EventMessage]] = []

    def __init__(self, session: object) -> None:
        del session

    def add(self, message: EventMessage) -> None:
        type(self).messages.append(message)


@pytest.fixture(autouse=True)
def use_fake_inbox(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeInbox.claimed_event_ids.clear()
    FakeSignalSubscriptionProjectionRepository.projections.clear()
    FakeSignalDeliveryIntentRepository.intents.clear()
    FakeInAppNotificationRepository.notifications.clear()
    FakeOutboxWriter.messages.clear()
    monkeypatch.setattr(run_message_worker, "ProcessedMessageInbox", FakeInbox)
    monkeypatch.setattr(
        run_message_worker,
        "SQLAlchemySignalSubscriptionProjectionRepository",
        FakeSignalSubscriptionProjectionRepository,
    )
    monkeypatch.setattr(
        run_message_worker,
        "SQLAlchemySignalDeliveryIntentRepository",
        FakeSignalDeliveryIntentRepository,
    )
    monkeypatch.setattr(
        run_message_worker,
        "SQLAlchemyInAppNotificationRepository",
        FakeInAppNotificationRepository,
    )
    monkeypatch.setattr(run_message_worker, "OutboxWriter", FakeOutboxWriter)


@pytest.mark.anyio
async def test_profile_event_is_claimed_once_on_payload_shard() -> None:
    registry = RecordingSessionRegistry()
    handler = run_message_worker.ApplicationMessageHandler(
        cast(AsyncSessionRegistry, registry)
    )
    message = EventMessage(
        event_id="4a1fb8bc-c45f-42cc-8a49-30ec6f436f52",
        event_type="account.profile.updated",
        aggregate_id="8e0228d4-762a-4ccf-90f9-fd8db616364f",
        routing_key="account.profile.updated",
        payload={"shard_id": "2"},
    )

    await handler.handle(message)
    await handler.handle(message)

    assert FakeInbox.claimed_event_ids == {message.event_id}
    assert registry.targets == [
        ShardTarget(store="account", shard_id="2"),
        ShardTarget(store="account", shard_id="2"),
    ]


@pytest.mark.anyio
async def test_unknown_event_is_rejected() -> None:
    registry = cast(AsyncSessionRegistry, RecordingSessionRegistry())
    handler = run_message_worker.ApplicationMessageHandler(registry)
    message = EventMessage(
        event_type="unknown.event",
        aggregate_id="aggregate-id",
        routing_key="account.profile.unknown",
        payload={"shard_id": "1"},
    )

    with pytest.raises(ValueError, match="Unsupported event type"):
        await handler.handle(message)


@pytest.mark.anyio
async def test_signal_subscription_event_is_projected_once_in_automation() -> None:
    registry = RecordingSessionRegistry()
    handler = run_message_worker.ApplicationMessageHandler(
        cast(AsyncSessionRegistry, registry)
    )
    message = EventMessage(
        event_id="4a1fb8bc-c45f-42cc-8a49-30ec6f436f53",
        event_type="signal.subscription.updated",
        aggregate_id="8e0228d4-762a-4ccf-90f9-fd8db616364f",
        routing_key="signal.subscription.updated",
        payload={
            "subscription_id": "8e0228d4-762a-4ccf-90f9-fd8db616364f",
            "user_id": "4a1fb8bc-c45f-42cc-8a49-30ec6f436f52",
            "shard_id": "2",
            "stock_code": "005930",
            "enabled": True,
            "revision": 1,
        },
    )

    await handler.handle(message)
    await handler.handle(message)

    projection = next(
        iter(FakeSignalSubscriptionProjectionRepository.projections.values())
    )
    assert projection.stock_code == "005930"
    assert projection.shard_id == "2"
    assert projection.enabled is True
    assert projection.revision == 1
    assert FakeInbox.claimed_event_ids == {message.event_id}
    assert registry.targets == [ShardTarget(store="automation")] * 2


@pytest.mark.anyio
async def test_stale_signal_subscription_event_does_not_overwrite_projection() -> None:
    registry = RecordingSessionRegistry()
    handler = run_message_worker.ApplicationMessageHandler(
        cast(AsyncSessionRegistry, registry)
    )
    payload = {
        "subscription_id": "8e0228d4-762a-4ccf-90f9-fd8db616364f",
        "user_id": "4a1fb8bc-c45f-42cc-8a49-30ec6f436f52",
        "shard_id": "2",
        "stock_code": "005930",
        "enabled": False,
        "revision": 2,
    }
    newest = EventMessage(
        event_id="4a1fb8bc-c45f-42cc-8a49-30ec6f436f54",
        event_type="signal.subscription.updated",
        aggregate_id=payload["subscription_id"],
        routing_key="signal.subscription.updated",
        payload=payload,
    )
    stale = EventMessage(
        event_id="4a1fb8bc-c45f-42cc-8a49-30ec6f436f55",
        event_type=newest.event_type,
        aggregate_id=newest.aggregate_id,
        routing_key=newest.routing_key,
        payload={**payload, "enabled": True, "revision": 1},
    )

    await handler.handle(newest)
    await handler.handle(stale)

    projection = next(
        iter(FakeSignalSubscriptionProjectionRepository.projections.values())
    )
    assert projection.enabled is False
    assert projection.revision == 2


@pytest.mark.anyio
async def test_invalid_signal_subscription_event_is_rejected_before_claim() -> None:
    registry = RecordingSessionRegistry()
    handler = run_message_worker.ApplicationMessageHandler(
        cast(AsyncSessionRegistry, registry)
    )
    message = EventMessage(
        event_type="signal.subscription.updated",
        aggregate_id="aggregate-id",
        routing_key="signal.subscription.updated",
        payload={},
    )

    with pytest.raises(ValueError, match="Invalid signal subscription event payload"):
        await handler.handle(message)

    assert FakeInbox.claimed_event_ids == set()
    assert registry.targets == []


@pytest.mark.anyio
async def test_signal_event_materializes_one_pending_intent_per_subscription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subscription = SignalSubscriptionProjection(
        subscription_id=uuid4(),
        user_id=uuid4(),
        shard_id="2",
        stock_code="005930",
        enabled=True,
        revision=1,
    )

    async def fake_list_subscriptions(
        registry: AsyncSessionRegistry,
        stock_code: str,
        *,
        limit: int,
    ) -> list[SignalSubscriptionProjection]:
        del registry, stock_code, limit
        return [subscription]

    monkeypatch.setattr(
        run_message_worker, "list_enabled_signal_subscriptions", fake_list_subscriptions
    )
    registry = RecordingSessionRegistry()
    handler = run_message_worker.ApplicationMessageHandler(
        cast(AsyncSessionRegistry, registry)
    )
    signal_id = uuid4()
    message = EventMessage(
        event_id="4a1fb8bc-c45f-42cc-8a49-30ec6f436f56",
        event_type="signal.created",
        aggregate_id=str(signal_id),
        routing_key="signal.created",
        payload={
            "signal_id": str(signal_id),
            "stock_code": "005930",
            "direction": "BUY",
            "price": "70000",
            "confidence": 0.91,
            "observed_at": "2026-08-20T00:00:00Z",
            "expires_at": "2099-08-20T00:05:00Z",
        },
    )

    await handler.handle(message)
    await handler.handle(message)

    assert len(FakeSignalDeliveryIntentRepository.intents) == 1
    intent = next(iter(FakeSignalDeliveryIntentRepository.intents.values()))
    assert intent.signal_id == signal_id
    assert intent.subscription_id == subscription.subscription_id
    assert intent.status == "pending"
    assert len(FakeOutboxWriter.messages) == 1
    assert FakeOutboxWriter.messages[0].event_type == "signal.delivery-intent.created"


@pytest.mark.anyio
@pytest.mark.parametrize("realtime_fails", [False, True])
async def test_delivery_intent_event_materializes_one_notification_on_payload_shard(
    realtime_fails: bool,
) -> None:
    registry = RecordingSessionRegistry()
    backplane = AfterCommitRealtimeBackplane(registry, fail=realtime_fails)
    handler = run_message_worker.ApplicationMessageHandler(
        cast(AsyncSessionRegistry, registry),
        realtime_backplane=cast(RealtimeBackplane, backplane),
    )
    intent_id = uuid4()
    user_id = uuid4()
    message = EventMessage(
        event_id="4a1fb8bc-c45f-42cc-8a49-30ec6f436f57",
        event_type="signal.delivery-intent.created",
        aggregate_id=str(intent_id),
        routing_key="signal.delivery-intent.created",
        payload={
            "intent_id": str(intent_id),
            "signal_id": str(uuid4()),
            "subscription_id": str(uuid4()),
            "user_id": str(user_id),
            "shard_id": "2",
            "stock_code": "005930",
            "expires_at": "2099-08-20T00:05:00Z",
            "status": "pending",
        },
    )

    await handler.handle(message)
    await handler.handle(message)

    assert len(FakeInAppNotificationRepository.notifications) == 1
    notification = next(iter(FakeInAppNotificationRepository.notifications.values()))
    assert notification.delivery_intent_id == intent_id
    assert notification.stock_code == "005930"
    assert registry.targets == [ShardTarget(store="account", shard_id="2")] * 2
    assert backplane.published == [
        (
            notification_channel(str(user_id)),
            notification_hint(notification.notification_id),
        )
    ]
