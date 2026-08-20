import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI

from kis_auto_trading.infrastructure.realtime import (
    RealtimeHub,
    RedisPubSubRealtimeBackplane,
)


def notification_channel(user_id: str) -> str:
    if not user_id:
        raise ValueError("notification user_id must not be empty")
    return f"notification:{user_id}"


def notification_hint(notification_id: UUID) -> str:
    return json.dumps(
        {"notification_id": str(notification_id)}, separators=(",", ":")
    )


@asynccontextmanager
async def realtime_notifications_lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    hub = RealtimeHub()
    backplane = RedisPubSubRealtimeBackplane.from_environment()
    await backplane.start(hub.publish)
    app.state.notification_realtime_hub = hub
    try:
        yield
    finally:
        del app.state.notification_realtime_hub
        await backplane.aclose()
        await hub.aclose()
