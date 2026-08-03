from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from kis_auto_trading.infrastructure.database.provider import (
    database_lifespan,
)
from kis_auto_trading.infrastructure.session_store.provider import (
    session_store_lifespan,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(database_lifespan(app))
        await stack.enter_async_context(session_store_lifespan(app))
        yield
