import os
from collections.abc import Sequence

import httpx

from kis_auto_trading.infrastructure.durable_jobs.models import DurableJobRecord
from kis_auto_trading.modules.search.hybrid import HybridSearchIndex, SearchBackend

JOB_HISTORY_INDEX = "operator-durable-jobs-v1"
_SUMMARY_LIMIT = 500


class DurableJobHistorySearchIndexer:
    """Indexes safe Durable Job execution summaries for operator search."""

    def __init__(
        self,
        *,
        ollama_url: str,
        embedding_model: str,
        elasticsearch_url: str | None = None,
        search_url: str | None = None,
        search_backend: SearchBackend | str = SearchBackend.ELASTICSEARCH,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if search_url is None:
            if elasticsearch_url is None:
                raise ValueError("search_url is required")
            search_url = elasticsearch_url
        self._index = HybridSearchIndex(
            index_name=JOB_HISTORY_INDEX,
            source_id_field="job_id",
            properties={
                "job_id": {"type": "keyword"},
                "job_type": {"type": "keyword"},
                "run_key": {"type": "keyword"},
                "status": {"type": "keyword"},
                "error_summary": {"type": "text"},
                "result_summary": {"type": "text"},
                "requested_at": {"type": "date"},
                "updated_at": {"type": "date"},
            },
            keyword_fields=[
                "job_type^3",
                "run_key^2",
                "status^2",
                "error_summary",
                "result_summary",
            ],
            ollama_url=ollama_url,
            embedding_model=embedding_model,
            search_url=search_url,
            search_backend=search_backend,
            transport=transport,
        )

    @classmethod
    def from_environment(cls) -> "DurableJobHistorySearchIndexer":
        search_url = os.getenv("RAG_SEARCH_URL") or os.environ["RAG_ELASTICSEARCH_URL"]
        return cls(
            ollama_url=os.environ["RAG_OLLAMA_URL"],
            embedding_model=os.environ["RAG_EMBEDDING_MODEL"],
            search_url=search_url,
            search_backend=os.getenv("RAG_SEARCH_BACKEND", SearchBackend.ELASTICSEARCH),
        )

    @classmethod
    def is_configured_from_environment(cls) -> bool:
        return bool(
            (os.getenv("RAG_SEARCH_URL") or os.getenv("RAG_ELASTICSEARCH_URL"))
            and os.getenv("RAG_OLLAMA_URL")
            and os.getenv("RAG_EMBEDDING_MODEL")
        )

    async def index(self, records: Sequence[DurableJobRecord]) -> int:
        return await self._index.index(
            [
                (source, self._content(source))
                for source in (self._source(record) for record in records)
            ]
        )

    async def search(self, query: str, *, limit: int = 10) -> list[dict[str, object]]:
        return await self._index.search(query, limit=limit)

    @staticmethod
    def _source(record: DurableJobRecord) -> dict[str, object]:
        return {
            "job_id": record.job_id,
            "job_type": record.job_type,
            "run_key": record.run_key,
            "status": record.status,
            "error_summary": _summary(record.error),
            "result_summary": _result_summary(record.result),
            "requested_at": record.requested_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }

    @staticmethod
    def _content(source: dict[str, object]) -> str:
        return "\n".join(
            value
            for value in (
                source["job_type"],
                source["run_key"],
                source["status"],
                source["error_summary"],
                source["result_summary"],
            )
            if isinstance(value, str) and value
        )


def _summary(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip()[:_SUMMARY_LIMIT] or None


def _result_summary(result: dict[str, object] | None) -> str | None:
    if not result:
        return None
    return _summary(
        ", ".join(sorted(str(key).strip() for key in result if str(key).strip()))
    )
