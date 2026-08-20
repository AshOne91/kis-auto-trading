import asyncio
import os

import aio_pika
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from kis_auto_trading.application.observability import LOGGER, configure_logging
from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.messaging.protocol import EventMessage
from kis_auto_trading.infrastructure.messaging.rabbitmq import RabbitMQConsumer
from kis_auto_trading.infrastructure.outbox.inbox import ProcessedMessageInbox
from kis_auto_trading.modules.signal.generated.models import (
    SignalSubscriptionProjection,
)
from kis_auto_trading.modules.signal.generated.sqlalchemy_repositories import (
    SQLAlchemySignalSubscriptionProjectionRepository,
)
from kis_auto_trading.modules.signal.messaging import (
    SUBSCRIPTION_PROJECTION_QUEUE,
    SUBSCRIPTION_PROJECTION_ROUTING_KEY,
)
from kis_auto_trading.modules.signal.subscription_policy import (
    normalize_domestic_stock_code,
)

RABBITMQ_URL_ENV = "RABBITMQ_URL"
AUTOMATION_DATABASE_URL_ENV = "AUTOMATION_DATABASE_URL"
ACCOUNT_SHARD_URL_ENVS = {
    "1": "ACCOUNT_SHARD_1_DATABASE_URL",
    "2": "ACCOUNT_SHARD_2_DATABASE_URL",
}
logger = LOGGER


class ApplicationMessageHandler:
    def __init__(self, session_registry: AsyncSessionRegistry) -> None:
        self._session_registry = session_registry

    async def handle(self, message: EventMessage) -> None:
        if message.event_type == "account.profile.updated":
            await self._handle_profile_update(message)
            return
        if message.event_type == "signal.subscription.updated":
            await self._handle_signal_subscription_update(message)
            return
        raise ValueError(f"Unsupported event type: {message.event_type}")

    async def _handle_profile_update(self, message: EventMessage) -> None:
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

    async def _handle_signal_subscription_update(
        self, message: EventMessage
    ) -> None:
        projection = _subscription_projection_from_payload(message.payload)
        target = ShardTarget(store="automation")
        async with self._session_registry.session(target) as session:
            claimed = await ProcessedMessageInbox(session).claim(message.event_id)
            if not claimed:
                logger.info(
                    "duplicate signal subscription event skipped",
                    extra={"event_id": message.event_id},
                )
                return
            repository = SQLAlchemySignalSubscriptionProjectionRepository(session)
            existing = await repository.find_by_id(projection.subscription_id)
            if existing is not None and existing.revision >= projection.revision:
                logger.info(
                    "stale signal subscription event skipped",
                    extra={
                        "event_id": message.event_id,
                        "subscription_id": str(projection.subscription_id),
                    },
                )
                return
            await repository.save(projection)
            logger.info(
                "signal subscription projection updated",
                extra={
                    "event_id": message.event_id,
                    "subscription_id": str(projection.subscription_id),
                    "stock_code": projection.stock_code,
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
    configure_logging()
    logger.info("message worker starting")
    shard_engines = build_account_engines()
    automation_engine = create_async_engine(
        os.environ[AUTOMATION_DATABASE_URL_ENV], pool_pre_ping=True
    )
    session_registry = AsyncSessionRegistry(
        {"automation": automation_engine}, shard_engines
    )
    connection = await aio_pika.connect_robust(
        os.environ[RABBITMQ_URL_ENV]
    )
    consumer = RabbitMQConsumer(connection)
    handler = ApplicationMessageHandler(session_registry)
    try:
        await consumer.consume(handler)
        await consumer.consume(
            handler,
            queue_name=SUBSCRIPTION_PROJECTION_QUEUE,
            routing_keys=(SUBSCRIPTION_PROJECTION_ROUTING_KEY,),
        )
        await asyncio.Future()
    finally:
        await connection.close()
        await automation_engine.dispose()
        for engine in shard_engines.values():
            await engine.dispose()
        logger.info("message worker stopped")


def _subscription_projection_from_payload(
    payload: dict[str, object],
) -> SignalSubscriptionProjection:
    try:
        projection = SignalSubscriptionProjection.model_validate(payload)
        stock_code = normalize_domestic_stock_code(projection.stock_code)
    except (ValueError, TypeError) as error:
        raise ValueError("Invalid signal subscription event payload") from error
    return projection.model_copy(update={"stock_code": stock_code})


if __name__ == '__main__':
    asyncio.run(main())
