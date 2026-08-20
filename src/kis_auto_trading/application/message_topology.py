from aio_pika.abc import AbstractRobustConnection

from kis_auto_trading.modules.signal.messaging import (
    ensure_subscription_projection_topology,
)


async def declare_user_message_topology(
    connection: AbstractRobustConnection,
) -> None:
    await ensure_subscription_projection_topology(connection)
