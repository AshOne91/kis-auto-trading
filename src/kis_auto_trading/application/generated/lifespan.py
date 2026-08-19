from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from kis_auto_trading.application import extensions
from kis_auto_trading.application.generated.service_heartbeat import (
    service_heartbeat_lifespan,
)
from kis_auto_trading.application.observability import LOGGER
from kis_auto_trading.infrastructure.database.provider import (
    database_lifespan,
)
from kis_auto_trading.infrastructure.session_store.provider import (
    session_store_lifespan,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    LOGGER.info('application starting')
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(database_lifespan(app))
        await stack.enter_async_context(session_store_lifespan(app))
        await stack.enter_async_context(service_heartbeat_lifespan(app))
        for lifespan_factory in getattr(extensions, 'USER_LIFESPANS', ()):
            await stack.enter_async_context(lifespan_factory(app))
        try:
            yield
        finally:
            LOGGER.info('application stopping')
