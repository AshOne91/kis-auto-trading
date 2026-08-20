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
