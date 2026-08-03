import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry

GLOBAL_DATABASES = [('identity', 'IDENTITY_DATABASE_URL')]
SHARD_DATABASES = [('account', '1', 'ACCOUNT_SHARD_1_DATABASE_URL'), ('account', '2', 'ACCOUNT_SHARD_2_DATABASE_URL')]


class DatabaseConfigurationError(RuntimeError):
    pass


def _required_url(environment_name: str) -> str:
    value = os.environ.get(environment_name)
    if not value:
        raise DatabaseConfigurationError(
            f"Required environment variable is missing: "
            f"{environment_name}"
        )
    return value


@asynccontextmanager
async def database_lifespan(app: FastAPI) -> AsyncIterator[None]:
    engines: list[AsyncEngine] = []
    global_engines: dict[str, AsyncEngine] = {}
    shard_engines: dict[tuple[str, str], AsyncEngine] = {}
    registry_registered = False
    try:
        for store, environment_name in GLOBAL_DATABASES:
            engine = create_async_engine(
                _required_url(environment_name), pool_pre_ping=True
            )
            engines.append(engine)
            global_engines[store] = engine
        for store, shard_id, environment_name in SHARD_DATABASES:
            engine = create_async_engine(
                _required_url(environment_name), pool_pre_ping=True
            )
            engines.append(engine)
            shard_engines[(store, shard_id)] = engine
        app.state.session_registry = AsyncSessionRegistry(
            global_engines, shard_engines
        )
        registry_registered = True
        yield
    finally:
        if registry_registered:
            del app.state.session_registry
        for engine in reversed(engines):
            await engine.dispose()


def get_session_registry(request: Request) -> AsyncSessionRegistry:
    try:
        return request.app.state.session_registry
    except AttributeError as error:
        raise DatabaseConfigurationError(
            "Database session registry is not initialized"
        ) from error
