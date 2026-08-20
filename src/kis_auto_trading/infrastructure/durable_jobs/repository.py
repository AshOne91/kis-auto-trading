from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from kis_auto_trading.infrastructure.messaging.protocol import EventMessage
from kis_auto_trading.infrastructure.outbox.repository import OutboxWriter

from .contracts import (
    JOB_DEFINITIONS,
    JOB_STATUS_EVENT_TYPE,
    JOB_STATUS_ROUTING_KEY,
    DurableJobStatus,
)
from .models import DurableJobRecord


@dataclass(frozen=True, slots=True)
class DurableJobRequestResult:
    job_id: str
    created: bool


class DurableJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def request(
        self,
        *,
        job_type: str,
        run_key: str,
        payload: dict[str, object],
        available_at: datetime | None = None,
    ) -> DurableJobRequestResult:
        definition = JOB_DEFINITIONS[job_type]
        now = datetime.now(UTC)
        job_id = str(uuid4())
        created_job_id = (
            await self._session.execute(
                insert(DurableJobRecord)
                .values(
                    job_id=job_id,
                    job_type=definition.name,
                    run_key=run_key,
                    status=DurableJobStatus.REQUESTED.value,
                    payload=payload,
                    requested_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(index_elements=['job_type', 'run_key'])
                .returning(DurableJobRecord.job_id)
            )
        ).scalar_one_or_none()
        if created_job_id is not None:
            OutboxWriter(self._session).add(
                EventMessage(
                    event_type=definition.event_type,
                    aggregate_id=created_job_id,
                    payload={
                        'job_id': created_job_id,
                        'job_type': definition.name,
                        'run_key': run_key,
                        'payload': payload,
                    },
                    routing_key=definition.routing_key,
                ),
                available_at=available_at,
            )
            return DurableJobRequestResult(job_id=created_job_id, created=True)

        existing = (
            await self._session.execute(
                select(DurableJobRecord.job_id).where(
                    DurableJobRecord.job_type == definition.name,
                    DurableJobRecord.run_key == run_key,
                )
            )
        ).scalar_one()
        return DurableJobRequestResult(job_id=existing, created=False)

    async def get(self, job_id: str) -> DurableJobRecord | None:
        return await self._session.get(
            DurableJobRecord, job_id, populate_existing=True
        )

    async def list_recent(
        self, *, job_type: str, limit: int
    ) -> list[DurableJobRecord]:
        records = await self._session.execute(
            select(DurableJobRecord)
            .where(DurableJobRecord.job_type == job_type)
            .order_by(
                DurableJobRecord.updated_at.desc(), DurableJobRecord.job_id.desc()
            )
            .limit(limit)
        )
        return list(records.scalars())

    async def transition(
        self,
        *,
        job_id: str,
        expected_status: DurableJobStatus,
        status: DurableJobStatus,
        result: dict[str, object] | None = None,
        error: str | None = None,
    ) -> bool:
        updated = await self._session.execute(
            update(DurableJobRecord)
            .where(
                DurableJobRecord.job_id == job_id,
                DurableJobRecord.status == expected_status.value,
            )
            .values(
                status=status.value,
                result=result,
                error=error,
                updated_at=datetime.now(UTC),
            )
            .returning(DurableJobRecord.job_id)
        )
        transitioned = updated.scalar_one_or_none() is not None
        if transitioned:
            OutboxWriter(self._session).add(
                EventMessage(
                    event_type=JOB_STATUS_EVENT_TYPE,
                    aggregate_id=job_id,
                    payload={
                        'job_id': job_id,
                        'status': status.value,
                        'result': result,
                        'error': error,
                    },
                    routing_key=JOB_STATUS_ROUTING_KEY,
                )
            )
        return transitioned
