from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError

from kis_auto_trading.infrastructure.session_store.protocol import SessionStoreError

router = APIRouter(tags=["health"])
_REQUIRED_DEPENDENCIES = ('session_registry', 'session_store')


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readiness")
async def readiness(request: Request) -> dict[str, str]:
    for state_name in _REQUIRED_DEPENDENCIES:
        dependency = getattr(request.app.state, state_name, None)
        health_check = getattr(dependency, 'health_check', None)
        if health_check is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f'{state_name} is not initialized',
            )
        try:
            await health_check()
        except (SQLAlchemyError, SessionStoreError):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f'{state_name} is not ready',
            ) from None
    return {"status": "ready"}
