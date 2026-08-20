import pytest

from kis_auto_trading.infrastructure.durable_jobs.contracts import (
    JOB_STATUS_EVENT_TYPE,
    JOB_STATUS_ROUTING_KEY,
    DurableJobStatus,
)
from kis_auto_trading.infrastructure.durable_jobs.repository import (
    DurableJobRepository,
)


class FakeResult:
    def scalar_one_or_none(self) -> str:
        return 'job-1'


class FakeSession:
    def __init__(self) -> None:
        self.statements: list[object] = []
        self.events: list[object] = []

    async def execute(self, statement: object) -> FakeResult:
        self.statements.append(statement)
        return FakeResult()

    def add(self, event: object) -> None:
        self.events.append(event)


@pytest.mark.anyio
async def test_transition_records_status_event_in_same_session() -> None:
    session = FakeSession()

    transitioned = await DurableJobRepository(session).transition(
        job_id='job-1',
        expected_status=DurableJobStatus.RUNNING,
        status=DurableJobStatus.SUCCEEDED,
        result={'articles': 2},
    )

    assert transitioned is True
    event = session.events[0]
    assert event.event_type == JOB_STATUS_EVENT_TYPE
    assert event.routing_key == JOB_STATUS_ROUTING_KEY
    assert event.aggregate_id == 'job-1'
    assert event.payload == {
        'job_id': 'job-1',
        'status': 'succeeded',
        'result': {'articles': 2},
        'error': None,
    }
