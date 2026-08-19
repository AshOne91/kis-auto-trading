from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from kis_auto_trading.infrastructure.access_control import (
    AccessLevel,
    require_access_level,
)
from kis_auto_trading.infrastructure.session_store.protocol import SessionData
from kis_auto_trading.infrastructure.session_store.provider import get_current_session
from kis_auto_trading.modules.identity.generated.router import router as identity_router


def _app(access_level: object) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_current_session] = lambda: SessionData(
        session_id="session",
        user_id="user",
        data={"access_level": access_level},
    )

    @app.get("/operator", dependencies=[Depends(require_access_level(AccessLevel.OPERATOR))])
    async def operator_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    return app


def test_generated_access_control_enforces_ranked_session_claims() -> None:
    with TestClient(_app("user")) as client:
        assert client.get("/operator").status_code == 403

    with TestClient(_app("operator")) as client:
        assert client.get("/operator").status_code == 200

    with TestClient(_app("invalid")) as client:
        assert client.get("/operator").status_code == 403


def test_operator_session_route_returns_only_for_operator_claim() -> None:
    def app_for(level: str) -> FastAPI:
        app = FastAPI()
        app.dependency_overrides[get_current_session] = lambda: SessionData(
            session_id="session",
            user_id="00000000-0000-0000-0000-000000000001",
            data={"access_level": level},
        )
        app.include_router(identity_router)
        return app

    with TestClient(app_for("user")) as client:
        assert client.get("/api/identity/operator/session").status_code == 403

    with TestClient(app_for("operator")) as client:
        response = client.get("/api/identity/operator/session")

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "access_level": "operator",
    }
