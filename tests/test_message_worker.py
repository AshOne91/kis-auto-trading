from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import ClassVar, cast

import pytest

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.messaging.protocol import EventMessage
from kis_auto_trading.modules.signal.generated.models import (
    SignalSubscriptionProjection,
)
from scripts import run_message_worker


class RecordingSessionRegistry:
    def __init__(self) -> None:
        self.targets: list[ShardTarget] = []

    @asynccontextmanager
    async def session(self, target: ShardTarget) -> AsyncIterator[object]:
        self.targets.append(target)
        yield object()


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


@pytest.fixture(autouse=True)
def use_fake_inbox(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeInbox.claimed_event_ids.clear()
    FakeSignalSubscriptionProjectionRepository.projections.clear()
    monkeypatch.setattr(run_message_worker, "ProcessedMessageInbox", FakeInbox)
    monkeypatch.setattr(
        run_message_worker,
        "SQLAlchemySignalSubscriptionProjectionRepository",
        FakeSignalSubscriptionProjectionRepository,
    )


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
