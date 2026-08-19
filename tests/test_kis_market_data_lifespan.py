from __future__ import annotations

import pytest
from fastapi import FastAPI

from kis_auto_trading.application import extensions


class _FakeMarketDataClient:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.anyio
async def test_kis_market_data_lifespan_registers_and_closes_the_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeMarketDataClient()
    monkeypatch.setattr(
        extensions.KisMarketDataClient,
        "from_environment",
        classmethod(lambda cls: client),
    )
    app = FastAPI()

    async with extensions.kis_market_data_lifespan(app):
        assert app.state.kis_market_data is client
        assert client.closed is False

    assert not hasattr(app.state, "kis_market_data")
    assert client.closed is True
