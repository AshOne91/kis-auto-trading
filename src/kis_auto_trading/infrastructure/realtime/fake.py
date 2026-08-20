from dataclasses import dataclass, field

from .protocol import RealtimeDeliveryHandler


@dataclass
class FakeRealtimeSubscriber:
    """Deterministic subscriber fake for application tests."""

    messages: list[str] = field(default_factory=list)

    async def send(self, message: str) -> None:
        self.messages.append(message)


class FakeRealtimeBackplane:
    """Deterministic in-memory stand-in for Redis Pub/Sub hints."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []
        self._deliver: RealtimeDeliveryHandler | None = None
        self._closed = False

    async def start(self, deliver: RealtimeDeliveryHandler) -> None:
        if self._closed:
            raise RuntimeError('realtime backplane is closed')
        self._deliver = deliver

    async def publish(self, channel: str, message: str) -> None:
        if self._closed:
            raise RuntimeError('realtime backplane is closed')
        self.published.append((channel, message))
        if self._deliver is not None:
            await self._deliver(channel, message)

    async def aclose(self) -> None:
        self._closed = True
        self._deliver = None
