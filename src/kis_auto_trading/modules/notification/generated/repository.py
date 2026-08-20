from typing import Protocol
from uuid import UUID

from kis_auto_trading.modules.notification.generated.models import InAppNotification


class InAppNotificationRepository(Protocol):
    async def find_by_id(
        self, notification_id: UUID,
    ) -> InAppNotification | None: ...
    async def save(
        self, aggregate: InAppNotification,
    ) -> None: ...
