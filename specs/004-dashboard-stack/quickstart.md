# Quickstart Validation: Dashboard Stack on k3s

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

This guide proves the feature end-to-end on the real cluster. It is a validation runbook, not a
complete implementation guide. Commands use the repository root; replace `<tailnet>`, `<stop-id>`,
and file paths with local values.

## Prerequisites

- Flux reconciles this repository and the `apps` Kustomization is `Ready`.
- Tailscale Kubernetes Operator and the `operator-oauth` Secret work; Home Assistant already proves
  the HTTPS ingress path.
- `kubectl` points at the `dietpi` cluster; `flux` CLI is available for reconcile commands.
- The dashboard GHCR package is public, or a manual `ghcr-pull` Secret exists and the frontend
  Deployment references it.
- A dashboard JSON file exists outside Git, based on
  [config.example.json](../../apps/dashboard/config.example.json).
- Docker or a registry client can check image visibility from the Mac.

## 1. Validate the repository

```bash
./scripts/validate.sh
```

Expected: Kustomize renders, `kubeconform` passes, YAML lint passes, the config validator tests pass,
and `gitleaks` finds no secrets.

If the dashboard package is still private, verify the failure and fix it before continuing:

```bash
docker manifest inspect ghcr.io/sousa99/home-sweet-home-dashboard:0.1.0 >/dev/null && echo public
```

Supported fix: make the GHCR package public (GitHub → package settings → visibility). Fallback:
create a `read:packages` token and a pull Secret, then add the Secret reference to the frontend
Deployment in Git:

```bash
kubectl -n dashboard create secret docker-registry ghcr-pull \
  --docker-server=ghcr.io \
  --docker-username=<github-user> \
  --docker-password=<read-packages-token>
```

Never commit the token or the Secret manifest.

## 2. Create the household configuration Secret

Do not commit this file. It contains the household location and stop IDs.

```bash
cp apps/dashboard/config.example.json ~/dashboard-config.json
$EDITOR ~/dashboard-config.json
python3 apps/dashboard/validate-config.py ~/dashboard-config.json
./scripts/create-dashboard-config-secret.sh ~/dashboard-config.json
```

The script creates the `dashboard` namespace if Flux has not yet, creates or updates
`dashboard-config`, and does not print the JSON. If the frontend pod was already waiting on the
Secret, delete it so the init container runs:

```bash
kubectl -n dashboard get secret dashboard-config
kubectl -n dashboard delete pod -l app.kubernetes.io/name=dashboard --ignore-not-found
```

## 3. Reconcile and verify

```bash
flux reconcile source git flux-system
flux reconcile kustomization apps --with-source
kubectl -n dashboard get deploy,pods,svc,ingress,pvc
```

Expected:

- Nine Deployments: `dashboard`, four `-rest`, four `-mcp`.
- Nine Services: one frontend plus REST/MCP per module.
- Two PVCs `Bound`.
- One Ingress named `dashboard` with a Tailscale load-balancer hostname.
- All pods `Running` and `Ready` on `dietpi`.

Rollout status:

```bash
kubectl -n dashboard rollout status deployment/dashboard --timeout=5m
kubectl -n dashboard rollout status deployment/bus-catcher-rest --timeout=5m
kubectl -n dashboard rollout status deployment/bus-catcher-mcp --timeout=5m
kubectl -n dashboard rollout status deployment/fly-over-tracker-rest --timeout=5m
kubectl -n dashboard rollout status deployment/fly-over-tracker-mcp --timeout=5m
kubectl -n dashboard rollout status deployment/procrastinator-tracker-rest --timeout=5m
kubectl -n dashboard rollout status deployment/procrastinator-tracker-mcp --timeout=5m
kubectl -n dashboard rollout status deployment/weather-psychic-rest --timeout=5m
kubectl -n dashboard rollout status deployment/weather-psychic-mcp --timeout=5m
```

## 4. Verify frontend access and REST proxying

From a tailnet device:

```bash
kubectl -n dashboard describe ingress dashboard
curl -sS -o /dev/null -w '%{http_code}\n' https://dashboard.<tailnet>.ts.net/
```

Expected: `200`, a Tailscale-issued certificate, and a dashboard with the clock and configured
blocks.

For local API verification without a tailnet device, port-forward the frontend:

```bash
kubectl -n dashboard port-forward svc/dashboard 8080:80
```

In another terminal:

```bash
curl -sS -o /dev/null -w 'page:%{http_code}\n' http://127.0.0.1:8080/
curl -sS http://127.0.0.1:8080/config.json | python3 -m json.tool >/dev/null && echo config:ok
curl -sS -o /dev/null -w 'bus:%{http_code}\n' http://127.0.0.1:8080/api/bus/api/health
curl -sS -o /dev/null -w 'tasks:%{http_code}\n' http://127.0.0.1:8080/api/tasks/health
curl -sS -o /dev/null -w 'fly:%{http_code}\n' 'http://127.0.0.1:8080/api/fly/api/fly-overs?lat=0&lng=0&radiusKm=1'
curl -sS -o /dev/null -w 'weather:%{http_code}\n' http://127.0.0.1:8080/api/weather/api/health
```

Expected: page and config succeed; each health call is non-5xx while its pod is Ready. The fly call
can return a non-2xx if the external feed is unavailable; that is a provider failure, not a proxy
failure.

Verify that no REST or MCP endpoint is externally exposed:

```bash
kubectl -n dashboard get ingress
kubectl -n dashboard get svc
```

Expected: one Ingress (`dashboard`); all Services `ClusterIP`; no LoadBalancer or NodePort.

## 5. First-run bus data

The bus schedule starts empty. Trigger the one-off GTFS ingest through the dashboard proxy:

```bash
curl -sS -X POST https://dashboard.<tailnet>.ts.net/api/bus/api/refresh
```

This can take several minutes. Then verify a configured stop:

```bash
curl -sS https://dashboard.<tailnet>.ts.net/api/bus/api/stops/<stop-id>/times
```

Expected: departure data for the stop; the dashboard bus block shows the configured stop cards.
If the ingest fails, the bus block remains unavailable/empty while tasks, flights, weather, and the
clock continue to work. Retry the POST or inspect `bus-catcher-rest` logs.

Tasks start empty; an empty task deck is valid. Create a task through the module API/SPA if a
non-empty deck is needed for the drill.

## 6. Verify MCP endpoints from another namespace

Use a temporary pod in another namespace (or the agent namespace once it exists):

```bash
kubectl run mcp-smoke --rm -i --restart=Never --image=curlimages/curl:8.10.1 -- \
  -sS -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}' \
  http://bus-catcher-mcp.dashboard.svc.cluster.local:3001/mcp
```

Expected: an MCP initialize response (JSON or an SSE `data:` frame), not a connection error. Repeat
for `fly-over-tracker-mcp`, `procrastinator-tracker-mcp`, and `weather-psychic-mcp`.

For local opencode debugging, do not expose MCP over Tailscale:

```bash
kubectl -n dashboard port-forward svc/bus-catcher-mcp 3200:3001
# then use http://127.0.0.1:3200/mcp in a local MCP client
```

The procrastinator MCP is single-session. If a client cannot reconnect:

```bash
kubectl -n dashboard delete pod \
  -l app.kubernetes.io/name=procrastinator-tracker,app.kubernetes.io/component=mcp
```

Data on the PVC survives.

## 7. Backup and restore drill

Run during a low-use window. The script suspends the `apps` Kustomization, stops the four stateful
Deployments, copies both SQLite files, and restores normal operation.

```bash
./scripts/pull-dashboard-data.sh
ls -l ~/backups/home-sweet-lab/dashboard/<timestamp>/
sha256sum -c ~/backups/home-sweet-lab/dashboard/<timestamp>/SHA256SUMS
```

Expected: archive and checksum present; checksums match; all workloads return to `Ready`; the Flux
Kustomization is resumed and `Ready`.

Restore drill into the same cluster:

```bash
./scripts/restore-dashboard-data.sh ~/backups/home-sweet-lab/dashboard/<timestamp>/dashboard-data.tar.gz
kubectl -n dashboard get pods
```

Expected: both databases are restored, the checksum is verified before extraction, the dashboard
shows the restored bus/task data, and the MCP endpoints respond. Record the drill date and result in
`docs/08-backups-and-recovery.md`.

## 8. Recovery drills

### Frontend pod loss

```bash
kubectl -n dashboard delete pod -l app.kubernetes.io/name=dashboard
kubectl -n dashboard rollout status deployment/dashboard --timeout=5m
curl -sS -o /dev/null -w '%{http_code}\n' https://dashboard.<tailnet>.ts.net/
```

Expected: `200` within 2 minutes. No data loss.

### Backend or MCP pod loss

```bash
kubectl -n dashboard delete pod -l app.kubernetes.io/name=bus-catcher
kubectl -n dashboard get pods -l app.kubernetes.io/name=bus-catcher
```

Expected: both bus pods are recreated; the dashboard recovers; the MCP Service resolves after the
new pod is Ready. Bus data survives.

### Node reboot

```bash
# after the node returns
kubectl get nodes
flux get kustomizations
kubectl -n dashboard get pods,pvc
curl -sS -o /dev/null -w '%{http_code}\n' https://dashboard.<tailnet>.ts.net/
```

Expected: all workloads Ready within 10 minutes of k3s; PVCs `Bound`; dashboard `200`; MCP URLs
respond; bus/task data intact.

### Image pull failure

```bash
kubectl -n dashboard describe pod -l app.kubernetes.io/name=dashboard | grep -A5 Events
```

Expected: a visible `ImagePullBackOff`/`ErrImagePull` with the image reference. Fix package
visibility or create `ghcr-pull` and reconcile. Other modules continue if only the dashboard image is
affected.

### Missing or invalid config

```bash
kubectl -n dashboard describe pod -l app.kubernetes.io/name=dashboard
kubectl -n dashboard logs deploy/dashboard -c validate-config --previous
```

Expected: a missing Secret event or a validator message naming the bad path. Fix the file, recreate
the Secret, delete the frontend pod, and verify. The frontend must not silently display a different
location.

### External provider outage

Stop or block the weather or flight provider. Reload the dashboard.

Expected: only that block degrades; the status strip marks it offline; clock, bus, tasks, and the
other module continue. Recovery happens on the next refresh after the provider returns.

### Service recreated

If a module Service was deleted and recreated with a new ClusterIP, restart the frontend:

```bash
kubectl -n dashboard delete pod -l app.kubernetes.io/name=dashboard
```

Expected: nginx re-resolves the static upstream names and API routes work.

## 9. Module update and rollback

Update one module at a time:

1. Change its backend image pin in the module manifest.
2. Commit and reconcile.
3. Verify its REST health, dashboard block, and MCP initialize call.
4. Record the new pin combination.

Rollback:

```bash
git revert <pin-change-commit>
flux reconcile source git flux-system
flux reconcile kustomization apps --with-source
```

Expected: the previous dashboard/backend combination is Ready within 10 minutes.

## 10. Final acceptance

The feature is accepted when:

- All nine Deployments are Ready and both PVCs are `Bound`.
- The dashboard loads over Tailscale with the configured blocks.
- All four `/api/<module>/` routes work through the frontend.
- All four MCP URLs respond from another namespace.
- Bus/task data survives a pod restart and a node reboot.
- The backup/restore drill passes with checksums.
- Only the dashboard has an external entry point; REST and MCP do not.
- No real location, stop ID, credential, database, or backup is in Git.
