# Generated integration environment

This disposable profile starts PostgreSQL, three-node Redis Cluster, RabbitMQ, Airflow, Outbox relay, durable-job worker for integration checks.

```powershell
Copy-Item .env.example .env
docker compose --env-file .env -f compose.integration.yml up -d --wait
docker compose --env-file .env -f compose.integration.yml down
```

Run application containers on the Compose network. The Redis Cluster URL uses
Docker service DNS and is intentionally not a host-process URL. Airflow is
generated paused and reads the durable-job API token from .env. When the
application profile is enabled, the outbox relay and durable-job worker run
from the same local image.
When Docker is enabled, migrations run before the generated application starts.
