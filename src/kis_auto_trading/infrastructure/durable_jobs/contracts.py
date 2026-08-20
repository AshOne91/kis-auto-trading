from dataclasses import dataclass
from enum import StrEnum

JOB_STATUS_EVENT_TYPE = 'durable-job.status.changed'
JOB_STATUS_ROUTING_KEY = 'durable-job.status.changed'


class DurableJobStatus(StrEnum):
    REQUESTED = 'requested'
    RUNNING = 'running'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


@dataclass(frozen=True, slots=True)
class DurableJobDefinition:
    name: str
    store: str
    event_type: str
    routing_key: str


JOB_DEFINITIONS: dict[str, DurableJobDefinition] = {
    "news_collection": DurableJobDefinition(
        name="news_collection",
        store="automation",
        event_type="news.collection.requested",
        routing_key="news.collection.requested",
    ),
    "news_index": DurableJobDefinition(
        name="news_index",
        store="automation",
        event_type="news.index.requested",
        routing_key="news.index.requested",
    ),
    "durable_job_history_index": DurableJobDefinition(
        name="durable_job_history_index",
        store="automation",
        event_type="durable-job.history.index.requested",
        routing_key="durable-job.history.index.requested",
    ),
    "market_price_snapshot": DurableJobDefinition(
        name="market_price_snapshot",
        store="automation",
        event_type="market-price.snapshot.requested",
        routing_key="market-price.snapshot.requested",
    )
}
