from __future__ import annotations

import json
import logging
from datetime import datetime

import aio_pika
from aio_pika.abc import (
    AbstractIncomingMessage,
    AbstractRobustConnection,
    AbstractRobustExchange,
    AbstractRobustQueue,
)
from aio_pika.exceptions import CONNECTION_EXCEPTIONS

from .protocol import EventMessage, MessageHandler, MessagePublishError

logger = logging.getLogger(__name__)

EXCHANGE_NAME = "kis.domain.events"
QUEUE_NAME = "kis.profile.events"
ROUTING_KEY = "account.profile.#"
DEAD_LETTER_EXCHANGE = "kis.domain.events.dlx"
DEAD_LETTER_QUEUE = "kis.profile.events.dead-letter"
PREFETCH_COUNT = 32


async def declare_topology(
    connection: AbstractRobustConnection,
    *,
    queue_name: str = QUEUE_NAME,
    routing_keys: tuple[str, ...] = (ROUTING_KEY,),
) -> tuple[AbstractRobustExchange, AbstractRobustQueue]:
    channel = await connection.channel(
        publisher_confirms=True, on_return_raises=True
    )
    await channel.set_qos(prefetch_count=PREFETCH_COUNT)
    dead_letter_exchange = await channel.declare_exchange(
        DEAD_LETTER_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
    )
    dead_letter_queue = await channel.declare_queue(
        DEAD_LETTER_QUEUE, durable=True
    )
    await dead_letter_queue.bind(dead_letter_exchange, routing_key='#')
    exchange = await channel.declare_exchange(
        EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
    )
    queue = await channel.declare_queue(
        queue_name,
        durable=True,
        arguments={'x-dead-letter-exchange': DEAD_LETTER_EXCHANGE},
    )
    for routing_key in routing_keys:
        await queue.bind(exchange, routing_key=routing_key)
    return exchange, queue


class RabbitMQPublisher:
    def __init__(self, connection: AbstractRobustConnection) -> None:
        self._connection = connection
        self._exchange: AbstractRobustExchange | None = None

    async def start(self) -> None:
        self._exchange, _ = await declare_topology(self._connection)

    async def publish(self, message: EventMessage) -> None:
        if self._exchange is None:
            await self.start()
        assert self._exchange is not None
        occurred_at = message.occurred_at
        assert occurred_at is not None
        body = json.dumps(
            {
                'event_id': message.event_id,
                'event_type': message.event_type,
                'event_version': message.event_version,
                'aggregate_id': message.aggregate_id,
                'payload': message.payload,
                'routing_key': message.routing_key,
                'occurred_at': occurred_at.isoformat(),
            },
            separators=(',', ':'),
            sort_keys=True,
        ).encode('utf-8')
        try:
            await self._exchange.publish(
                aio_pika.Message(
                    body=body,
                    message_id=message.event_id,
                    type=message.event_type,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type='application/json',
                ),
                routing_key=message.routing_key,
                mandatory=True,
            )
        except CONNECTION_EXCEPTIONS as error:
            raise MessagePublishError(str(error)) from error


class RabbitMQConsumer:
    def __init__(self, connection: AbstractRobustConnection) -> None:
        self._connection = connection

    async def consume(
        self,
        handler: MessageHandler,
        *,
        queue_name: str = QUEUE_NAME,
        routing_keys: tuple[str, ...] = (ROUTING_KEY,),
    ) -> None:
        _, queue = await declare_topology(
            self._connection, queue_name=queue_name, routing_keys=routing_keys
        )

        async def process(message: AbstractIncomingMessage) -> None:
            try:
                async with message.process(requeue=False):
                    decoded = json.loads(message.body.decode('utf-8'))
                    await handler.handle(
                        EventMessage(
                            event_id=decoded['event_id'],
                            event_type=decoded['event_type'],
                            event_version=decoded['event_version'],
                            aggregate_id=decoded['aggregate_id'],
                            payload=decoded['payload'],
                            routing_key=decoded['routing_key'],
                            occurred_at=datetime.fromisoformat(
                                decoded['occurred_at']
                            ),
                        )
                    )
            except Exception:
                logger.exception(
                    'message rejected after handler failure',
                    extra={'message_id': message.message_id},
                )

        await queue.consume(process, no_ack=False)
