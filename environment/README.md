# Generated integration environment

This disposable profile starts PostgreSQL, three-node Redis Cluster, RabbitMQ, Airflow, Outbox relay, durable-job worker for integration checks.

```powershell
Copy-Item .env.example .env
docker compose --env-file .env -f compose.integration.yml up -d --wait
docker compose --env-file .env -f compose.integration.yml down
```

Long-running services use `restart: unless-stopped`, so they recover after the Docker engine restarts. The host must start Docker automatically; AWS Launch Template UserData is a separate deployment concern and is not part of this disposable integration profile.

Run application containers on the Compose network. The Redis Cluster URL uses
Docker service DNS and is intentionally not a host-process URL.
The generated application is built from Dockerfile. When Docker is enabled, migrations run before the generated application starts.
Airflow is generated paused and reads the durable-job API token from .env. The outbox relay and durable-job worker run from the same local image.
