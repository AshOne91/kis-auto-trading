# kis-auto-trading Kubernetes base_server

This directory is generated from `autoforge.yaml`. It creates
the Proxy/App topology only; it never contains Secret values and does not apply
itself to a cluster.

## Required runtime contract

- application image: `kis-auto-trading:latest`
- namespace: `default`
- Kubernetes Secret: `my-kis-gold-bar`
- external entry point: LoadBalancer service on port `8080`

The Secret must provide these keys before the Deployment starts:

- `ACCOUNT_SHARD_1_DATABASE_URL`
- `ACCOUNT_SHARD_2_DATABASE_URL`
- `AUTOMATION_DATABASE_URL`
- `DURABLE_JOB_API_TOKEN`
- `IDENTITY_DATABASE_URL`
- `RABBITMQ_URL`
- `REDIS_URL`
Start from the generated zero-value template, fill it locally,
and keep the completed file out of Git:

Database topology is provider-owned. Database URL keys are bound from this
Secret.


This profile does not create database clusters, Routers, or StatefulSets.

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
