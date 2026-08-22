import hashlib
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from kis_auto_trading.infrastructure.access_control import (
    AccessLevel,
    require_access_level,
)
from kis_auto_trading.infrastructure.database.provider import get_session_registry
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.session_store.protocol import (
    ReplayRecord,
    RequestReplayConflict,
    RequestReplayInProgress,
    RequestReplayStore,
    SessionData,
)
from kis_auto_trading.infrastructure.session_store.provider import (
    get_current_session,
    get_request_replay_store,
)
from kis_auto_trading.modules.brokerage_account import handlers
from kis_auto_trading.modules.brokerage_account.generated.models import (
    BrokerageAccountConnection,
)

router = APIRouter(prefix="/api/brokerage-account", tags=["Brokerage Account"])


@router.put("/connection", response_model=BrokerageAccountConnection, dependencies=[Depends(require_access_level(AccessLevel.USER))])
async def link_default_connection(
    http_request: Request,
    current_session: Annotated[SessionData, Depends(get_current_session)],
    session_registry: Annotated[AsyncSessionRegistry, Depends(get_session_registry)],
    replay_store: Annotated[RequestReplayStore, Depends(get_request_replay_store)],
) -> BrokerageAccountConnection:
    idempotency_key = http_request.headers.get("Idempotency-Key")
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    fingerprint_source = "PUT:/connection:" + ""
    fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()
    try:
        replay = await replay_store.claim(idempotency_key, fingerprint, 86400)
    except RequestReplayConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RequestReplayInProgress as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if isinstance(replay, ReplayRecord):
        return JSONResponse(status_code=replay.status_code, content=json.loads(replay.body))
    try:
        result = await handlers.link_default_connection(current_session, session_registry)
        body = json.dumps(jsonable_encoder(result), separators=(",", ":"))
        await replay_store.complete(replay, 200, body)
        return result
    except Exception:
        await replay_store.abort(replay)
        raise


@router.get("/connection", response_model=BrokerageAccountConnection, dependencies=[Depends(require_access_level(AccessLevel.USER))])
async def get_connection(
    current_session: Annotated[SessionData, Depends(get_current_session)],
    session_registry: Annotated[AsyncSessionRegistry, Depends(get_session_registry)],
) -> BrokerageAccountConnection:
    return await handlers.get_connection(current_session, session_registry)
