import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from kis_auto_trading.infrastructure.access_control import (
    AccessLevel,
    require_access_level,
)
from kis_auto_trading.infrastructure.database.provider import get_session_registry
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.kis_domestic_account import (
    KisDomesticAccountClient,
    KisDomesticAccountError,
)
from kis_auto_trading.infrastructure.kis_token_coordinator import (
    KisTokenCoordinatorError,
)
from kis_auto_trading.infrastructure.service_tokens import require_service_token
from kis_auto_trading.infrastructure.session_store.protocol import SessionData
from kis_auto_trading.infrastructure.session_store.provider import get_current_session
from kis_auto_trading.modules.brokerage_account import handlers
from kis_auto_trading.modules.brokerage_account.generated.models import (
    BrokerageAccountConnection,
)
from kis_auto_trading.modules.portfolio import handlers as portfolio_handlers
from kis_auto_trading.modules.portfolio.generated.models import (
    PortfolioPositionSnapshot,
    PortfolioSnapshot,
)

logger = logging.getLogger(__name__)


class DomesticStockHoldingResponse(BaseModel):
    stock_code: str
    product_name: str
    holding_quantity: str
    orderable_quantity: str
    current_price: str


class PortfolioSnapshotResponse(BaseModel):
    snapshot: PortfolioSnapshot
    positions: list[PortfolioPositionSnapshot]


def get_kis_domestic_account(request: Request) -> KisDomesticAccountClient:
    try:
        return request.app.state.kis_domestic_account
    except AttributeError as error:
        raise HTTPException(
            status_code=503,
            detail="KIS domestic account is not configured",
        ) from error


router = APIRouter(
    prefix="/internal/operator/portfolio",
    tags=["operator-portfolio"],
    dependencies=[Depends(require_service_token("operator"))],
)

user_router = APIRouter(
    prefix="/api/brokerage-account",
    tags=["brokerage-account"],
    dependencies=[Depends(require_access_level(AccessLevel.USER))],
)
portfolio_router = APIRouter(
    prefix="/api/portfolio",
    tags=["portfolio"],
    dependencies=[Depends(require_access_level(AccessLevel.USER))],
)


async def get_active_kis_connection(
    current_session: Annotated[SessionData, Depends(get_current_session)],
    session_registry: Annotated[
        AsyncSessionRegistry, Depends(get_session_registry)
    ],
) -> BrokerageAccountConnection:
    connection = await handlers.get_connection(current_session, session_registry)
    if (
        connection.provider != "kis"
        or connection.credential_ref != "kis:default"
        or connection.status != "active"
    ):
        raise HTTPException(
            status_code=409,
            detail="Brokerage account connection is unavailable",
        )
    return connection


@router.get("/domestic-stock-holdings", response_model=list[DomesticStockHoldingResponse])
async def list_domestic_stock_holdings(
    account: Annotated[KisDomesticAccountClient, Depends(get_kis_domestic_account)],
) -> list[DomesticStockHoldingResponse]:
    try:
        holdings = await account.list_domestic_stock_holdings()
    except KisDomesticAccountError as error:
        logger.warning("operator KIS balance rejected: %s", type(error).__name__)
        raise HTTPException(
            status_code=502,
            detail="KIS domestic account is unavailable",
        ) from error
    except (KisTokenCoordinatorError, httpx.HTTPError) as error:
        logger.warning(
            "operator KIS balance transport failed: %s", type(error).__name__
        )
        raise HTTPException(
            status_code=503,
            detail="KIS domestic account is unavailable",
        ) from error
    return [
        DomesticStockHoldingResponse(
            stock_code=holding.stock_code,
            product_name=holding.product_name,
            holding_quantity=holding.holding_quantity,
            orderable_quantity=holding.orderable_quantity,
            current_price=holding.current_price,
        )
        for holding in holdings
    ]


@user_router.get(
    "/domestic-stock-holdings",
    response_model=list[DomesticStockHoldingResponse],
)
async def list_linked_domestic_stock_holdings(
    request: Request,
    _connection: Annotated[
        BrokerageAccountConnection, Depends(get_active_kis_connection)
    ],
) -> list[DomesticStockHoldingResponse]:
    return await list_domestic_stock_holdings(get_kis_domestic_account(request))


@portfolio_router.post(
    "/snapshots",
    response_model=PortfolioSnapshotResponse,
)
async def capture_linked_portfolio_snapshot(
    request: Request,
    current_session: Annotated[SessionData, Depends(get_current_session)],
    session_registry: Annotated[
        AsyncSessionRegistry, Depends(get_session_registry)
    ],
    connection: Annotated[
        BrokerageAccountConnection, Depends(get_active_kis_connection)
    ],
) -> PortfolioSnapshotResponse:
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key header is required",
        )
    if len(idempotency_key) > 128:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key header is too long",
        )
    try:
        capture = await portfolio_handlers.capture_portfolio_snapshot(
            current_session,
            session_registry,
            connection,
            get_kis_domestic_account(request),
            idempotency_key,
        )
    except KisDomesticAccountError as error:
        logger.warning("user KIS balance rejected: %s", type(error).__name__)
        raise HTTPException(
            status_code=502,
            detail="KIS domestic account is unavailable",
        ) from error
    except (KisTokenCoordinatorError, httpx.HTTPError) as error:
        logger.warning("user KIS balance transport failed: %s", type(error).__name__)
        raise HTTPException(
            status_code=503,
            detail="KIS domestic account is unavailable",
        ) from error
    return PortfolioSnapshotResponse(
        snapshot=capture.snapshot,
        positions=list(capture.positions),
    )
