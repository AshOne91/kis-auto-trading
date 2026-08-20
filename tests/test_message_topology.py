import pytest

from kis_auto_trading.application import message_topology


@pytest.mark.anyio
async def test_user_message_topology_declares_signal_subscription_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    async def fake_declare(connection: object) -> None:
        calls.append(connection)

    monkeypatch.setattr(
        message_topology,
        "ensure_subscription_projection_topology",
        fake_declare,
    )
    connection = object()

    await message_topology.declare_user_message_topology(connection)  # type: ignore[arg-type]

    assert calls == [connection]
