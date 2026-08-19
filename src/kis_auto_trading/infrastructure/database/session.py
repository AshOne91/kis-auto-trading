from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from kis_auto_trading.infrastructure.database.routing import (
    ShardRoutingError,
    ShardTarget,
)


class AsyncSessionRegistry:
    def __init__(
        self,
        global_engines: Mapping[str, AsyncEngine],
        shard_engines: Mapping[tuple[str, str], AsyncEngine],
    ) -> None:
        self._global_engines = dict(global_engines)
        self._shard_engines = dict(shard_engines)

    @asynccontextmanager
    async def session(
        self, target: ShardTarget,
    ) -> AsyncIterator[AsyncSession]:
        engine = self._engine_for(target)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session, session.begin():
            yield session

    async def health_check(self) -> None:
        for engine in (
            *self._global_engines.values(), *self._shard_engines.values()
        ):
            async with engine.connect() as connection:
                await connection.execute(text('SELECT 1'))

    def _engine_for(self, target: ShardTarget) -> AsyncEngine:
        if target.is_global:
            engine = self._global_engines.get(target.store)
        else:
            assert target.shard_id is not None
            engine = self._shard_engines.get(
                (target.store, target.shard_id)
            )
        if engine is None:
            raise ShardRoutingError(
                f"Database engine is not configured: {target}"
            )
        return engine
