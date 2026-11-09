# Runtime Verification Contract: Workload Image Updates

This feature changes no public API. The contract below defines the observable behavior that must be
true after the image pins are reconciled. Commands assume the repository root and a working
`kubeconfig` for the `dietpi` cluster. Replace `<tailnet>` placeholders; never commit real values.

## bus-catcher REST

### Readiness

```bash
kubectl -n dashboard rollout status deployment/bus-catcher-rest --timeout=10m
kubectl -n dashboard get pods -l app.kubernetes.io/name=bus-catcher,app.kubernetes.io/component=rest
```

**Expected**: rollout completes; one pod is `Running` with all containers Ready; the running image is
`ghcr.io/sousa99/bus-catcher-backend:0.4.0`.

### Health

```bash
kubectl -n dashboard port-forward svc/bus-catcher-rest 3000:3000
curl -sS http://127.0.0.1:3000/api/health
```

**Expected**: HTTP `200` and a JSON body with `"ok": true`.

### Status before refresh

```bash
curl -sS http://127.0.0.1:3000/api/status
```

**Expected**: JSON containing `lastRefresh`, `feedVersion`, `stale`, `refreshing`, and
`refreshError`. Record the pre-upgrade values. `refreshError` may be null or absent.

### Force refresh

```bash
curl -sS -X POST 'http://127.0.0.1:3000/api/refresh?force=true'
```

**Expected**: HTTP `202` with a started/accepted JSON result. The request returns immediately; the
ingest continues asynchronously.

Poll until the refresh completes:

```bash
curl -sS http://127.0.0.1:3000/api/status
```

**Expected**:

- `refreshing` returns to `false`.
- `refreshError` is null or absent.
- `lastRefresh` advances past the pre-upgrade value.
- `stale` becomes `false` or reflects a fresh feed.
- No container restart with reason `OOMKilled` occurred.

### No OOMKill

```bash
kubectl -n dashboard get pod -l app.kubernetes.io/name=bus-catcher,app.kubernetes.io/component=rest \
  -o jsonpath='{.items[*].status.containerStatuses[*].lastState.terminated.reason}{"\n"}'
kubectl -n dashboard describe pod -l app.kubernetes.io/name=bus-catcher,app.kubernetes.io/component=rest | grep -A5 'Last State'
```

**Expected**: no `OOMKilled` last state. A previous 0.3.0 termination may still appear in history;
only a termination after the 0.4.0 rollout counts as a failure.

## bus-catcher MCP

### Readiness

```bash
kubectl -n dashboard rollout status deployment/bus-catcher-mcp --timeout=10m
kubectl -n dashboard get pods -l app.kubernetes.io/name=bus-catcher,app.kubernetes.io/component=mcp
```

**Expected**: rollout completes; one pod Ready; the running image is
`ghcr.io/sousa99/bus-catcher-backend:0.4.0`.

### MCP initialize

```bash
kubectl run mcp-smoke --rm -i --restart=Never --image=curlimages/curl:8.10.1 -- \
  -sS -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}' \
  http://bus-catcher-mcp.dashboard.svc.cluster.local:3001/mcp
```

**Expected**: a JSON-RPC result containing `serverInfo`. No `Invalid Host` error; bus-catcher does
not need the host-rewrite sidecar.

### Data consistency

Read the same configured stop through REST and MCP after the refresh.

```bash
curl -sS 'http://127.0.0.1:3000/api/stops/<stop-id>/times'
```

**Expected**: REST returns schedule data newer than the stale pre-upgrade dataset. The MCP
`get_stop_times` tool returns data from the same database. Neither call reports a concurrent-ingest
or database-lock error.

## Dashboard path

```bash
kubectl -n dashboard port-forward svc/dashboard 8080:80
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/api/bus/api/health
```

**Expected**: HTTP `200`; the existing nginx proxy still reaches the bus Service.

## Bus persistence

```bash
kubectl -n dashboard delete pod -l app.kubernetes.io/name=bus-catcher,app.kubernetes.io/component=rest
kubectl -n dashboard rollout status deployment/bus-catcher-rest --timeout=10m
curl -sS http://127.0.0.1:3000/api/status
```

**Expected**: the replacement pod becomes Ready; `lastRefresh` and `feedVersion` still reflect the
pre-restart refresh; the configured stop list is unchanged; the schedule is readable without a new
full ingest.

## Home Assistant readiness

```bash
kubectl -n home-assistant rollout status deployment/home-assistant --timeout=10m
kubectl -n home-assistant get pods
```

**Expected**: rollout completes; the pod is `Running` and Ready; all four image references report
`ghcr.io/sousa99/home-sweet-home-home-assistant:main-20261109193052-7e131ee`.

## Home Assistant seed evidence

```bash
kubectl -n home-assistant logs deploy/home-assistant -c seed-config
kubectl -n home-assistant logs deploy/home-assistant -c restore-state
kubectl -n home-assistant logs deploy/home-assistant -c configure-http
```

**Expected**:

- `seed-config` exits `0`; the log may be empty because `cp -a` is silent.
- `restore-state` exits `0` and does not apply a new bundle, because no new archive was uploaded.
- `configure-http` exits `0` and reports success or no change.

A non-zero init exit blocks the main container and is a rollback trigger.

## Home Assistant tracked configuration

```bash
kubectl -n home-assistant exec deploy/home-assistant -- \
  sh -c 'test -f /config/custom_components/home_sweet_home_agent/manifest.json && echo component-manifest-ok'
kubectl -n home-assistant exec deploy/home-assistant -- \
  sh -c 'test -f /config/custom_components/home_sweet_home_agent/conversation.py && echo component-code-ok'
kubectl -n home-assistant exec deploy/home-assistant -- \
  sh -c 'grep -q "Charge Server" /config/automations.yaml && echo automations-ok'
```

**Expected**: all three markers print. This proves the seed copied new tracked configuration,
including the custom integration.

## Home Assistant runtime state preservation

```bash
kubectl -n home-assistant exec deploy/home-assistant -- \
  sh -c 'test -f /config/.storage/core.config_entries && echo storage-ok'
kubectl -n home-assistant exec deploy/home-assistant -- \
  sh -c 'test -f /config/zigbee.db && echo zigbee-ok'
kubectl -n home-assistant exec deploy/home-assistant -- \
  sh -c 'ls -l /config/home-assistant_v2.db* 2>/dev/null | head'
kubectl -n home-assistant exec deploy/home-assistant -- \
  sh -c 'test -f /config/secrets.yaml && echo secrets-present || echo secrets-absent'
```

**Expected**:

- `.storage/core.config_entries` exists.
- `zigbee.db` exists and is updated by Home Assistant startup.
- The recorder database files are present.
- `secrets.yaml` is either preserved exactly as before or absent exactly as before; the change must
  not create or remove it.
- Existing integrations and the Assist pipeline selection are still visible in Home Assistant.
- No state-bundle upload or manual `/config` copy was performed.

## Home Assistant UI and integration availability

```bash
kubectl -n home-assistant port-forward svc/home-assistant 8123:8123
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8123/manifest.json
```

**Expected**: HTTP `200`. In the UI, the `Home Sweet Home Agent` integration is available. If it is
not configured yet, adding it with the agent URL and bearer token succeeds. If it is already
configured, it remains configured. Selecting the conversation agent for Assist remains a manual
operator step stored in `.storage`.

## Manifest validation

```bash
./scripts/validate.sh
```

**Expected**: renders `apps/` and `infrastructure/`, passes `kubeconform`, yamllint, Python and shell
tests, and gitleaks with no findings.

## Rollback contract

```bash
git revert <pin-commit>
flux reconcile source git flux-system
flux reconcile kustomization apps --with-source
kubectl -n dashboard rollout status deployment/bus-catcher-rest --timeout=10m
kubectl -n dashboard rollout status deployment/bus-catcher-mcp --timeout=10m
kubectl -n home-assistant rollout status deployment/home-assistant --timeout=10m
```

**Expected**: both bus workloads return to `0.3.0` and Home Assistant returns to
`main-20261025090622-dd38b4b`; all workloads become Ready; bus and Home Assistant data remain on
their PVCs.
