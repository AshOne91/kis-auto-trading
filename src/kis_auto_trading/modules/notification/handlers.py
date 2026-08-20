from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.session_store.protocol import SessionData
from kis_auto_trading.modules.notification.generated.models import InAppNotification
from kis_auto_trading.modules.notification.generated.sqlalchemy_repositories import (
    SQLAlchemyInAppNotificationRepository,
)


async def list_user_notifications(
    current_session: SessionData,
    session_registry: AsyncSessionRegistry,
) -> list[InAppNotification]:
    user_id, target = _notification_location(current_session)
    async with session_registry.session(target) as session:
        repository = SQLAlchemyInAppNotificationRepository(session)
        return await repository.list_by_user_id(user_id)


async def mark_user_notification_read(
    notification_id: UUID,
    current_session: SessionData,
    session_registry: AsyncSessionRegistry,
) -> InAppNotification:
    user_id, target = _notification_location(current_session)
    async with session_registry.session(target) as session:
        repository = SQLAlchemyInAppNotificationRepository(session)
        notification = await repository.find_by_id(notification_id)
        if notification is None or notification.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification was not found",
            )
        if notification.read_at is not None:
            return notification
        updated = notification.model_copy(update={"read_at": datetime.now(UTC)})
        await repository.save(updated)
        return updated


def _notification_location(session: SessionData) -> tuple[UUID, ShardTarget]:
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
