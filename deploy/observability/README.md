# Generated ELK development profile

This profile runs a local Elasticsearch, Kibana and Filebeat stack. It collects JSON-lines application logs for `kis_auto_trading`:

- Filebeat reads `LOG_ROOT/*.log` and `LOG_ROOT/*/*.log` as NDJSON.
- Filebeat preserves its read registry in the `filebeat-data` volume.
- Elasticsearch stores indexed logs in the `elasticsearch-data` volume.
- Kibana is available at `http://127.0.0.1:$KIBANA_PORT` (default `5601`).

Start it together with the application's integration Compose file:

```powershell
docker compose -f <base-compose-file> -f deploy/observability/compose.elk.yaml up -d
```

Set `LOG_ROOT` when logs are stored outside `./logs`. Set `ELASTICSEARCH_PORT`,
`KIBANA_PORT`, or `FILEBEAT_CONFIG` when the defaults conflict with the host.

This is a local development profile. The central mode disables security and
binds its ports to localhost. Production requires authenticated
Elasticsearch/Kibana and a cluster-aware collector such as a Filebeat or Fluent
Bit DaemonSet; do not use this overlay as a production deployment.
