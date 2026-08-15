# Generated single-host operating overlay

This generated overlay keeps `environment/compose.integration.yml` as the
dependency runtime and adds one public Nginx entry point with
`application` scaled to 3 replicas. It is service-level HA on
one Docker host: it recovers containers, not loss of the physical machine.

```powershell
Copy-Item environment/.env.example environment/.env
Copy-Item deploy/single-host/runtime.env.example deploy/single-host/runtime.env
# Replace every sample credential in environment/.env before starting.
docker compose --env-file environment/.env --env-file deploy/single-host/runtime.env -f environment/compose.integration.yml -f deploy/single-host/compose.override.yml up -d --wait
docker compose --env-file environment/.env --env-file deploy/single-host/runtime.env -f environment/compose.integration.yml -f deploy/single-host/compose.override.yml down
```

A Windows Task Scheduler adapter is generated at `deploy/single-host/windows/start-compose.ps1`; register it to run after Docker Desktop starts.
The public proxy listens on `PUBLIC_BIND_ADDRESS:PUBLIC_HTTP_PORT`; application,
database, Redis, RabbitMQ, and Airflow host ports remain governed by the integration
environment. `LOG_ROOT` is a host bind mount so file logs survive application
container recreation. Keep `environment/.env` outside Git. Configure host firewall,
TLS termination, off-host backup, and Docker service auto-start before exposing the
host to an untrusted network.
