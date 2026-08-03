import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio.cluster import RedisCluster

from .protocol import SessionData, SessionStore, SessionStoreError
from .redis import RedisSessionStore

REDIS_CLUSTER_URL_ENV = "REDIS_CLUSTER_URL"


@asynccontextmanager
async def session_store_lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    cluster_url = os.environ.get(REDIS_CLUSTER_URL_ENV)
    if not cluster_url:
        raise SessionStoreError(
            f"Required environment variable is missing: "
            f"{REDIS_CLUSTER_URL_ENV}"
        )
    client = RedisCluster.from_url(
        cluster_url,
        decode_responses=True,
        require_full_coverage=True,
        reinitialize_steps=1,
    )
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
