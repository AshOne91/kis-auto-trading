from fastapi import WebSocket


class FastAPIWebSocketSubscriber:
    """Adapt one accepted FastAPI WebSocket for RealtimeHub delivery."""

    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket

    async def send(self, message: str) -> None:
        await self._websocket.send_text(message)
