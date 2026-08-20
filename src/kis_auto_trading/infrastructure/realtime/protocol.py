from collections.abc import Awaitable, Callable
from typing import Protocol

RealtimeDeliveryHandler = Callable[[str, str], Awaitable[None]]


class RealtimeSubscriber(Protocol):
    async def send(self, message: str) -> None: ...


class RealtimeBackplane(Protocol):
    async def start(self, deliver: RealtimeDeliveryHandler) -> None: ...

    async def publish(self, channel: str, message: str) -> None: ...

    async def aclose(self) -> None: ...
