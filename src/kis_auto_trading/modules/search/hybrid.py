import asyncio
import json
from collections.abc import Sequence
from enum import StrEnum

import httpx


class SearchBackend(StrEnum):
    ELASTICSEARCH = "elasticsearch"
    OPENSEARCH = "opensearch"


class HybridSearchIndex:
    """KIS-local hybrid keyword and vector index transport."""

    def __init__(
        self,
        *,
        index_name: str,
        source_id_field: str,
        properties: dict[str, object],
        keyword_fields: Sequence[str],
        ollama_url: str,
        embedding_model: str,
        search_url: str,
        search_backend: SearchBackend | str = SearchBackend.ELASTICSEARCH,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._index_name = index_name
        self._source_id_field = source_id_field
        self._properties = properties
        self._keyword_fields = tuple(keyword_fields)
        self._search_backend = SearchBackend(search_backend)
        self._search_url = search_url.rstrip("/")
        self._ollama_url = ollama_url.rstrip("/")
        self._embedding_model = embedding_model
        self._transport = transport

    async def index(self, documents: Sequence[tuple[dict[str, object], str]]) -> int:
        if not documents:
            return 0

        embeddings = await self._embed([content for _, content in documents])
        if len(embeddings) != len(documents):
            raise ValueError("embedding response does not match indexed documents")
        await self._ensure_index(dimensions=len(embeddings[0]))

        lines: list[str] = []
        for (source, _), embedding in zip(documents, embeddings, strict=True):
            document_id = str(source[self._source_id_field])
            lines.append(
                f'{{"index":{{"_index":"{self._index_name}","_id":"{document_id}"}}}}'
            )
            lines.append(
                json.dumps({**source, "embedding": embedding}, separators=(",", ":"))
            )
        async with self._client() as client:
            response = await client.post(
                f"{self._search_url}/_bulk",
                content="\n".join(lines) + "\n",
                headers={"content-type": "application/x-ndjson"},
            )
        response.raise_for_status()
        if response.json()["errors"]:
            raise RuntimeError("search backend rejected one or more documents")
        return len(documents)

    async def search(self, query: str, *, limit: int = 10) -> list[dict[str, object]]:
        embedding = (await self._embed([query]))[0]
        candidate_count = max(limit * 2, 20)
        async with self._client() as client:
            keyword_response, vector_response = await asyncio.gather(
                client.post(
                    f"{self._search_url}/{self._index_name}/_search",
                    json={
                        "size": candidate_count,
                        "query": {
                            "multi_match": {
                                "query": query,
                                "fields": list(self._keyword_fields),
                            }
                        },
                    },
                ),
                client.post(
                    f"{self._search_url}/{self._index_name}/_search",
                    json=self._vector_search_payload(embedding, candidate_count),
                ),
            )
        keyword_response.raise_for_status()
        vector_response.raise_for_status()

        sources: dict[str, dict[str, object]] = {}
        scores: dict[str, float] = {}
        for response in (keyword_response, vector_response):
            for rank, hit in enumerate(response.json()["hits"]["hits"], start=1):
                source = hit["_source"]
                source_id = str(source[self._source_id_field])
                sources[source_id] = source
                scores[source_id] = scores.get(source_id, 0.0) + 1.0 / (60 + rank)

        ranked_ids = sorted(
            scores, key=lambda source_id: (-scores[source_id], source_id)
        )
        return [sources[source_id] for source_id in ranked_ids[:limit]]

    async def _embed(self, inputs: Sequence[str]) -> list[list[float]]:
        async with self._client() as client:
            response = await client.post(
                f"{self._ollama_url}/api/embed",
                json={"model": self._embedding_model, "input": list(inputs)},
            )
        response.raise_for_status()
        embeddings = response.json()["embeddings"]
        if (
            not embeddings
            or not embeddings[0]
            or not all(isinstance(vector, list) for vector in embeddings)
        ):
            raise ValueError("Ollama returned no embeddings")
        return embeddings

    async def _ensure_index(self, *, dimensions: int) -> None:
        async with self._client() as client:
            exists = await client.head(f"{self._search_url}/{self._index_name}")
            if exists.status_code == 200:
                return
            if exists.status_code != 404:
                exists.raise_for_status()
            created = await client.put(
                f"{self._search_url}/{self._index_name}",
                json=self._index_mapping(dimensions),
            )
        if created.status_code not in {200, 201, 400}:
            created.raise_for_status()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, timeout=30.0)

    def _vector_search_payload(
        self, embedding: list[float], candidate_count: int
    ) -> dict[str, object]:
        if self._search_backend is SearchBackend.OPENSEARCH:
            return {
                "size": candidate_count,
                "query": {
                    "knn": {"embedding": {"vector": embedding, "k": candidate_count}}
                },
            }
        return {
            "size": candidate_count,
            "knn": {
                "field": "embedding",
                "query_vector": embedding,
                "k": candidate_count,
                "num_candidates": 100,
            },
        }

    def _index_mapping(self, dimensions: int) -> dict[str, object]:
        properties = dict(self._properties)
        if self._search_backend is SearchBackend.OPENSEARCH:
            properties["embedding"] = {
                "type": "knn_vector",
                "dimension": dimensions,
                "method": {
                    "name": "hnsw",
                    "engine": "faiss",
                    "space_type": "cosinesimil",
                },
            }
            return {
                "settings": {"index": {"knn": True}},
                "mappings": {"properties": properties},
            }
        properties["embedding"] = {
            "type": "dense_vector",
            "dims": dimensions,
            "similarity": "cosine",
        }
        return {"mappings": {"properties": properties}}
