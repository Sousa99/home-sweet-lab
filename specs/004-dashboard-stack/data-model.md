# Phase 1 Data Model: Dashboard Stack on k3s

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

This is an infrastructure feature; the data model describes cluster objects, configuration shape,
storage, and runtime relationships rather than application tables.

## 1. Module Runtime

Four modules, each with a REST process and an MCP process. The image, command, ports, health, and
storage are fixed by the published module images.

| Module | Image tag | REST command | MCP command | REST port | MCP port | Storage |
| ------ | --------- | ------------ | ----------- | --------- | -------- | ------- |
| bus-catcher | `ghcr.io/sousa99/bus-catcher-backend:0.2.0` | `node dist/index.js --http` | `node dist/index.js --mcp` | 3000 | 3001 | `bus-catcher-data` |
| fly-over-tracker | `ghcr.io/sousa99/fly-over-tracker-backend:0.5.0` | `node dist/index.js --http` | `node dist/index.js --mcp` | 3000 | 3001 | none |
| procrastinator-tracker | `ghcr.io/sousa99/procrastinator-tracker-backend:0.2.0` | `sh -c 'node dist/migrate.js && node dist/index.js --http'` | `sh -c 'node dist/migrate.js && node dist/index.js --mcp'` | 3000 | 3001 | `procrastinator-data` |
| weather-psychic | `ghcr.io/sousa99/weather-psychic-backend:0.1.0` | `node dist/index.js --http` | `node dist/index.js --mcp` | 3000 | 3001 | none |

The fly-over-tracker and weather-psychic MCP processes listen on `0.0.0.0:3002` and run beside an nginx
`host-rewrite` sidecar that listens on `3001`, proxies to `127.0.0.1:3002`, and sets
`Host: localhost` plus `Origin: http://localhost`. Their published MCP helper rejects the Kubernetes
Service DNS Host header. The Service still exposes 3001, so consumers use the same URL shape for all
four modules. Bus-catcher and procrastinator do not need the sidecar.

Common environment:

| Variable | Value | Notes |
| -------- | ----- | ----- |
| `HOST` | `0.0.0.0` | Set for fly-over and weather as in Compose; harmless for all. |
| `PORT` | `3000` | REST listener. |
| `MCP_PORT` | `3001` (bus/tasks), `3002` (fly/weather) | MCP listener. Fly/weather use the sidecar for Host rewriting. |
| `DB_PATH` | `/data/bus-catcher.db` | Bus only. |
| `DATABASE_URL` | `/data/procrastinator.db` | Procrastinator only. |
| `SNAPSHOT_CACHE_TTL_MS` | `60000` | Fly-over only. |

Runtime relationships:

```text
Browser ──HTTPS──▶ Tailscale Ingress ──▶ dashboard Service :80
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

## 2. Dashboard Config

The runtime JSON is mounted from the manual `dashboard-config` Secret at
`/usr/share/nginx/html/config.json`.

### Required and optional fields

| Path | Type | Required | Validation |
| ---- | ---- | -------- | ---------- |
| `clock` | object | No | If present, object. |
| `clock.defaultFormat` | `"12h"` or `"24h"` | No | Enum. |
| `clock.switchable` | boolean | No | Type. |
| `clock.align` | `"left"`, `"center"`, `"right"` | No | Enum. |
| `bus` | object | No | If present, object. |
| `bus.stops` | array | **Yes** | Array; may be empty. |
| `bus.stops[].id` | string | **Yes** | Non-empty string. |
| `bus.stops[].name` | string | **Yes** | Non-empty string. |
| `bus.stops[].lines` | array of strings | No | If present, string array. |
| `bus.stops[].limit` | integer | No | 1–20. |
| `bus.stops[].refetchIntervalMs` | integer | No | `>= 0`; `0` disables. |
| `flights` | object | **Yes** | Object. |
| `flights.location` | object | **Yes** | Object. |
| `flights.location.lat` | number | **Yes** | Finite, -90–90. |
| `flights.location.lng` | number | **Yes** | Finite, -180–180. |
| `flights.location.radiusKm` | number | **Yes** | Finite, `> 0`. |
| `flights.autoRefresh` | `"off"`, `5`, `10`, `30`, `60` | No | Enum. |
| `flights.maxResults` | integer | No | `1–20` if present. |
| `flights.debugMap` | boolean | No | Type. |
| `tasks` | object | No | If present, object. |
| `tasks.filters` | object | No | Passed to the widget. |
| `tasks.refreshRateMs` | integer | No | `>= 0`. |
| `tasks.autoRotateMs` | integer | No | `>= 0`; `0` disables. |
| `tasks.transitionVariant` | string | No | Upstream enum; non-empty. |
| `tasks.slideDurationMs` | integer | No | `>= 0`. |
| `weather` | object | **Yes** | Object. |
| `weather.location` | object | **Yes** | Object. |
| `weather.location.id` | number/string | No | Passed through. |
| `weather.location.name` | string | **Yes** | Non-empty. |
| `weather.location.latitude` | number | **Yes** | Finite, -90–90. |
| `weather.location.longitude` | number | **Yes** | Finite, -180–180. |
| `weather.location.timezone` | string | **Yes** | Non-empty IANA timezone string. |
| `weather.location.country` | string | No | Passed through. |
| `weather.refetchIntervalMs` | integer | No | `>= 0`; `0` disables. |
| `status` | object | No | If present, object. |
| `status.intervalMs` | integer | No | `> 0`. |
| `placeholders` | array of `{title, description}` | No | Array; each object with strings. |

Rules:

- The file must be valid JSON and an object at the root.
- The validator checks types and ranges. It does not reject unknown keys, matching the dashboard's
  deep-merge behavior.
- `flights.location`, `weather.location`, and `bus.stops` are explicitly required so the operator
  cannot accidentally rely on the image's built-in location.
- The validator prints only the failing path and reason; it never echoes field values.
- A missing Secret prevents the frontend pod from starting. An invalid file fails the init
  container. The dashboard's silent fallback is therefore bypassed.

### Secret shape

| Key | Value |
| --- | ----- |
| `config.json` | The JSON document, created manually with `kubectl create secret generic dashboard-config --from-file=config.json=<path>` |

The Secret is not managed by Flux. It is recorded in `docs/07-secrets-and-unsynced-state.md` and
included in the operator's backup/credential inventory.

## 3. Cluster Objects

### Namespace

| Field | Value |
| ----- | ----- |
| Name | `dashboard` |
| Labels | `app.kubernetes.io/part-of: home-sweet-lab` |

### Deployments

| Name | Replicas | Strategy | Containers | Storage |
| ---- | -------- | -------- | ---------- | ------- |
| `dashboard` | 1 | RollingUpdate | `dashboard` + `validate-config` init | none |
| `bus-catcher-rest` | 1 | Recreate | `rest` | `bus-catcher-data` |
| `bus-catcher-mcp` | 1 | Recreate | `mcp` | `bus-catcher-data` |
| `fly-over-tracker-rest` | 1 | Recreate | `rest` | none |
| `fly-over-tracker-mcp` | 1 | Recreate | `mcp` + `host-rewrite` | none |
| `procrastinator-tracker-rest` | 1 | Recreate | `rest` | `procrastinator-data` |
| `procrastinator-tracker-mcp` | 1 | Recreate | `mcp` | `procrastinator-data` |
| `weather-psychic-rest` | 1 | Recreate | `rest` | none |
| `weather-psychic-mcp` | 1 | Recreate | `mcp` + `host-rewrite` | none |

All module Deployments use `Recreate` to avoid overlapping writers during a rollout on the shared
SQLite volume. The frontend uses RollingUpdate because it holds no state.

Labels:

- Common: `app.kubernetes.io/part-of: home-sweet-lab`
- Module: `app.kubernetes.io/name: <module>`
- Mode: `app.kubernetes.io/component: rest|mcp`
- Frontend: `app.kubernetes.io/name: dashboard`

### Services

| Name | Selector | Port | Target |
| ---- | -------- | ---- | ------ |
| `dashboard` | `name=dashboard` | 80 | nginx 80 |
| `bus-catcher-rest` | `name=bus-catcher,component=rest` | 3000 | 3000 |
| `bus-catcher-mcp` | `name=bus-catcher,component=mcp` | 3001 | 3001 |
| `fly-over-tracker-rest` | `name=fly-over-tracker,component=rest` | 3000 | 3000 |
| `fly-over-tracker-mcp` | `name=fly-over-tracker,component=mcp` | 3001 | 3001 |
| `procrastinator-tracker-rest` | `name=procrastinator-tracker,component=rest` | 3000 | 3000 |
| `procrastinator-tracker-mcp` | `name=procrastinator-tracker,component=mcp` | 3001 | 3001 |
| `weather-psychic-rest` | `name=weather-psychic,component=rest` | 3000 | 3000 |
| `weather-psychic-mcp` | `name=weather-psychic,component=mcp` | 3001 | 3001 |

All Services are `ClusterIP`. Only `dashboard` is referenced by the Tailscale Ingress.

### Ingress

| Field | Value |
| ----- | ----- |
| Name | `dashboard` |
| Class | `tailscale` |
| Host | `dashboard` (the operator appends the tailnet suffix) |
| Backend | `dashboard:80` |
| TLS | Tailscale-issued certificate for `dashboard.<tailnet>.ts.net` |

### PersistentVolumeClaims

| Name | Size | Access mode | Storage class | Mount |
| ---- | ---- | ----------- | ------------- | ----- |
| `bus-catcher-data` | 10 GiB | ReadWriteOnce | `local-path` | `/data` in bus REST and MCP |
| `procrastinator-data` | 1 GiB | ReadWriteOnce | `local-path` | `/data` in procrastinator REST and MCP |

Both PVCs use `WaitForFirstConsumer`, matching the default class. They are not backed up by storage
snapshots; the scripts copy the SQLite files while writers are stopped.

### Manual Secrets

| Name | Namespace | Purpose | Created by |
| ---- | --------- | ------- | ---------- |
| `dashboard-config` | `dashboard` | Runtime dashboard JSON | `scripts/create-dashboard-config-secret.sh` |
| `ghcr-pull` (optional) | `dashboard` | GHCR pull credential only if the dashboard package stays private | Operator, documented fallback |

### Generated ConfigMaps

| Name | Source | Keys | Mount |
| ---- | ------ | ---- | ----- |
| `dashboard-nginx` | `apps/dashboard/nginx.conf` | `nginx.conf` | `/etc/nginx/conf.d/default.conf` (subPath) |
| `dashboard-config-check` | `apps/dashboard/validate-config.py` | `validate-config.py` | `/check/validate-config.py` |

Kustomize `configMapGenerator` gives these content-hashed names and updates the volume references,
so a config change rolls the frontend pod.

## 4. Backup Asset

| Field | Value |
| ----- | ----- |
| Format | `tar.gz` containing `bus-catcher/bus-catcher.db` and `procrastinator/procrastinator.db` |
| Checksum | SHA-256 recorded alongside the archive |
| Location | `~/backups/home-sweet-lab/dashboard/<timestamp>/` by default |
| Consistency | Writers scaled to zero for the duration; Flux suspended |
| Retention | Keep at least the previous archive; offsite copy is the operator's responsibility |
| Git | Never committed; `backups/` and `bundles/` are ignored |

Restore requires stopping the four stateful Deployments, verifying the checksum, extracting into the
PVCs, then scaling back and reconciling. A restore drill is part of acceptance.

## 5. Image Pin Matrix

| Component | Pin | Notes |
| --------- | --- | ----- |
| Dashboard frontend | `ghcr.io/sousa99/home-sweet-home-dashboard:0.1.0` | Make package public or use `ghcr-pull`. |
| Bus backend | `ghcr.io/sousa99/bus-catcher-backend:0.2.0` | Components package `^0.2.0`. |
| Fly-over backend | `ghcr.io/sousa99/fly-over-tracker-backend:0.5.0` | Components package `^0.5.0`. |
| Procrastinator backend | `ghcr.io/sousa99/procrastinator-tracker-backend:0.2.0` | Components package `^0.2.0`. |
| Weather backend | `ghcr.io/sousa99/weather-psychic-backend:0.1.0` | Components package `^0.1.0`. |
| Config validator | `python:3.12-alpine@sha256:b658b05ce9c4eb97ec6fc19424818a1f31993659c2b505a532f470e83807815d` | Reused from the host-metrics image. |
| MCP host rewrite | `nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10` | Sidecar for fly-over and weather MCP only. |

Update one module at a time: change its backend pin in the module manifest, reconcile, verify the
frontend block and MCP call, then record the new combination. Rollback is a Git revert.

## 6. Resource Profile

| Workload | CPU request | CPU limit | Memory request | Memory limit |
| -------- | ----------- | --------- | -------------- | ------------ |
| `bus-catcher-rest` | 250m | 2 | 512Mi | 10Gi |
| `bus-catcher-mcp` | 100m | 1 | 256Mi | 1Gi |
| Other module containers (REST or MCP) | 50m | 500m | 128Mi | 512Mi |
| Frontend | 25m | 250m | 32Mi | 128Mi |

`bus-catcher-rest` needs the larger limit because the Carris GTFS feed is about 77 MB compressed and
974 MB uncompressed; the one-off ingest was OOMKilled at 2 GiB during validation. The worker unzips
the archive and parses the 807 MB `stop_times.txt` in memory. The 10 GiB PVC leaves room for the
indexed SQLite database. Totals are approximately 875m CPU and 1.75Gi memory requested; 6.5 CPU and
14.1Gi memory at limits. Home Assistant, Flux, Tailscale, and k3s retain headroom; the bus limits
are a deliberate exception for the one-off ingest and settle back after it completes.

## 7. State Transitions

| Event | Expected state |
| ----- | -------------- |
| Initial reconcile | Namespace, ConfigMaps, PVCs, Services, Deployments, Ingress created; pods schedule on `dietpi`. |
| Config Secret missing | Frontend pod stays `ContainerCreating`; REST/MCP start normally; event names the missing Secret. |
| Config Secret invalid | Frontend init container exits non-zero; pod restarts with backoff; REST/MCP unaffected. |
| Config Secret updated | Operator deletes the frontend pod; new pod validates and serves the new config. |
| Frontend pod deleted | ReplicaSet recreates it; data unaffected. |
| REST pod deleted | ReplicaSet recreates it; MCP keeps its own endpoint; SQLite unaffected. |
| MCP pod deleted | ReplicaSet recreates it; single-session clients reconnect; data unaffected. |
| Module image pull fails | Pod `ImagePullBackOff`; other modules continue. Frontend block for that module is unavailable. |
| Bus GTFS ingest | Empty schedule becomes populated; dashboard shows departures. |
| External weather/flight provider down | Only that block degrades; status strip marks it offline; other blocks continue. |
| Node reboot | All pods recreated; PVC data intact; dashboard and MCP return after k3s/Flux. |
| PVC loss | Bus or tasks data absent; restore from the latest backup; other module unaffected. |
| Backup window | Apps Kustomization suspended, stateful pods at zero, archive copied, then restored. |
