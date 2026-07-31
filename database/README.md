# Database bootstrap and migrations

AutoForge specifications are the source of truth. The SQL files in this directory
are generated, version-controlled migration artifacts that allow another local
environment to reproduce the database structure without copying live data.

## Placement

- `global/`: apply once to the Global database. Login and shard-routing metadata
  belong here.
- `sharded/`: apply the same ordered files to every shard database. Personal
  profile data belongs here.

## Local setup order

1. Create one Global PostgreSQL database.
2. Create one or more Shard PostgreSQL databases.
3. Apply `global/*.sql` in filename order once to the Global database.
4. Apply `sharded/*.sql` in filename order to every Shard database.
5. Configure DSNs through environment variables or a secret manager.

SQL files must never contain passwords, DSNs, access tokens, or production data.
Application startup must not run migrations because horizontally scaled instances
could race. A dedicated setup or CI/CD migration job owns schema application.
