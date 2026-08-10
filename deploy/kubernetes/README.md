# kis-auto-trading Kubernetes base_server

This directory is generated from `autoforge.yaml`. It creates the Proxy/App
topology only; it never contains Secret values and does not apply itself to a
cluster.

## Required runtime contract

- application image: `kis-auto-trading:latest`
- namespace: `default`
- Kubernetes Secret: `my-kis-gold-bar`
- external entry point: LoadBalancer service on port `8080`

The Secret must provide these keys before the Deployment starts:

- `ACCOUNT_SHARD_1_DATABASE_URL`
- `ACCOUNT_SHARD_2_DATABASE_URL`
- `AUTOMATION_DATABASE_URL`
- `IDENTITY_DATABASE_URL`
- `RABBITMQ_URL`
- `REDIS_CLUSTER_URL`
Start from the generated zero-value template, fill it locally,
and keep the completed file out of Git:

```powershell
Copy-Item secret.env.example kis_secret.env
```

Create or rotate the Secret only after filling the values:

```powershell
kubectl create secret generic my-kis-gold-bar --namespace default --from-env-file=kis_secret.env
```

Apply and verify only after the image and Secret are ready:

```powershell
kubectl apply --namespace default -f base-server.yaml
kubectl rollout status --namespace default deployment/kis-auto-trading
kubectl rollout status --namespace default deployment/kis-auto-trading-nginx
```

`base-server.yaml` uses a local hostPath for `/app/logs` only when the
specification requests one. It is suitable only for single-node local
development (such as Docker Desktop): a hostPath is node-local and cannot
preserve one replica's files when another node runs it. Production deployments
must centralize stdout through a log collector. If a file-retention policy is
also required, use a PVC/PV with an access mode appropriate for the replicas.

## Filebeat node collector

`observability-filebeat.yaml` creates one Filebeat DaemonSet Pod per eligible
node. It reads only the generated application log hostPath and persists its
registry at `kis-auto-trading`'s `.filebeat-data` directory on that node.

The same Secret must also provide `ELASTICSEARCH_HOST` and
`ELASTICSEARCH_API_KEY`. Use a TLS Elasticsearch endpoint and an API key scoped
only to event publishing. The manifest does not grant Kubernetes API access,
does not create Elasticsearch/Kibana, and does not use privileged mode.

```powershell
kubectl apply --namespace default -f observability-filebeat.yaml
kubectl rollout status --namespace default daemonset/kis-auto-trading-filebeat
```

Clusters that prohibit hostPath mounts require an approved node-log collector
policy before this manifest can run.
