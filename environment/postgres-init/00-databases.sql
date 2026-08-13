SELECT format('CREATE DATABASE %I', database_name)
FROM (VALUES ('identity'), ('automation'), ('account_shard_1'), ('account_shard_2'), ('airflow')) AS requested(database_name)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_database WHERE datname = requested.database_name
)
\gexec
