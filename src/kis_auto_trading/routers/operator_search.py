import logging
from datetime import datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from kis_auto_trading.modules.operations.durable_job_history_search import (
    DurableJobHistorySearchIndexer,
)
from kis_auto_trading.routers.durable_jobs import require_durable_job_api_token

logger = logging.getLogger(__name__)


class DurableJobHistorySearchResponse(BaseModel):
    job_id: str
    job_type: str
    run_key: str
    status: str
    error_summary: str | None
    result_summary: str | None
    requested_at: datetime
    updated_at: datetime


def get_durable_job_history_search_indexer() -> DurableJobHistorySearchIndexer:
    if not DurableJobHistorySearchIndexer.is_configured_from_environment():
        raise HTTPException(status_code=503, detail="operator search is not configured")
    return DurableJobHistorySearchIndexer.from_environment()


router = APIRouter(
    prefix="/internal/operator/search",
    tags=["operator-search"],
    dependencies=[Depends(require_durable_job_api_token)],
)


@router.get("/durable-jobs", response_model=list[DurableJobHistorySearchResponse])
async def search_durable_job_history(
    query: Annotated[str, Query(min_length=1, max_length=200)],
    indexer: Annotated[
        DurableJobHistorySearchIndexer, Depends(get_durable_job_history_search_indexer)
    ],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[dict[str, object]]:
    try:
        return await indexer.search(query, limit=limit)
    except httpx.HTTPError as error:
        logger.warning("operator durable job search is unavailable: %s", error)
        raise HTTPException(
            status_code=503, detail="operator search is unavailable"
        ) from error
