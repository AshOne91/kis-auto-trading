import os
from datetime import datetime
from secrets import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from kis_auto_trading.infrastructure.database.provider import get_session_registry
from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.durable_jobs.contracts import (
    JOB_DEFINITIONS,
    DurableJobStatus,
)
from kis_auto_trading.infrastructure.durable_jobs.repository import DurableJobRepository


class DurableJobTriggerRequest(BaseModel):
    run_key: str = Field(min_length=1)
    payload: dict[str, object] = Field(default_factory=dict)


class DurableJobTriggerResponse(BaseModel):
    job_id: str
    created: bool


class DurableJobStatusResponse(BaseModel):
    job_id: str
    job_type: str
    run_key: str
    status: str
    payload: dict[str, object]
    result: dict[str, object] | None
    error: str | None
    requested_at: datetime
    updated_at: datetime


def require_durable_job_api_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    expected_token = os.getenv('DURABLE_JOB_API_TOKEN')
    if not expected_token:
        raise HTTPException(status_code=503, detail='durable job API token is not configured')
    scheme, _, token = (authorization or '').partition(' ')
    if scheme != 'Bearer' or not compare_digest(token, expected_token):
        raise HTTPException(status_code=401, detail='invalid durable job API token')


router = APIRouter(
    prefix='/internal/jobs',
    tags=['durable-jobs'],
    dependencies=[Depends(require_durable_job_api_token)],
)


def _definition(job_type: str):
    definition = JOB_DEFINITIONS.get(job_type)
    if definition is None:
        raise HTTPException(status_code=404, detail='durable job type not found')
    return definition


def _status_response(job) -> DurableJobStatusResponse:
    return DurableJobStatusResponse(
        job_id=job.job_id,
        job_type=job.job_type,
        run_key=job.run_key,
        status=job.status,
        payload=job.payload,
        result=job.result,
        error=job.error,
        requested_at=job.requested_at,
        updated_at=job.updated_at,
    )


@router.post(
    '/{job_type}',
    response_model=DurableJobTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_durable_job(
    job_type: str,
    request: DurableJobTriggerRequest,
    session_registry: Annotated[
        AsyncSessionRegistry, Depends(get_session_registry)
    ],
) -> DurableJobTriggerResponse:
    definition = _definition(job_type)
    async with session_registry.session(ShardTarget(store=definition.store)) as session:
        result = await DurableJobRepository(session).request(
            job_type=job_type, run_key=request.run_key, payload=request.payload
        )
    return DurableJobTriggerResponse(
        job_id=result.job_id, created=result.created
    )


@router.get('/{job_type}', response_model=list[DurableJobStatusResponse])
async def list_durable_jobs(
    job_type: str,
    session_registry: Annotated[
        AsyncSessionRegistry, Depends(get_session_registry)
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[DurableJobStatusResponse]:
    definition = _definition(job_type)
    async with session_registry.session(ShardTarget(store=definition.store)) as session:
        jobs = await DurableJobRepository(session).list_recent(
            job_type=definition.name, limit=limit
        )
    return [_status_response(job) for job in jobs]


@router.get('/{job_type}/{job_id}', response_model=DurableJobStatusResponse)
async def get_durable_job(
    job_type: str,
    job_id: str,
    session_registry: Annotated[
        AsyncSessionRegistry, Depends(get_session_registry)
    ],
) -> DurableJobStatusResponse:
    definition = _definition(job_type)
    async with session_registry.session(ShardTarget(store=definition.store)) as session:
        job = await DurableJobRepository(session).get(job_id)
    if job is None or job.job_type != definition.name:
        raise HTTPException(status_code=404, detail='durable job not found')
    return _status_response(job)


@router.delete('/{job_type}/{job_id}', response_model=DurableJobStatusResponse)
async def cancel_durable_job(
    job_type: str,
    job_id: str,
    session_registry: Annotated[
        AsyncSessionRegistry, Depends(get_session_registry)
    ],
) -> DurableJobStatusResponse:
    definition = _definition(job_type)
    async with session_registry.session(ShardTarget(store=definition.store)) as session:
        repository = DurableJobRepository(session)
        job = await repository.get(job_id)
        if job is None or job.job_type != definition.name:
            raise HTTPException(status_code=404, detail='durable job not found')
        if job.status == DurableJobStatus.CANCELLED.value:
            return _status_response(job)
        cancelled = await repository.transition(
            job_id=job_id, expected_status=DurableJobStatus.REQUESTED,
            status=DurableJobStatus.CANCELLED,
        )
        if not cancelled:
            job = await repository.get(job_id)
            if job is not None and job.status == DurableJobStatus.CANCELLED.value:
                return _status_response(job)
            raise HTTPException(status_code=409, detail='durable job is already running or finished')
        job = await repository.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail='durable job not found')
        return _status_response(job)
