from aio_pika.abc import AbstractRobustConnection

from kis_auto_trading.infrastructure.messaging.rabbitmq import declare_topology

SUBSCRIPTION_PROJECTION_QUEUE = "kis.signal-subscription-projection.events"
SUBSCRIPTION_PROJECTION_ROUTING_KEY = "signal.subscription.updated"


async def ensure_subscription_projection_topology(
    connection: AbstractRobustConnection,
) -> None:
    await declare_topology(
        connection,
        queue_name=SUBSCRIPTION_PROJECTION_QUEUE,
        routing_keys=(SUBSCRIPTION_PROJECTION_ROUTING_KEY,),
    )
