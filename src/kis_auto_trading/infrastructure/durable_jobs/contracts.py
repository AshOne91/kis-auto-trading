from dataclasses import dataclass
from enum import StrEnum


class DurableJobStatus(StrEnum):
    REQUESTED = 'requested'
    RUNNING = 'running'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'


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
    )
}
