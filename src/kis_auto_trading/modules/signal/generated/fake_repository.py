from uuid import UUID

from kis_auto_trading.modules.signal.generated.models import (
    SignalEvent,
    SignalSubscription,
    SignalSubscriptionProjection,
)


class FakeSignalEventRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, SignalEvent] = {}

    async def find_by_id(
        self, signal_id: UUID,
    ) -> SignalEvent | None:
        return self._items.get(signal_id)

    async def save(
        self, aggregate: SignalEvent,
    ) -> None:
        self._items[aggregate.signal_id] = aggregate


class FakeSignalSubscriptionRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, SignalSubscription] = {}

    async def find_by_id(
        self, subscription_id: UUID,
    ) -> SignalSubscription | None:
        return self._items.get(subscription_id)

    async def save(
        self, aggregate: SignalSubscription,
    ) -> None:
        self._items[aggregate.subscription_id] = aggregate


class FakeSignalSubscriptionProjectionRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, SignalSubscriptionProjection] = {}

    async def find_by_id(
        self, subscription_id: UUID,
    ) -> SignalSubscriptionProjection | None:
        return self._items.get(subscription_id)

    async def save(
        self, aggregate: SignalSubscriptionProjection,
    ) -> None:
        self._items[aggregate.subscription_id] = aggregate
