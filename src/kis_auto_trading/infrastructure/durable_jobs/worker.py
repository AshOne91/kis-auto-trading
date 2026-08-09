from dataclasses import dataclass
from typing import Protocol

from kis_auto_trading.infrastructure.database.routing import ShardTarget
from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.messaging.protocol import EventMessage

from .contracts import JOB_DEFINITIONS, DurableJobStatus
from .repository import DurableJobRepository


@dataclass(frozen=True, slots=True)
class DurableJobExecution:
    job_id: str
    job_type: str
    run_key: str
    payload: dict[str, object]


class DurableJobHandler(Protocol):
    async def handle(
        self, execution: DurableJobExecution
    ) -> dict[str, object] | None: ...


class DurableJobMessageHandler:
    def __init__(
        self, session_registry: AsyncSessionRegistry, handler: DurableJobHandler
    ) -> None:
        self._session_registry = session_registry
        self._handler = handler

    async def handle(self, message: EventMessage) -> None:
        payload = message.payload
        job_id = str(payload['job_id'])
        job_type = str(payload['job_type'])
        run_key = str(payload['run_key'])
        job_payload = payload['payload']
        if not isinstance(job_payload, dict):
            raise TypeError('durable job payload must be an object')
        definition = JOB_DEFINITIONS.get(job_type)
        if definition is None or message.event_type != definition.event_type:
            raise ValueError('durable job message does not match a definition')

        async with self._session_registry.session(
            ShardTarget(store=definition.store)
        ) as session:
            repository = DurableJobRepository(session)
            claimed = await repository.transition(
                job_id=job_id,
                expected_status=DurableJobStatus.REQUESTED,
                status=DurableJobStatus.RUNNING,
            )
            if not claimed:
                return

        execution = DurableJobExecution(
            job_id=job_id,
            job_type=job_type,
            run_key=run_key,
            payload=job_payload,
        )
        try:
            result = await self._handler.handle(execution)
        except Exception as error:
            async with self._session_registry.session(
                ShardTarget(store=definition.store)
            ) as session:
                await DurableJobRepository(session).transition(
                    job_id=job_id,
                    expected_status=DurableJobStatus.RUNNING,
                    status=DurableJobStatus.FAILED,
                    error=str(error) or type(error).__name__,
                )
            raise

        async with self._session_registry.session(
            ShardTarget(store=definition.store)
        ) as session:
            completed = await DurableJobRepository(session).transition(
                job_id=job_id,
                expected_status=DurableJobStatus.RUNNING,
                status=DurableJobStatus.SUCCEEDED,
                result=result,
            )
        if not completed:
            raise RuntimeError('durable job completion transition was lost')
