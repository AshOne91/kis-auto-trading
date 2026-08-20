from aio_pika.abc import AbstractRobustConnection

from kis_auto_trading.infrastructure.messaging.rabbitmq import declare_topology

SUBSCRIPTION_PROJECTION_QUEUE = "kis.signal-subscription-projection.events"
SUBSCRIPTION_PROJECTION_ROUTING_KEY = "signal.subscription.updated"
DELIVERY_INTENT_QUEUE = "kis.signal-delivery-intent.events"
DELIVERY_INTENT_ROUTING_KEY = "signal.created"


async def ensure_subscription_projection_topology(
    connection: AbstractRobustConnection,
) -> None:
    await declare_topology(
        connection,
        queue_name=SUBSCRIPTION_PROJECTION_QUEUE,
        routing_keys=(SUBSCRIPTION_PROJECTION_ROUTING_KEY,),
    )


async def ensure_delivery_intent_topology(
    connection: AbstractRobustConnection,
) -> None:
    await declare_topology(
        connection,
        queue_name=DELIVERY_INTENT_QUEUE,
        routing_keys=(DELIVERY_INTENT_ROUTING_KEY,),
    )
