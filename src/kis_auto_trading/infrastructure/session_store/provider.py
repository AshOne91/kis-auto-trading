import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from redis.asyncio import Redis

from .protocol import SessionStore, SessionStoreError
from .redis import RedisSessionStore

REDIS_URL_ENV = "REDIS_URL"


@asynccontextmanager
async def session_store_lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    redis_url = os.environ.get(REDIS_URL_ENV)
    if not redis_url:
        raise SessionStoreError(
            f"Required environment variable is missing: {REDIS_URL_ENV}"
        )
    client = Redis.from_url(redis_url, decode_responses=True)
    app.state.session_store = RedisSessionStore(client)
    try:
        yield
    finally:
        del app.state.session_store
        await client.aclose()


def get_session_store(request: Request) -> SessionStore:
    try:
        return request.app.state.session_store
    except AttributeError as error:
        raise SessionStoreError(
            "SessionStore is not initialized"
        ) from error
