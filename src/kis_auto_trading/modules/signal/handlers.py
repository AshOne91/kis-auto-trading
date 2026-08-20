from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.messaging.protocol import EventMessage
from kis_auto_trading.infrastructure.outbox.repository import OutboxWriter
from kis_auto_trading.infrastructure.session_store.protocol import SessionData
from kis_auto_trading.modules.signal.generated.models import (
    SignalEvent,
    SignalSubscription,
)
from kis_auto_trading.modules.signal.generated.schemas import (
    SubscribeRequest,
    UnsubscribeRequest,
)
from kis_auto_trading.modules.signal.generated.sqlalchemy_repositories import (
    SQLAlchemySignalEventRepository,
    SQLAlchemySignalSubscriptionRepository,
)


async def record_signal(
    signal: SignalEvent,
    session_registry: AsyncSessionRegistry,
) -> SignalEvent:
    """Persist a signal and enqueue its domain event in one transaction."""
    async with session_registry.session(ShardTarget(store="automation")) as session:
        repository = SQLAlchemySignalEventRepository(session)
        existing = await repository.find_by_id(signal.signal_id)
        if existing is not None:
            return existing

        await repository.save(signal)
        OutboxWriter(session).add(
            EventMessage(
                event_type="signal.created",
                aggregate_id=str(signal.signal_id),
                routing_key="signal.created",
                payload=signal.model_dump(mode="json"),
            )
        )
    return signal


async def subscribe(
    request: SubscribeRequest,
    current_session: SessionData,
    session_registry: AsyncSessionRegistry,
) -> SignalSubscription:
    user_id, target = _subscription_location(current_session)
    stock_code = _domestic_stock_code(request.stock_code)
    subscription_id = _subscription_id(user_id, stock_code)
    async with session_registry.session(target) as session:
        repository = SQLAlchemySignalSubscriptionRepository(session)
        existing = await repository.find_by_id(subscription_id)
        if existing is not None and existing.enabled:
            return existing
        subscription = SignalSubscription(
            subscription_id=subscription_id,
            user_id=user_id,
            stock_code=stock_code,
            enabled=True,
        )
        await repository.save(subscription)
        _record_subscription_update(session, subscription, target)
    return subscription


async def unsubscribe(
    request: UnsubscribeRequest,
    current_session: SessionData,
    session_registry: AsyncSessionRegistry,
) -> SignalSubscription:
    user_id, target = _subscription_location(current_session)
    stock_code = _domestic_stock_code(request.stock_code)
    subscription_id = _subscription_id(user_id, stock_code)
    async with session_registry.session(target) as session:
        repository = SQLAlchemySignalSubscriptionRepository(session)
        existing = await repository.find_by_id(subscription_id)
        if existing is None or not existing.enabled:
            return existing or SignalSubscription(
                subscription_id=subscription_id,
                user_id=user_id,
                stock_code=stock_code,
                enabled=False,
            )
        subscription = existing.model_copy(update={"enabled": False})
        await repository.save(subscription)
        _record_subscription_update(session, subscription, target)
    return subscription


def _subscription_location(session: SessionData) -> tuple[UUID, ShardTarget]:
    shard_id = session.data.get("shard_id")
    if not isinstance(shard_id, str) or not shard_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session shard is missing",
        )
    try:
        user_id = UUID(session.user_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session user is invalid",
        ) from error
    return user_id, ShardTarget(store="account", shard_id=shard_id)


def _domestic_stock_code(stock_code: str) -> str:
    normalized = stock_code.strip()
    if len(normalized) != 6 or not normalized.isascii() or not normalized.isdecimal():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="stock_code must be a six-digit domestic stock code",
        )
    return normalized


def _subscription_id(user_id: UUID, stock_code: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"kis-auto-trading:signal-subscription:{user_id}:{stock_code}")


def _record_subscription_update(
    session: AsyncSession,
    subscription: SignalSubscription,
    target: ShardTarget,
) -> None:
    OutboxWriter(session).add(
        EventMessage(
            event_type="signal.subscription.updated",
            aggregate_id=str(subscription.subscription_id),
            routing_key="signal.subscription.updated",
            payload={
                "subscription_id": str(subscription.subscription_id),
                "user_id": str(subscription.user_id),
                "shard_id": target.shard_id or "",
                "stock_code": subscription.stock_code,
                "enabled": subscription.enabled,
            },
        )
    )
