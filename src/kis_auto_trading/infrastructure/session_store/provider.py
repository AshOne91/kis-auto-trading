import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from redis.asyncio.sentinel import Sentinel

from .protocol import SessionStore, SessionStoreError
from .redis import RedisSessionStore

REDIS_SENTINEL_URLS_ENV = "REDIS_SENTINEL_URLS"
REDIS_SENTINEL_MASTER = "kis-session"


def _sentinel_endpoints(value: str) -> list[tuple[str, int]]:
    endpoints: list[tuple[str, int]] = []
    for item in value.split(','):
        host, separator, port_text = item.strip().rpartition(':')
        if not separator or not host:
            raise SessionStoreError(
                f"Invalid Redis Sentinel endpoint: {item!r}"
            )
        try:
            port = int(port_text)
        except ValueError as error:
            raise SessionStoreError(
                f"Invalid Redis Sentinel port: {item!r}"
            ) from error
        endpoints.append((host, port))
    if not endpoints:
        raise SessionStoreError("Redis Sentinel endpoints are empty")
    return endpoints


@asynccontextmanager
async def session_store_lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    raw_urls = os.environ.get(REDIS_SENTINEL_URLS_ENV)
    if not raw_urls:
        raise SessionStoreError(
            f"Required environment variable is missing: "
            f"{REDIS_SENTINEL_URLS_ENV}"
        )
    sentinel = Sentinel(
        _sentinel_endpoints(raw_urls),
        socket_timeout=2,
        decode_responses=True,
    )
    client = sentinel.master_for(
        REDIS_SENTINEL_MASTER,
        socket_timeout=2,
        decode_responses=True,
    )
    app.state.session_store = RedisSessionStore(client)
    try:
        yield
    finally:
        del app.state.session_store
        await client.aclose()
        for sentinel_client in sentinel.sentinels:
            await sentinel_client.aclose()


def get_session_store(request: Request) -> SessionStore:
    try:
        return request.app.state.session_store
    except AttributeError as error:
        raise SessionStoreError(
            "SessionStore is not initialized"
        ) from error
