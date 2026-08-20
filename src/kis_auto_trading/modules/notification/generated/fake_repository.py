from uuid import UUID

from kis_auto_trading.modules.notification.generated.models import InAppNotification


class FakeInAppNotificationRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, InAppNotification] = {}

    async def find_by_id(
        self, notification_id: UUID,
    ) -> InAppNotification | None:
        return self._items.get(notification_id)

    async def save(
        self, aggregate: InAppNotification,
    ) -> None:
        self._items[aggregate.notification_id] = aggregate

    async def list_by_user_id(
        self, user_id: UUID,
    ) -> list[InAppNotification]:
        items = [
            item for item in self._items.values()
            if item.user_id == user_id
        ]
        return sorted(
            items,
            key=lambda item: item.created_at,
            reverse=True,
        )[:100]
