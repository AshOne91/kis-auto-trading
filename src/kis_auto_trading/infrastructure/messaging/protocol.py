from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class EventMessage:
    event_type: str
    aggregate_id: str
    payload: dict[str, object]
    routing_key: str
    event_id: str = ""
    event_version: int = 1
    occurred_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.event_id:
            object.__setattr__(self, 'event_id', str(uuid4()))
        if self.occurred_at is None:
            object.__setattr__(self, 'occurred_at', datetime.now(UTC))


class MessagePublisher(Protocol):
    async def publish(self, message: EventMessage) -> None: ...


class MessagePublishError(RuntimeError):
    pass


class MessageHandler(Protocol):
    async def handle(self, message: EventMessage) -> None: ...
