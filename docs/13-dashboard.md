# 13 — Dashboard stack

Status: manifests, scripts, and local validation implemented on 2026-10-26. Cluster deployment and
recovery drills are pending the GHCR package visibility decision and the Git/Flux reconciliation.

## What runs

The `dashboard` namespace contains nine Deployments, nine Services, two PVCs, one Tailscale Ingress,
two generated ConfigMaps, and one manual Secret.

```text
Browser ──HTTPS──▶ Tailscale Ingress ──▶ dashboard Service :80 (nginx)
                                         │
                                         ├─ /api/bus/ ────▶ bus-catcher-rest :3000
                                         ├─ /api/tasks/ ──▶ procrastinator-tracker-rest :3000
                                         ├─ /api/fly/ ────▶ fly-over-tracker-rest :3000
                                         └─ /api/weather/ ▶ weather-psychic-rest :3000

home-sweet-home-agent ──▶ bus-catcher-mcp :3001/mcp
                       ├─▶ fly-over-tracker-mcp :3001/mcp
                       ├─▶ procrastinator-tracker-mcp :3001/mcp
                       └─▶ weather-psychic-mcp :3001/mcp
```

Only the dashboard is externally reachable. REST and MCP Services are `ClusterIP`; the browser uses
the dashboard's same-origin proxy, and MCP consumers run inside the cluster. There is no direct REST
or MCP ingress, CORS configuration, or authentication in v1.

| Object | Purpose |
| ------ | ------- |
| `apps/dashboard/frontend.yaml` | nginx SPA, same-origin proxy, config validator init container |
| `apps/dashboard/bus-catcher-rest.yaml` | Bus REST API and Service |
| `apps/dashboard/bus-catcher-mcp.yaml` | Bus MCP server and Service |
| `apps/dashboard/fly-over-tracker-rest.yaml` | Flight REST API and Service |
| `apps/dashboard/fly-over-tracker-mcp.yaml` | Flight MCP server and Service |
| `apps/dashboard/procrastinator-tracker-rest.yaml` | Tasks REST API and Service |
| `apps/dashboard/procrastinator-tracker-mcp.yaml` | Tasks MCP server and Service |
| `apps/dashboard/weather-psychic-rest.yaml` | Weather REST API and Service |
| `apps/dashboard/weather-psychic-mcp.yaml` | Weather MCP server and Service |
| `apps/dashboard/pvc.yaml` | `bus-catcher-data` and `procrastinator-data` |
| `apps/dashboard/nginx.conf` | Kubernetes-compatible proxy configuration |
| `apps/dashboard/validate-config.py` | Runtime JSON validator |
| `apps/dashboard/tailscale-ingress.yaml` | `dashboard.<tailnet>.ts.net` |
| `apps/dashboard/config.example.json` | Placeholder-only example, never mounted |

## Image pins

| Component | Pin |
| --------- | --- |
| Dashboard frontend | `ghcr.io/sousa99/home-sweet-home-dashboard:0.1.0` |
| Bus backend | `ghcr.io/sousa99/bus-catcher-backend:0.2.0` |
| Fly-over backend | `ghcr.io/sousa99/fly-over-tracker-backend:0.5.0` |
| Procrastinator backend | `ghcr.io/sousa99/procrastinator-tracker-backend:0.2.0` |
| Weather backend | `ghcr.io/sousa99/weather-psychic-backend:0.1.0` |
| Config validator | `python:3.12-alpine@sha256:b658b05ce9c4eb97ec6fc19424818a1f31993659c2b505a532f470e83807815d` |
| MCP host rewrite | `nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10` |

The module backend images are publicly pullable. The dashboard image was **not** anonymously
pullable during implementation. Resolve this before expecting the frontend pod to start.

### Make the dashboard package public (supported)

GitHub → the `home-sweet-home-dashboard` package settings → change visibility to public. This matches
the other GHCR images and avoids a long-lived token. Verify from the Mac:

```bash
docker manifest inspect ghcr.io/sousa99/home-sweet-home-dashboard:0.1.0 >/dev/null && echo public
```

### Use a pull Secret (fallback)

Create a `read:packages` token and a `ghcr-pull` Secret, then add the Secret reference to
`apps/dashboard/frontend.yaml` in Git:

```yaml
spec:
  template:
    spec:
      imagePullSecrets:
        - name: ghcr-pull
```

```bash
kubectl -n dashboard create secret docker-registry ghcr-pull \
  --docker-server=ghcr.io \
  --docker-username=<github-user> \
  --docker-password=<read-packages-token>
```

Never commit the token or the Secret manifest. If the package is public, do not add the
`imagePullSecrets` reference.

## Prerequisites

- Flux reconciles this repository and the `apps` Kustomization is `Ready`.
- The Tailscale Kubernetes Operator and `operator-oauth` Secret work; Home Assistant already proves
  the HTTPS ingress path.
- The dashboard GHCR package is public, or `ghcr-pull` exists and the frontend Deployment references
  it.
- A real dashboard JSON file exists outside Git, based on
  [`apps/dashboard/config.example.json`](../apps/dashboard/config.example.json).

## Create the household configuration Secret

The dashboard's `loadConfig()` silently merges over built-in defaults on any error. The frontend
therefore refuses to start until `dashboard-config` exists and passes validation.

```bash
cp apps/dashboard/config.example.json ~/dashboard-config.json
$EDITOR ~/dashboard-config.json
python3 apps/dashboard/validate-config.py ~/dashboard-config.json
./scripts/create-dashboard-config-secret.sh ~/dashboard-config.json
```

The script creates the `dashboard` namespace if Flux has not yet, validates the file, and creates or
updates the Secret without printing its contents. The real coordinates, stop IDs, and bus lines stay
outside Git.

If the frontend pod was already waiting on the Secret:

```bash
kubectl -n dashboard get secret dashboard-config
kubectl -n dashboard delete pod -l app.kubernetes.io/name=dashboard --ignore-not-found
```

## Deploy and verify

```bash
./scripts/validate.sh
flux reconcile source git flux-system
flux reconcile kustomization apps --with-source
kubectl -n dashboard get deploy,pods,svc,ingress,pvc
```

Expected:

- Nine Deployments Ready: `dashboard`, four `-rest`, four `-mcp`.
- Nine Services, all `ClusterIP`.
- Two PVCs `Bound`.
- One Ingress named `dashboard` with a Tailscale load-balancer hostname.
- One Secret `dashboard-config`.
- All pods on `dietpi` (`linux/amd64`).

The URL is `https://dashboard.<tailnet>.ts.net/`. The repository commits only the short hostname
`dashboard`, never the tailnet FQDN.

Local checks without a tailnet browser:

```bash
kubectl -n dashboard port-forward svc/dashboard 8080:80
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/
curl -sS http://127.0.0.1:8080/config.json | python3 -m json.tool >/dev/null && echo config:ok
curl -sS -o /dev/null -w 'bus:%{http_code}\n' http://127.0.0.1:8080/api/bus/api/health
curl -sS -o /dev/null -w 'tasks:%{http_code}\n' http://127.0.0.1:8080/api/tasks/health
curl -sS -o /dev/null -w 'fly:%{http_code}\n' 'http://127.0.0.1:8080/api/fly/api/fly-overs?lat=0&lng=0&radiusKm=1'
curl -sS -o /dev/null -w 'weather:%{http_code}\n' http://127.0.0.1:8080/api/weather/api/health
```

The fly call may return a non-2xx when the external adsb.lol feed is unavailable; that is a provider
failure, not a proxy failure. No REST or MCP Service should have an Ingress or non-ClusterIP type.

## First-run data

Bus starts empty. Trigger the one-off GTFS ingest through the proxy:

```bash
curl -sS -X POST https://dashboard.<tailnet>.ts.net/api/bus/api/refresh
```

It can take several minutes. Then verify a configured stop:

```bash
curl -sS https://dashboard.<tailnet>.ts.net/api/bus/api/stops/<stop-id>/times
```

Tasks start empty; an empty deck is valid. Create a task through the module API/SPA if a non-empty
deck is needed. The bus/task SQLite files live on their PVCs and survive pod replacement.

The Carris feed is about 77 MB compressed. `bus-catcher-rest` has a 2 GiB memory limit because the
first ingest OOMKilled at 512 MiB; the other module containers stay at 512 MiB. If the ingest still
fails, check `bus-catcher-rest` logs and events before retrying.

## REST proxy contract

| Public route | Backend Service | Backend path after prefix strip |
| ------------ | --------------- | ------------------------------- |
| `/api/bus/...` | `bus-catcher-rest:3000` | `/api/...` |
| `/api/tasks/...` | `procrastinator-tracker-rest:3000` | `/...` |
| `/api/fly/...` | `fly-over-tracker-rest:3000` | `/api/...` |
| `/api/weather/...` | `weather-psychic-rest:3000` | `/api/...` |

The nginx configuration uses static Kubernetes Service names. It does not use Docker's
`127.0.0.11` resolver. If a module Service is deleted and recreated with a new ClusterIP, delete the
frontend pod so nginx re-resolves the upstreams.

## MCP endpoints

| Module | Cross-namespace URL |
| ------ | ------------------- |
| bus-catcher | `http://bus-catcher-mcp.dashboard.svc.cluster.local:3001/mcp` |
| fly-over-tracker | `http://fly-over-tracker-mcp.dashboard.svc.cluster.local:3001/mcp` |
| procrastinator-tracker | `http://procrastinator-tracker-mcp.dashboard.svc.cluster.local:3001/mcp` |
| weather-psychic | `http://weather-psychic-mcp.dashboard.svc.cluster.local:3001/mcp` |

Smoke test from another namespace:

```bash
kubectl run mcp-smoke --rm -i --restart=Never --image=curlimages/curl:8.10.1 -- \
  -sS -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}' \
  http://bus-catcher-mcp.dashboard.svc.cluster.local:3001/mcp
```

Repeat for the other three URLs. The fly-over and weather MCP pods run an nginx `host-rewrite`
sidecar because those published servers reject a Kubernetes Service DNS Host header with
`Invalid Host`. The sidecar listens on 3001, proxies to the MCP process on `127.0.0.1:3002`, and
sends `Host: localhost`; consumers still use the normal Service URL. Bus and tasks need no sidecar.

Local debugging uses port-forward, not an ingress:

```bash
kubectl -n dashboard port-forward svc/bus-catcher-mcp 3200:3001
# http://127.0.0.1:3200/mcp
```

The procrastinator MCP server is single-session per container lifetime. If a client cannot
reconnect, delete its pod; task data is on the PVC:

```bash
kubectl -n dashboard delete pod \
  -l app.kubernetes.io/name=procrastinator-tracker,app.kubernetes.io/component=mcp
```

## Updates and rollback

Update one module at a time:

1. Change its backend image pin in `apps/dashboard/<module>-rest.yaml` and
   `apps/dashboard/<module>-mcp.yaml`.
2. Commit and reconcile.
3. Verify the REST health path, the dashboard block, and an MCP initialize call.
4. Record the new pin combination here.

Rollback is a Git revert of the pin commit, followed by Flux reconciliation. Do not use
`kubectl set image`; Flux will revert it.

## Backup and restore

The dashboard databases are separate from the Home Assistant state bundle. The backup script uses a
maintenance window because SQLite files are copied with the writers stopped.

```bash
./scripts/pull-dashboard-data.sh
ls -l ~/backups/home-sweet-lab/dashboard/<timestamp>/
sha256sum -c ~/backups/home-sweet-lab/dashboard/<timestamp>/SHA256SUMS
```

The script suspends the `apps` Flux Kustomization, scales the four stateful module Deployments to
zero, runs a temporary pinned Python helper pod, archives both PVCs with SHA-256, copies the archive
to the Mac, scales back, and resumes Flux. A trap restores Flux and replicas if the script fails.

Restore:

```bash
./scripts/restore-dashboard-data.sh \
  ~/backups/home-sweet-lab/dashboard/<timestamp>/dashboard-data.tar.gz
```

The script verifies the checksum before touching the PVCs, then stops writers, clears the two data
directories, extracts the archive, and restarts the workloads. See
[08-backups-and-recovery.md](08-backups-and-recovery.md).

Never commit `dashboard-data.tar.gz`, `SHA256SUMS`, or the PVC contents.

## Recovery procedures

### Pod lost or restarted

Flux/ReplicaSets recreate the pod. PVC data is intact. For a single-session MCP client, reconnect to
the same Service URL.

### Frontend configuration missing or invalid

```bash
kubectl -n dashboard describe pod -l app.kubernetes.io/name=dashboard
kubectl -n dashboard logs deploy/dashboard -c validate-config --previous
```

A missing Secret leaves the pod in `ContainerCreating`; an invalid file fails the init container with
a path and reason. Fix the JSON, rerun `scripts/create-dashboard-config-secret.sh`, and delete the
frontend pod. The frontend must not silently display a different location.

### Image pull failure

```bash
kubectl -n dashboard describe pod -l app.kubernetes.io/name=dashboard | grep -A5 Events
```

A `401`/`ImagePullBackOff` for the dashboard image means the GHCR package is still private and no
`ghcr-pull` Secret/reference is in place. Fix package visibility or the pull Secret, then reconcile.

### External provider outage

Weather and flights depend on external providers. Only those blocks degrade; the clock, bus, tasks,
and status strip for other modules continue. Recovery happens on the next refresh.

### Service recreated

If a module Service was deleted and recreated with a new ClusterIP, delete the frontend pod so nginx
re-resolves the static upstream names.

### Node reboot

After k3s and Flux return, all nine Deployments are recreated, both PVCs remain bound, the dashboard
URL returns `200`, the MCP URLs resolve, and bus/task data is intact. If a pod cannot schedule,
check the node, PVC, and image-pull events.

## Limitations

- The frontend is Tailscale-only; a TV that cannot join the tailnet cannot open it.
- REST and MCP are not externally exposed. There is no dashboard login, SSO, or MCP authentication.
- Single node, single replica, `local-path` storage. There is no HA, snapshot, or replication.
- The dashboard image and module images are third-party artifacts consumed by pinned tag. A missing
  or private image blocks that component.
- Frontend component packages and backend images version independently. Verify both after an update.
- The procrastinator MCP server is single-session; a restart drops the session, not the data.
- Configuration changes require a frontend pod restart; the file is read at page load.
- Backup/restore is a manual maintenance window, not an automated offsite backup.
- The bus GTFS ingest is memory-heavy: the feed is about 77 MB compressed and the first attempt
  OOMKilled at 512 MiB. `bus-catcher-rest` is capped at 2 GiB; this is a deliberate exception to the
  512 MiB module limit.
- Home Assistant remains the higher-priority workload; dashboard resource limits protect it, but a
  node-level failure affects both.

## Never commit

- Real dashboard coordinates, stop IDs, bus lines, or tailnet identifiers.
- `dashboard-config` Secret contents or a `ghcr-pull` token.
- SQLite files, `dashboard-data.tar.gz`, `SHA256SUMS`, or any archive under `backups/`/`bundles/`.
