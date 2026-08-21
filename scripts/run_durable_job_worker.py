import asyncio
import os
from contextlib import suppress

import aio_pika
from sqlalchemy.ext.asyncio import create_async_engine

from kis_auto_trading.application.durable_job_handler import (
    create_durable_job_handler,
)
from kis_auto_trading.application.generated.service_heartbeat import (
    run_service_heartbeat_reporter,
)
from kis_auto_trading.application.observability import LOGGER, configure_logging
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.durable_jobs.worker import DurableJobMessageHandler
from kis_auto_trading.infrastructure.messaging.rabbitmq import RabbitMQConsumer

RABBITMQ_URL_ENV = "RABBITMQ_URL"
DURABLE_JOB_QUEUE = "kis.profile.events.durable-jobs"
DURABLE_JOB_EVENT_TYPES = ["news.collection.requested", "news.index.requested", "durable-job.history.index.requested", "market-price.snapshot.requested", "market-history.domestic-daily.collection.requested"]
GLOBAL_DATABASE_URL_ENVS = {"automation": "AUTOMATION_DATABASE_URL"}


async def main() -> None:
    configure_logging()
    LOGGER.info('durable job worker starting')
    engines = {
        store: create_async_engine(os.environ[environment_name], pool_pre_ping=True)
        for store, environment_name in GLOBAL_DATABASE_URL_ENVS.items()
    }
    registry = AsyncSessionRegistry(engines, {})
    connection = await aio_pika.connect_robust(os.environ[RABBITMQ_URL_ENV])
    consumer = RabbitMQConsumer(connection)
    handler = DurableJobMessageHandler(
        registry, create_durable_job_handler(registry)
    )
    heartbeat_task = asyncio.create_task(
        run_service_heartbeat_reporter(
            service_name='kis_auto_trading' + '-durable-job-worker',
            dependencies={'database': 'ok', 'rabbitmq': 'ok'},
        ),
        name='durable-job-worker-heartbeat',
    )
    try:
        await consumer.consume(
            handler,
            queue_name=DURABLE_JOB_QUEUE,
            routing_keys=tuple(DURABLE_JOB_EVENT_TYPES),
        )
        await asyncio.Future()
    finally:
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task
        await connection.close()
        for engine in engines.values():
            await engine.dispose()
        LOGGER.info('durable job worker stopped')


if __name__ == '__main__':
    asyncio.run(main())
