from sqlalchemy import select

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.modules.signal.generated.models import (
    SignalDeliveryIntent,
    SignalSubscriptionProjection,
)
from kis_auto_trading.modules.signal.generated.sqlalchemy_models import (
    SignalDeliveryIntentRecord,
    SignalSubscriptionProjectionRecord,
)
from kis_auto_trading.modules.signal.subscription_policy import (
    normalize_domestic_stock_code,
)


async def list_enabled_signal_subscriptions(
    session_registry: AsyncSessionRegistry,
    stock_code: str,
    *,
    limit: int,
) -> list[SignalSubscriptionProjection]:
    normalized_stock_code = normalize_domestic_stock_code(stock_code)
    statement = (
        select(SignalSubscriptionProjectionRecord)
        .where(
            SignalSubscriptionProjectionRecord.stock_code == normalized_stock_code,
            SignalSubscriptionProjectionRecord.enabled.is_(True),
        )
        .order_by(SignalSubscriptionProjectionRecord.subscription_id)
        .limit(limit)
    )
    async with session_registry.session(ShardTarget(store="automation")) as session:
        result = await session.scalars(statement)
        return [
            SignalSubscriptionProjection(
                subscription_id=record.subscription_id,
                user_id=record.user_id,
                shard_id=record.shard_id,
                stock_code=record.stock_code,
                enabled=record.enabled,
                revision=record.revision,
            )
            for record in result.all()
        ]


async def list_pending_signal_delivery_intents(
    session_registry: AsyncSessionRegistry,
    stock_code: str,
    *,
    limit: int,
) -> list[SignalDeliveryIntent]:
    normalized_stock_code = normalize_domestic_stock_code(stock_code)
    statement = (
        select(SignalDeliveryIntentRecord)
        .where(
            SignalDeliveryIntentRecord.stock_code == normalized_stock_code,
            SignalDeliveryIntentRecord.status == "pending",
        )
        .order_by(SignalDeliveryIntentRecord.intent_id)
        .limit(limit)
    )
    async with session_registry.session(ShardTarget(store="automation")) as session:
        result = await session.scalars(statement)
        return [
            SignalDeliveryIntent(
                intent_id=record.intent_id,
                signal_id=record.signal_id,
                subscription_id=record.subscription_id,
                user_id=record.user_id,
                shard_id=record.shard_id,
                stock_code=record.stock_code,
                expires_at=record.expires_at,
                status=record.status,
            )
            for record in result.all()
        ]
