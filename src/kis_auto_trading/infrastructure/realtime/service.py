from __future__ import annotations

import asyncio

from .protocol import RealtimeSubscriber


class RealtimeHub:
    """In-process channel fan-out; transport and policy stay consumer-owned."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[RealtimeSubscriber]] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    async def subscribe(self, channel: str, subscriber: RealtimeSubscriber) -> None:
        _require_channel(channel)
        async with self._lock:
            self._require_open()
            subscribers = self._subscribers.setdefault(channel, [])
            if not any(existing is subscriber for existing in subscribers):
                subscribers.append(subscriber)

    async def unsubscribe(self, channel: str, subscriber: RealtimeSubscriber) -> None:
        _require_channel(channel)
        async with self._lock:
            subscribers = self._subscribers.get(channel)
            if subscribers is None:
                return
            remaining = [item for item in subscribers if item is not subscriber]
            if remaining:
                self._subscribers[channel] = remaining
            else:
                self._subscribers.pop(channel, None)

    async def publish(self, channel: str, message: str) -> int:
        _require_channel(channel)
        async with self._lock:
            self._require_open()
            subscribers = tuple(self._subscribers.get(channel, ()))
        await asyncio.gather(*(subscriber.send(message) for subscriber in subscribers))
        return len(subscribers)

    async def aclose(self) -> None:
        async with self._lock:
            self._closed = True
            self._subscribers.clear()

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError('realtime hub is closed')


def _require_channel(channel: str) -> None:
    if not channel.strip():
        raise ValueError('realtime channel must not be empty')
