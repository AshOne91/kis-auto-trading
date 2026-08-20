from typing import Protocol
from uuid import UUID

from kis_auto_trading.modules.signal.generated.models import (
    SignalDeliveryIntent,
    SignalEvent,
    SignalSubscription,
    SignalSubscriptionProjection,
)


class SignalEventRepository(Protocol):
    async def find_by_id(
        self, signal_id: UUID,
    ) -> SignalEvent | None: ...
    async def save(
        self, aggregate: SignalEvent,
    ) -> None: ...


class SignalSubscriptionRepository(Protocol):
    async def find_by_id(
        self, subscription_id: UUID,
    ) -> SignalSubscription | None: ...
    async def save(
        self, aggregate: SignalSubscription,
    ) -> None: ...


class SignalSubscriptionProjectionRepository(Protocol):
    async def find_by_id(
        self, subscription_id: UUID,
    ) -> SignalSubscriptionProjection | None: ...
    async def save(
        self, aggregate: SignalSubscriptionProjection,
    ) -> None: ...


class SignalDeliveryIntentRepository(Protocol):
    async def find_by_id(
        self, intent_id: UUID,
    ) -> SignalDeliveryIntent | None: ...
    async def save(
        self, aggregate: SignalDeliveryIntent,
    ) -> None: ...
