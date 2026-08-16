# Generated local object storage

This generated overlay provides an S3-compatible MinIO endpoint for
`kis_auto_trading`. It does not configure retention rules,
object schemas, or application upload code.

```powershell
Copy-Item deploy/storage/.env.example deploy/storage/.env
docker compose --env-file deploy/storage/.env -f deploy/storage/compose.storage.yaml --profile storage up -d
docker compose --env-file deploy/storage/.env -f deploy/storage/compose.storage.yaml --profile storage down
```

The S3-compatible in-network endpoint is `S3_ENDPOINT_URL`. `minio-init`
idempotently creates `S3_BUCKET` after MinIO becomes healthy. MinIO data uses a
named Docker volume and the API/console bind to `LOCAL_BIND_ADDRESS` only.
`minio-init` exits successfully after initialization, so start this overlay with
`up -d` rather than adding it to a Compose `--wait` health gate.
Replace the sample root credentials before starting the profile. Production
requires separate credentials, encrypted backups, bucket policies, lifecycle
rules, and a cluster-aware object-storage deployment; do not use this Compose
file as a production topology.
