from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import ClassVar, cast

import pytest

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.messaging.protocol import EventMessage
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


@pytest.fixture(autouse=True)
def use_fake_inbox(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeInbox.claimed_event_ids.clear()
    monkeypatch.setattr(run_message_worker, "ProcessedMessageInbox", FakeInbox)


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
