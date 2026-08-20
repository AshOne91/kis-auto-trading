import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from kis_auto_trading.infrastructure.kis_domestic_account import (
    KisDomesticAccountClient,
    KisDomesticAccountError,
)
from kis_auto_trading.infrastructure.kis_token_coordinator import (
    KisTokenCoordinatorError,
)
from kis_auto_trading.infrastructure.service_tokens import require_service_token

logger = logging.getLogger(__name__)


class DomesticStockHoldingResponse(BaseModel):
    stock_code: str
    product_name: str
    holding_quantity: str
    orderable_quantity: str
    current_price: str


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
