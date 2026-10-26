# Implementation Plan: Dashboard Stack on k3s

**Branch**: `main` | **Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-dashboard-stack/spec.md`

## Summary

Deploy the published `home-sweet-home-dashboard` stack into the `dashboard` namespace: one nginx
frontend, four module REST backends, and four module MCP servers. The browser reaches only the
Tailscale-exposed frontend; its same-origin `/api/<module>/` requests are proxied to cluster-internal
REST Services. MCP servers stay cluster-internal for `home-sweet-home-agent`, with
`kubectl port-forward` for debugging. Bus-catcher and procrastinator-tracker SQLite data lives on
`local-path` PVCs; the household-specific dashboard JSON is a manually created Secret validated by
an init container. All manifests, docs, scripts, and validation changes are owned by this repository;
the dashboard and module repositories are not modified.

The plan mirrors the published Compose topology but resolves three Kubernetes-specific problems:
Docker DNS in the bundled nginx configuration, independent REST/MCP Service routing, and a
frontend configuration loader that silently falls back to defaults when `/config.json` is missing or
invalid.

## Technical Context

**Language/Version**: YAML and Kustomize `v5`; Bash scripts; Python `3.12` for the runtime-config
validator and tests. Application containers are the published Node.js module images and the
published nginx dashboard image.

**Primary Dependencies**: k3s, Flux Kustomizations and image pins, Traefik (not used by this app),
Tailscale Kubernetes Operator, `local-path` storage, GHCR images:
`home-sweet-home-dashboard:0.1.0`, `bus-catcher-backend:0.2.0`,
`fly-over-tracker-backend:0.5.0`, `procrastinator-tracker-backend:0.2.0`, and
`weather-psychic-backend:0.1.0`. The pinned `python:3.12-alpine` digest from the host-metrics image
is reused for config validation.

**Storage**: Two `local-path` PersistentVolumeClaims, `bus-catcher-data` and
`procrastinator-data`, each 1 GiB and mounted at `/data` by the matching REST and MCP pods. Fly-over
and weather are stateless.

**Testing**: `scripts/validate.sh` (Kustomize render, `kubeconform`, `yamllint`, `gitleaks`, Python
tests), a new `apps/dashboard/test_validate_config.py`, and documented cluster smoke, backup,
restore, and recovery drills.

**Target Platform**: Single k3s node `dietpi`, x86-64 (`linux/amd64`), DietPi on Debian 13,
15 GiB RAM, `local-path` storage, Tailscale ingress class. Module images are `linux/amd64`; the
Deployments select the `amd64` architecture so a future arm64 node fails visibly instead of running
under unexpected emulation.

**Project Type**: GitOps-managed cluster workload; infrastructure-as-code, not an application source
tree.

**Performance Goals**: Dashboard page reachable in under 5 seconds from a tailnet device; all four
API proxy smoke calls complete in under 2 seconds when backends are warm; six-hour household use
without pod restarts or memory pressure; no dashboard backend blocks Home Assistant.

**Constraints**: Single node and single replica per workload; no external REST or MCP exposure; no
public TLS; no image builds in this repository; no image automation; dashboard configuration and SQLite
data never in Git; the dashboard image must be pullable or a manual pull Secret supplied; no
dashboard/module source changes.

**Scale/Scope**: One household, one TV/large-screen client, one agent consumer, nine Deployments
(one frontend, four REST, four MCP), nine Services, two PVCs, one Tailscale Ingress, and a small
manual Secret surface.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Result |
| --------- | ---- | ------ |
| I. GitOps as source of truth | All deployable resources live in `apps/dashboard` and are reconciled by Flux; manual actions are limited to the config Secret, optional pull Secret, and backup/restore maintenance windows. | Pass |
| II. Reproducible host bootstrap | The new `docs/13-dashboard.md` records prerequisites, manual steps, verification, and recovery; the app is reproducible from Git plus documented manual state. | Pass |
| III. Public repositories, private state | Household coordinates, stop IDs, and the dashboard JSON live in a manual Secret; SQLite files and backups are excluded from Git; docs use placeholders. | Pass |
| IV. Local-first, documented cloud dependencies | The dashboard, REST, and MCP run locally. GHCR, Tailscale, and the GTFS/flight/weather providers are documented with failure behavior. | Pass |
| V. Recoverability before optimization | Two PVCs, a documented stop-copy backup/restore procedure, and node-reboot recovery are part of the design. | Pass |
| VI. Small, reviewable, validated changes | One app Kustomization, pinned images, no image automation, manifest validation, and documented rollback by Git pin. | Pass |
| VII. Clear repository boundaries | This repository deploys published images and owns cluster resources; the dashboard repo owns the frontend image and module repos own the backends. No source is copied. | Pass |
| Technology standards | YAML/Kustomize, Flux, GHCR pins, `local-path`, manual Secrets, no Helm. | Pass |

No constitutional violations or complexity exceptions are required.

## Project Structure

### Documentation (this feature)

```text
specs/004-dashboard-stack/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── dashboard-config.md
│   ├── http-proxy.md
│   └── mcp-services.md
├── checklists/
│   └── requirements.md
└── tasks.md              # Created by /speckit.tasks
```

### Source Code (repository root)

```text
apps/
├── kustomization.yaml                     # add `dashboard`
└── dashboard/
    ├── kustomization.yaml                 # resources + generated ConfigMaps
    ├── namespace.yaml                     # dashboard namespace
    ├── nginx.conf                         # Kubernetes-compatible frontend proxy config
    ├── mcp-host-rewrite.conf              # nginx sidecar for fly/weather MCP Host validation
    ├── validate-config.py                 # runtime config validator (also init container)
    ├── test_validate_config.py            # validator unit tests
    ├── config.example.json                # non-sensitive placeholder config
    ├── pvc.yaml                           # bus-catcher-data and procrastinator-data
    ├── bus-catcher-rest.yaml              # REST Deployment, Service
    ├── bus-catcher-mcp.yaml               # MCP Deployment, Service
    ├── fly-over-tracker-rest.yaml         # REST Deployment, Service
    ├── fly-over-tracker-mcp.yaml          # MCP Deployment, Service
    ├── procrastinator-tracker-rest.yaml   # REST Deployment, Service
    ├── procrastinator-tracker-mcp.yaml    # MCP Deployment, Service
    ├── weather-psychic-rest.yaml          # REST Deployment, Service
    ├── weather-psychic-mcp.yaml           # MCP Deployment, Service
    ├── frontend.yaml                      # nginx Deployment, Service, init validator
    └── tailscale-ingress.yaml             # dashboard.<tailnet>.ts.net

scripts/
├── create-dashboard-config-secret.sh     # validate JSON, create/update manual Secret
├── pull-dashboard-data.sh                # suspend Flux, stop writers, pull SQLite backup
├── restore-dashboard-data.sh             # verify and restore SQLite backup
└── validate.sh                           # add dashboard validator tests

docs/
├── 13-dashboard.md                       # new runbook
├── README.md                             # index entry
├── 07-secrets-and-unsynced-state.md      # dashboard-config Secret
├── 08-backups-and-recovery.md            # dashboard DB backups and restore
└── 09-limitations.md                     # dashboard limitations

README.md                                 # status, architecture, access, repo map
```

**Structure Decision**: The app follows the existing `apps/<name>/kustomization.yaml` pattern.
REST and MCP objects are split into separate files per module (`<module>-rest.yaml` and
`<module>-mcp.yaml`) so the P1 REST slice and the P2 MCP slice can be implemented and validated
independently. Shared PVCs live in `pvc.yaml`; the frontend, its Tailscale Ingress, and the generated
nginx/config-check ConfigMaps are separate. Separate Services and component selectors avoid routing
REST traffic to an MCP-only pod.

## Phase 0 Research

Research decisions and rejected alternatives are recorded in [research.md](research.md). The
critical outcomes are:

1. Nine separate Deployments, not four two-container pods, so REST and MCP have independent
   readiness and restart behavior. Each module gets separate `-rest` and `-mcp` Services selecting
   the matching component.
2. The bundled nginx configuration is replaced by `apps/dashboard/nginx.conf` through a generated
   ConfigMap. Static upstream Service names work with Kubernetes DNS and avoid Docker's
   `127.0.0.11` resolver.
3. The runtime JSON is a manual Secret. A Python init container validates it before nginx starts,
   because the dashboard's `loadConfig()` silently falls back to built-in defaults on any failure.
4. The frontend is reachable only through a Tailscale Ingress; REST and MCP Services remain
   ClusterIP. The four MCP URLs are documented for the agent repository.
5. Bus-catcher and procrastinator-tracker use one PVC each, shared by their REST and MCP pods on the
   single node. Backups use a maintenance-window stop-copy-start procedure; online SQLite backup is
   deferred because it adds tooling and has no v1 requirement.
6. The dashboard GHCR package is currently not anonymously pullable. The supported path is to make
   the package public; a documented `ghcr-pull` Secret is the fallback.
7. The fly-over and weather MCP servers use the Hono MCP helper's localhost Host validation. Each
   gets an nginx `host-rewrite` sidecar that listens on 3001, proxies to the MCP process on
   `127.0.0.1:3002`, and sets `Host: localhost` plus a localhost Origin. The Service contract stays
   `<module>-mcp...:3001/mcp`.

## Phase 1 Design Outputs

- [data-model.md](data-model.md): runtime entities, config schema, module matrix, storage, Services,
  ingress, image pins, and resource limits.
- [contracts/http-proxy.md](contracts/http-proxy.md): public frontend routes, internal upstreams,
  rewrite rules, health paths, and smoke calls.
- [contracts/mcp-services.md](contracts/mcp-services.md): internal MCP URLs, commands, ports,
  session caveat, and cross-namespace access.
- [contracts/dashboard-config.md](contracts/dashboard-config.md): required JSON fields, validation
  rules, Secret shape, and placeholder example.
- [quickstart.md](quickstart.md): deploy, configure, verify, first-run, backup/restore, and recovery
  validation scenarios.

## Post-Design Constitution Re-check

| Gate | Result |
| ---- | ------ |
| GitOps source of truth | Pass: all manifests and generated ConfigMaps are in `apps/dashboard`; Secrets and database backups are documented manual state. |
| Public repositories, private state | Pass: the config Secret is external; the example config uses zeroed placeholders; no real coordinates or stop IDs in the plan or manifests. |
| Recoverability | Pass: two PVCs, stop-copy backup/restore scripts, and node-reboot verification. |
| Reviewable, validated changes | Pass: one app Kustomization, per-module files, pinned images, no image automation, expanded validation. |
| Repository boundaries | Pass: only published images are consumed; no dashboard or module source changes. |

## Complexity Tracking

No constitutional violations. The only intentional complexity is a second Service per stateful
module so REST and MCP endpoints remain independently routable; a single shared Service would send
REST traffic to MCP-only pods and was rejected.
