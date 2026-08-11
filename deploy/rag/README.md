# Generated local RAG infrastructure

This optional overlay provides a local vector store (Qdrant), keyword search
(Opensearch), and local inference runtime (Ollama) for
`kis_auto_trading`. It does not create collections, indexes,
documents, embeddings, prompts, or models.

Create the shared network once before starting either the RAG overlay or the
generated local environment. It lets separately managed Compose projects use
service DNS without exposing internal container ports through the host.

```powershell
if (-not (docker network inspect kis_auto_trading-rag 2>$null)) {
  docker network create kis_auto_trading-rag
}
```

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

Qdrant and Opensearch use named Docker volumes because they own persistent
data. Ports bind to `LOCAL_BIND_ADDRESS` and default to the configured local
port block. Search-engine security is disabled only for this local overlay.
Production requires authenticated, backed-up, cluster-aware service deployment;
do not use this Compose file as a production topology.
