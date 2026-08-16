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

Before `up`, a checkout with AutoForge available can perform the read-only
override check:

```powershell
python -m autoforge.main validate-ports `
  --env-file environment/.env `
  --env-file deploy/rag/.env.example
```

Pass every environment file that publishes host ports. The check rejects
duplicates but does not allocate ports or replace specification validation.

A Windows Task Scheduler adapter is generated at `deploy/single-host/windows/start-compose.ps1`; register it to run after Docker Desktop starts. The bootstrap performs a read-only Compose port-collision preflight before starting containers.
The public proxy listens on `PUBLIC_BIND_ADDRESS:PUBLIC_HTTP_PORT`; application,
database, Redis, RabbitMQ, and Airflow host ports remain governed by the integration
environment. `LOG_ROOT` is a host bind mount so file logs survive application
container recreation. Keep `environment/.env` outside Git. Configure host firewall,
TLS termination, off-host backup, and Docker service auto-start before exposing the
host to an untrusted network.

## Generated host-port block

This consumer uses the AutoForge-generated local block beginning at `49400`:

| Service | Host port |
| --- | ---: |
| public application proxy | `49400` |
| PostgreSQL/HAProxy | `49410` |
| RabbitMQ AMQP | `49430` |
| RabbitMQ management | `49431` |
| Airflow | `49440` |

The application, database, broker, and scheduler communicate through Compose
service names and container ports. Do not assign another generated environment
the same block. The authoritative allocation rules live in [AutoForge's local
Docker port policy](https://github.com/AshOne91/AutoForge/blob/main/docs/architecture/local_port_policy.md).
Individual environment variables are one-off deployment overrides; changing them
does not make `ProjectSpec` revalidate a runtime collision.
