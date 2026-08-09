# Generated integration environment

This disposable profile starts PostgreSQL, three-node Redis Cluster, RabbitMQ for integration checks.

```powershell
Copy-Item .env.example .env
docker compose --env-file .env -f compose.integration.yml up -d --wait
docker compose --env-file .env -f compose.integration.yml down
```

Run application containers on the Compose network. The Redis Cluster URL uses
Docker service DNS and is intentionally not a host-process URL. Airflow, the
application container, and message workers are separate later contracts.
