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
from kis_auto_trading.modules.signal import handlers
from kis_auto_trading.modules.signal.generated.models import SignalSubscription
from kis_auto_trading.modules.signal.generated.schemas import (
    SubscribeRequest,
    UnsubscribeRequest,
)

router = APIRouter(prefix="/api/signal", tags=["Trading Signal"])


@router.put("/subscription", response_model=SignalSubscription, dependencies=[Depends(require_access_level(AccessLevel.USER))])
async def subscribe(
    http_request: Request,
    request: SubscribeRequest,
    current_session: Annotated[SessionData, Depends(get_current_session)],
    session_registry: Annotated[AsyncSessionRegistry, Depends(get_session_registry)],
    replay_store: Annotated[RequestReplayStore, Depends(get_request_replay_store)],
) -> SignalSubscription:
    idempotency_key = http_request.headers.get("Idempotency-Key")
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    fingerprint_source = "PUT:/subscription:" + request.model_dump_json()
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
        result = await handlers.subscribe(request, current_session, session_registry)
        body = json.dumps(jsonable_encoder(result), separators=(",", ":"))
        await replay_store.complete(replay, 200, body)
        return result
    except Exception:
        await replay_store.abort(replay)
        raise


@router.delete("/subscription", response_model=SignalSubscription, dependencies=[Depends(require_access_level(AccessLevel.USER))])
async def unsubscribe(
    http_request: Request,
    request: UnsubscribeRequest,
    current_session: Annotated[SessionData, Depends(get_current_session)],
    session_registry: Annotated[AsyncSessionRegistry, Depends(get_session_registry)],
    replay_store: Annotated[RequestReplayStore, Depends(get_request_replay_store)],
) -> SignalSubscription:
    idempotency_key = http_request.headers.get("Idempotency-Key")
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    fingerprint_source = "DELETE:/subscription:" + request.model_dump_json()
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
        result = await handlers.unsubscribe(request, current_session, session_registry)
        body = json.dumps(jsonable_encoder(result), separators=(",", ":"))
        await replay_store.complete(replay, 200, body)
        return result
    except Exception:
        await replay_store.abort(replay)
        raise
