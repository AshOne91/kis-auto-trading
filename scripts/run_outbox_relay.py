import asyncio
import os

import aio_pika
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from kis_auto_trading.infrastructure.messaging.rabbitmq import RabbitMQPublisher
from kis_auto_trading.infrastructure.outbox.relay import OutboxRelay

DATABASE_URL_ENVS = ["AUTOMATION_DATABASE_URL", "ACCOUNT_SHARD_1_DATABASE_URL", "ACCOUNT_SHARD_2_DATABASE_URL"]
RABBITMQ_URL_ENV = "RABBITMQ_URL"


async def main() -> None:
    rabbitmq_url = os.environ[RABBITMQ_URL_ENV]
    connection = await aio_pika.connect_robust(rabbitmq_url)
    publisher = RabbitMQPublisher(connection)
    await publisher.start()
    engines = [
        create_async_engine(os.environ[name], pool_pre_ping=True)
        for name in DATABASE_URL_ENVS
    ]
    relay = OutboxRelay(publisher)
    try:
        while True:
            published = 0
            for engine in engines:
                factory = async_sessionmaker(engine, expire_on_commit=False)
                async with factory() as session, session.begin():
                    published += await relay.publish_pending(session)
            if published == 0:
                await asyncio.sleep(1)
    finally:
        for engine in engines:
            await engine.dispose()
        await connection.close()


if __name__ == '__main__':
    asyncio.run(main())
