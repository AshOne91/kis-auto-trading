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
Create or rotate it outside Git, for example:

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
specification requests one. Replace it with a PVC/PV or centralized logging
before production deployment.
