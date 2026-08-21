# Generated integration environment

This disposable profile starts PostgreSQL, Redis, RabbitMQ, Outbox relay, message worker, Airflow, durable-job worker for integration checks.

```powershell
Copy-Item .env.example .env
docker compose --env-file .env -f compose.integration.yml up -d --wait
docker compose --env-file .env -f compose.integration.yml down
```

Long-running services use `restart: unless-stopped`, so they recover after the Docker engine restarts. The host must start Docker automatically; AWS Launch Template UserData is a separate deployment concern and is not part of this disposable integration profile.

The generated application is built from Dockerfile. When Docker is enabled, migrations run before the generated application starts.
Airflow is generated paused and reads the durable-job API token from .env. Scheduled job payloads are JSON objects supplied by their generated `DURABLE_JOB_*_PAYLOAD_JSON` entries in `.env`. The durable-job worker runs from the same local image.
The outbox relay and scaffolded message worker run from the same local image. Customize the scaffolded worker handler for application event consumption.
