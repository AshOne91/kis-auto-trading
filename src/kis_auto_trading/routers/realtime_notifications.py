import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.security import HTTPAuthorizationCredentials

from kis_auto_trading.application.realtime_notifications import notification_channel
from kis_auto_trading.infrastructure.access_control import (
    AccessLevel,
    require_access_level,
)
from kis_auto_trading.infrastructure.realtime import (
    FastAPIWebSocketSubscriber,
    RealtimeHub,
)
from kis_auto_trading.infrastructure.session_store.protocol import (
    SessionData,
    SessionStoreError,
)
from kis_auto_trading.infrastructure.session_store.provider import get_current_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class _SafeWebSocketSubscriber:
    def __init__(self, websocket: WebSocket) -> None:
        self._subscriber = FastAPIWebSocketSubscriber(websocket)

    async def send(self, message: str) -> None:
        try:
            await self._subscriber.send(message)
        except (RuntimeError, WebSocketDisconnect):
            logger.debug("notification websocket delivery skipped")


def _bearer_credentials(
    websocket: WebSocket,
) -> HTTPAuthorizationCredentials | None:
    authorization = websocket.headers.get("authorization")
    if authorization is None:
        return None
    scheme, separator, credentials = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not credentials:
        return None
    return HTTPAuthorizationCredentials(scheme=scheme, credentials=credentials)


async def _current_websocket_session(websocket: WebSocket) -> SessionData:
    credentials = _bearer_credentials(websocket)
    return await get_current_session(
        credentials,
        websocket.app.state.session_store,
    )


async def _authorized_websocket_session(
    websocket: WebSocket,
) -> SessionData | None:
    try:
        current_session = await _current_websocket_session(websocket)
        await require_access_level(AccessLevel.USER)(current_session)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    except SessionStoreError:
        logger.warning("notification websocket session lookup failed")
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
        return None
    return current_session


@router.websocket("/stream")
async def stream_notifications(websocket: WebSocket) -> None:
    current_session = await _authorized_websocket_session(websocket)
    if current_session is None:
        return
    try:
        hub: RealtimeHub = websocket.app.state.notification_realtime_hub
    except AttributeError:
        logger.warning("notification realtime hub is unavailable")
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
        return

    channel = notification_channel(current_session.user_id)
    subscriber = _SafeWebSocketSubscriber(websocket)
    await websocket.accept()
    try:
        await hub.subscribe(channel, subscriber)
    except RuntimeError:
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
        return
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unsubscribe(channel, subscriber)
