# KIS Local Integration Profile

## Purpose

This document defines the first real runtime environment for the AutoForge
generated KIS contracts. It is a validation target, not a production topology.

## Selected KIS contracts

| Concern | Selected contract | Local realization required |
| --- | --- | --- |
| Identity data | Global `identity` PostgreSQL database | one logical PostgreSQL database |
| Job coordination | Global `automation` PostgreSQL database | one logical PostgreSQL database |
| Account data | `account` shards `1` and `2` | two logical PostgreSQL databases |
| Session store | Redis Cluster | a real Redis Cluster, not standalone Redis |
| Event delivery | RabbitMQ Outbox | RabbitMQ with the declared exchange, queue, and DLQ |
| Scheduled workflow | Airflow DAG source | generated trigger/status API, Job handler, and worker binding |

The PostgreSQL logical databases may share one local PostgreSQL container. They
must remain separate database names and URLs because the generated routing
contract must be exercised without collapsing Global and Shard placement.

## Required environment variables

```text
IDENTITY_DATABASE_URL
AUTOMATION_DATABASE_URL
ACCOUNT_SHARD_1_DATABASE_URL
ACCOUNT_SHARD_2_DATABASE_URL
REDIS_CLUSTER_URL
RABBITMQ_URL
DURABLE_JOB_API_TOKEN
```

Values belong in an ignored local `.env` file. The future generated
`.env.example` may show variable names and non-secret defaults only.

## Validation sequence

1. Start PostgreSQL, the Redis Cluster, and RabbitMQ.
2. Verify every declared endpoint is reachable with its generated URL.
3. Apply identity, automation, and account migrations independently.
4. Start the FastAPI application and verify the health endpoint.
5. Verify Redis SessionStore behavior against the real Cluster.
6. Create a Durable Job and verify its JobRecord and OutboxEvent are committed
   together in `automation`.
7. Run the Outbox relay and verify RabbitMQ delivery and DLQ behavior.
8. Verify the KIS-owned Job handler and explicit consumer binding.
9. Cancel a requested Durable Job and verify that a delivered message does not
   invoke the handler; running or completed Jobs must reject cancellation.
10. Start Airflow and validate DAG trigger, retry, timeout, and status polling.

## Deliberate exclusions

- no standalone Redis fallback: it would not validate `mode: cluster`
- no production Airflow cluster, cloud scheduler, or production credentials
- no production Redis Cluster, PostgreSQL replication, RabbitMQ HA, Kubernetes,
  AWS, passwords, or cloud credentials

## Single-host operations and backup drill

The selected local block begins at `49400`: the public proxy uses `49400`,
PostgreSQL/HAProxy `49410`, RabbitMQ `49430`/`49431`, and Airflow `49440`.
Before starting Compose with overrides, run the read-only port check against
every active environment file:

```powershell
python -m autoforge.main validate-ports `
  --env-file environment/.env `
  --env-file deploy/single-host/runtime.env
```

The generated single-host README is AutoForge-owned. This document owns the
KIS-specific backup drill and must not be written into that generated file.

Create recoverable artifacts outside the project directory before changing or
removing any volume:

```powershell
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = "C:\kis-auto-trading-backups\$stamp"
New-Item -ItemType Directory -Path $backup -Force | Out-Null
robocopy C:\kis-auto-trading\logs "$backup\logs" /E /R:1 /W:1
$container = (docker compose --env-file environment\.env `
  -f environment\compose.integration.yml ps -q postgres-ha-0).Trim()
foreach ($db in 'identity', 'account_shard_1', 'account_shard_2') {
  docker compose --env-file environment\.env `
    -f environment\compose.integration.yml `
    exec -T postgres-ha-0 sh -lc "pg_dump -U autoforge -d $db -Fc -f /tmp/$db.dump"
  docker cp "${container}:/tmp/$db.dump" "$backup\$db.dump"
  docker compose --env-file environment\.env `
    -f environment\compose.integration.yml `
    exec -T postgres-ha-0 rm -f "/tmp/$db.dump"
}
```

Restore only into a disposable source-compatible Spilo target first. Use
`pg_restore --clean --if-exists --no-owner --no-privileges`; never overwrite a
live database during a drill. After producing an artifact, use `autoforge
backup` with the generated `S3_*` settings to upload and checksum-verify it.

## Ownership

- `autoforge.yaml` selects the services and is KIS-owned input.
- AutoForge owns generated infrastructure, migrations, Job API, and DAG source.
- KIS owns the News/RAG handler, source selection, payload policy, and secrets.
- The future Environment Generator must preserve KIS override files and local
  secret files.
