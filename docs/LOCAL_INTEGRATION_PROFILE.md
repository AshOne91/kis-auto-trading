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

## Ownership

- `autoforge.yaml` selects the services and is KIS-owned input.
- AutoForge owns generated infrastructure, migrations, Job API, and DAG source.
- KIS owns the News/RAG handler, source selection, payload policy, and secrets.
- The future Environment Generator must preserve KIS override files and local
  secret files.
