import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis

from .protocol import RequestReplayStore, SessionData, SessionStore, SessionStoreError
from .redis import RedisSessionStore
from .request_replay import RedisRequestReplayStore

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
    app.state.request_replay_store = RedisRequestReplayStore(client, "kis_session")
    try:
        yield
    finally:
        del app.state.session_store
        del app.state.request_replay_store
        await client.aclose()


def get_session_store(request: Request) -> SessionStore:
    try:
        return request.app.state.session_store
    except AttributeError as error:
        raise SessionStoreError(
            "SessionStore is not initialized"
        ) from error


def get_request_replay_store(request: Request) -> RequestReplayStore:
    try:
        return request.app.state.request_replay_store
    except AttributeError as error:
        raise SessionStoreError(
            "RequestReplayStore is not initialized"
        ) from error


bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_session(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    session_store: Annotated[SessionStore, Depends(get_session_store)],
) -> SessionData:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer session is required",
        )
    session = await session_store.get(credentials.credentials)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )
    return session
