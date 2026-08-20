import pytest

from kis_auto_trading.modules.signal import messaging


@pytest.mark.anyio
async def test_subscription_projection_topology_uses_declared_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, str, tuple[str, ...]]] = []

    async def fake_declare_topology(
        connection: object,
        *,
        queue_name: str,
        routing_keys: tuple[str, ...],
    ) -> None:
        calls.append((connection, queue_name, routing_keys))

    monkeypatch.setattr(messaging, "declare_topology", fake_declare_topology)
    connection = object()

    await messaging.ensure_subscription_projection_topology(connection)  # type: ignore[arg-type]

    assert calls == [
        (
            connection,
            "kis.signal-subscription-projection.events",
            ("signal.subscription.updated",),
        )
    ]


@pytest.mark.anyio
async def test_in_app_notification_topology_uses_declared_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, str, tuple[str, ...]]] = []

    async def fake_declare_topology(
        connection: object,
        *,
        queue_name: str,
        routing_keys: tuple[str, ...],
    ) -> None:
        calls.append((connection, queue_name, routing_keys))

    monkeypatch.setattr(messaging, "declare_topology", fake_declare_topology)
    connection = object()

    await messaging.ensure_in_app_notification_topology(connection)  # type: ignore[arg-type]

    assert calls == [
        (
            connection,
            "kis.in-app-notification.events",
            ("signal.delivery-intent.created",),
        )
    ]
