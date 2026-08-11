# Generated local RAG infrastructure

This optional overlay provides a local vector store (Qdrant), keyword search
(Elasticsearch), and local inference runtime (Ollama) for
`kis_auto_trading`. It does not create collections, indexes,
documents, embeddings, prompts, or models.

```powershell
Copy-Item deploy/rag/.env.example deploy/rag/.env
docker compose --env-file deploy/rag/.env -f deploy/rag/compose.rag.yaml --profile rag up -d
docker compose --env-file deploy/rag/.env -f deploy/rag/compose.rag.yaml --profile rag down
```

Start Ollama only when local inference is needed. The image and every model use
substantial disk space, so no model is downloaded automatically.

```powershell
docker compose --env-file deploy/rag/.env -f deploy/rag/compose.rag.yaml --profile inference up -d
docker compose --env-file deploy/rag/.env -f deploy/rag/compose.rag.yaml exec ollama ollama pull <selected-model>
```

Qdrant and Elasticsearch use named Docker volumes because they own persistent
data. Ports bind to `LOCAL_BIND_ADDRESS` and default to the configured local
port block. `xpack.security.enabled` is disabled only for this local overlay.
Production requires authenticated, backed-up, cluster-aware service deployment;
do not use this Compose file as a production topology.
