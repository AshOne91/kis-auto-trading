from __future__ import annotations

import asyncio
import json
import os
from contextlib import suppress

from redis.asyncio import Redis
from redis.asyncio.sentinel import Sentinel
from redis.exceptions import RedisError

from .protocol import RealtimeDeliveryHandler

REALTIME_TOPIC = "realtime.notifications.v1"
RECONNECT_DELAY_SECONDS = 1.0
REDIS_URL_ENV = "REDIS_URL"


class RealtimeBackplaneError(RuntimeError):
    pass


class RedisPubSubRealtimeBackplane:
    """Best-effort multi-replica hint transport over Redis Pub/Sub."""

    def __init__(
        self,
        urls: tuple[str, ...],
        *,
        topic: str = REALTIME_TOPIC,
        reconnect_delay_seconds: float = RECONNECT_DELAY_SECONDS,
        sentinel_master: str | None = None,
    ) -> None:
        if not urls:
            raise ValueError(
                "Redis realtime backplane requires at least one URL"
            )
        if not topic:
            raise ValueError("Redis realtime topic must not be empty")
        self._urls = urls
        self._topic = topic
        self._reconnect_delay_seconds = reconnect_delay_seconds
        self._sentinel_master = sentinel_master
        self._sentinel = (
            Sentinel(
                _sentinel_endpoints(urls),
                socket_timeout=2,
                decode_responses=True,
            )
            if sentinel_master is not None
            else None
        )
        self._publisher: Redis | None = None
        self._listener: asyncio.Task[None] | None = None
        self._closed = False

    @classmethod
    def from_environment(cls) -> RedisPubSubRealtimeBackplane:
        return cls(_redis_urls_from_environment())

    async def start(self, deliver: RealtimeDeliveryHandler) -> None:
        if self._closed:
            raise RealtimeBackplaneError("realtime backplane is closed")
        if self._listener is not None:
            raise RealtimeBackplaneError(
                "realtime backplane is already started"
            )
        self._listener = asyncio.create_task(self._listen(deliver))

    async def publish(self, channel: str, message: str) -> None:
        if self._closed:
            raise RealtimeBackplaneError("realtime backplane is closed")
        if not channel:
            raise ValueError("realtime channel must not be empty")
        payload = json.dumps({"channel": channel, "message": message})
        for _ in range(2):
            client = await self._publisher_client()
            try:
                await client.publish(self._topic, payload)
                return
            except RedisError:
                await self._discard_publisher()
        raise RealtimeBackplaneError("Redis realtime publish failed")

    async def aclose(self) -> None:
        self._closed = True
        listener = self._listener
        self._listener = None
        if listener is not None:
            listener.cancel()
            with suppress(asyncio.CancelledError):
                await listener
        await self._discard_publisher()
        if self._sentinel is not None:
            for sentinel_client in self._sentinel.sentinels:
                await sentinel_client.aclose()

    async def _publisher_client(self) -> Redis:
        if self._publisher is None:
            self._publisher = await self._open_client()
        return self._publisher

    async def _discard_publisher(self) -> None:
        publisher = self._publisher
        self._publisher = None
        if publisher is not None:
            await publisher.aclose()

    async def _listen(self, deliver: RealtimeDeliveryHandler) -> None:
        while not self._closed:
            client: Redis | None = None
            pubsub = None
            try:
                client = await self._open_client()
                pubsub = client.pubsub()
                await pubsub.subscribe(self._topic)
                while not self._closed:
                    event = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1.0
                    )
                    if event is None:
                        continue
                    payload = _decode_payload(event.get("data"))
                    if payload is not None:
                        await deliver(*payload)
            except (RedisError, RealtimeBackplaneError):
                pass
            finally:
                if pubsub is not None:
                    await pubsub.aclose()
                if client is not None:
                    await client.aclose()
            if not self._closed:
                await asyncio.sleep(self._reconnect_delay_seconds)

    async def _open_client(self) -> Redis:
        if self._sentinel is not None and self._sentinel_master is not None:
            return self._sentinel.master_for(
                self._sentinel_master,
                socket_timeout=2,
                decode_responses=True,
            )
        last_error: RedisError | None = None
        for url in self._urls:
            client = Redis.from_url(url, decode_responses=True)
            try:
                await client.ping()
                return client
            except RedisError as error:
                last_error = error
                await client.aclose()
        raise RealtimeBackplaneError(
            "Redis realtime connection failed"
        ) from last_error


def _redis_urls_from_environment() -> tuple[str, ...]:
    redis_url = os.environ.get(REDIS_URL_ENV)
    if not redis_url:
        raise RealtimeBackplaneError(
            f"Required environment variable is missing: {REDIS_URL_ENV}"
        )
    return (redis_url,)



def _sentinel_endpoints(values: tuple[str, ...]) -> list[tuple[str, int]]:
    endpoints: list[tuple[str, int]] = []
    for item in values:
        host, separator, port_text = item.rpartition(":")
        if not separator or not host:
            raise RealtimeBackplaneError(
                f"Invalid Redis Sentinel endpoint: {item!r}"
            )
        try:
            port = int(port_text)
        except ValueError as error:
            raise RealtimeBackplaneError(
                f"Invalid Redis Sentinel port: {item!r}"
            ) from error
        endpoints.append((host, port))
    if not endpoints:
        raise RealtimeBackplaneError("Redis Sentinel endpoints are empty")
    return endpoints


def _decode_payload(value: object) -> tuple[str, str] | None:
    if not isinstance(value, str):
        return None
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return None
    channel = payload.get("channel") if isinstance(payload, dict) else None
    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(channel, str) or not channel:
        return None
    if not isinstance(message, str):
        return None
    return channel, message
