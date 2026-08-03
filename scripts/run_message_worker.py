import asyncio
import logging
import os

import aio_pika
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.messaging.protocol import EventMessage
from kis_auto_trading.infrastructure.messaging.rabbitmq import RabbitMQConsumer
from kis_auto_trading.infrastructure.outbox.inbox import ProcessedMessageInbox

RABBITMQ_URL_ENV = "RABBITMQ_URL"
ACCOUNT_SHARD_URL_ENVS = {
    "1": "ACCOUNT_SHARD_1_DATABASE_URL",
    "2": "ACCOUNT_SHARD_2_DATABASE_URL",
}
logger = logging.getLogger(__name__)


class ApplicationMessageHandler:
    def __init__(self, session_registry: AsyncSessionRegistry) -> None:
        self._session_registry = session_registry

    async def handle(self, message: EventMessage) -> None:
        if message.event_type != "account.profile.updated":
            raise ValueError(f"Unsupported event type: {message.event_type}")
        shard_id = message.payload.get("shard_id")
        if not isinstance(shard_id, str) or shard_id not in ACCOUNT_SHARD_URL_ENVS:
            raise ValueError(f"Invalid account shard: {shard_id!r}")

        target = ShardTarget(store="account", shard_id=shard_id)
        async with self._session_registry.session(target) as session:
            claimed = await ProcessedMessageInbox(session).claim(message.event_id)
            if not claimed:
                logger.info(
                    "duplicate profile event skipped",
                    extra={"event_id": message.event_id},
                )
                return
            logger.info(
                "profile event processed",
                extra={
                    "event_id": message.event_id,
                    "user_id": message.aggregate_id,
                    "shard_id": shard_id,
                },
            )


def build_account_engines() -> dict[tuple[str, str], AsyncEngine]:
    return {
        ("account", shard_id): create_async_engine(
            os.environ[environment_name], pool_pre_ping=True
        )
        for shard_id, environment_name in ACCOUNT_SHARD_URL_ENVS.items()
    }


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    shard_engines = build_account_engines()
    session_registry = AsyncSessionRegistry({}, shard_engines)
    connection = await aio_pika.connect_robust(
        os.environ[RABBITMQ_URL_ENV]
    )
    consumer = RabbitMQConsumer(connection)
    try:
        await consumer.consume(ApplicationMessageHandler(session_registry))
        await asyncio.Future()
    finally:
        await connection.close()
        for engine in shard_engines.values():
            await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
