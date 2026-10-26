---
description: "Task list for the dashboard stack on k3s"
---

# Tasks: Dashboard Stack on k3s

**Input**: Design documents from `/specs/004-dashboard-stack/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Validator unit tests are required by the specification's validation requirements. Cluster
smoke, backup/restore, and recovery checks are manual tasks tied to the quickstart. No application
code is built in this repository.

**Organization**: Tasks are grouped by user story. US1 delivers the dashboard and REST APIs, US2
adds the MCP servers, and US3 covers backups, recovery, updates, and documentation.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no incomplete dependencies)
- **[Story]**: US1, US2, or US3 for story phases only
- Every task includes an exact repository-relative file path

## Path Conventions

- App manifests: `apps/dashboard/`
- Shared scripts: `scripts/`
- Documentation: `docs/`
- Feature design and runbooks: `specs/004-dashboard-stack/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the app skeleton and the shared runtime-config validator.

- [X] T001 Create `apps/dashboard/namespace.yaml` with namespace `dashboard` and label `app.kubernetes.io/part-of: home-sweet-lab`; create the `apps/dashboard/` directory without registering it in `apps/kustomization.yaml` yet.
- [X] T002 [P] Create `apps/dashboard/config.example.json` with the non-sensitive placeholder config from `specs/004-dashboard-stack/contracts/dashboard-config.md` (zero coordinates, empty stops, `Placeholder` location, `UTC`).
- [X] T003 [P] Implement `apps/dashboard/validate-config.py` with the required-field, type, enum, range, and unknown-key behavior in `specs/004-dashboard-stack/contracts/dashboard-config.md`; accept the JSON path as a CLI argument, print only the failing path/reason, and exit non-zero on failure.
- [X] T004 Add `apps/dashboard/test_validate_config.py` covering a valid example, invalid JSON, a non-object root, missing `flights.location`, missing `weather.location`, invalid stop fields, and valid empty `bus.stops`; use `config.example.json` as a fixture.
- [X] T005 Update `scripts/validate.sh` to run `python3 -m unittest discover -s apps/dashboard -p 'test_*.py'` alongside the existing host-metrics tests.

**Checkpoint**: The validator and its tests exist; the app is not yet deployable.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared storage, proxy configuration, and the manual Secret workflow needed before any
story can be deployed.

**⚠️ CRITICAL**: Complete this phase before deploying US1 or US2.

- [X] T006 [P] Create `apps/dashboard/pvc.yaml` with `bus-catcher-data` at 10 GiB and `procrastinator-data` at 1 GiB, `ReadWriteOnce`, `storageClassName: local-path`, namespace `dashboard`.
- [X] T007 Create `scripts/create-dashboard-config-secret.sh`: create the `dashboard` namespace if absent, validate the input with `apps/dashboard/validate-config.py`, and create/update the `dashboard-config` Secret from `config.json` without printing values; support a path argument and fail safely.
- [X] T008 [P] Create `apps/dashboard/nginx.conf` with the four same-origin routes in `specs/004-dashboard-stack/contracts/http-proxy.md`: static upstreams `bus-catcher-rest:3000`, `procrastinator-tracker-rest:3000`, `fly-over-tracker-rest:3000`, `weather-psychic-rest:3000`; strip `/api/<module>`; no Docker `127.0.0.11` resolver; serve the SPA and `/config.json` with `Cache-Control: no-store`; set the documented proxy headers and timeouts.

**Checkpoint**: PVCs, proxy config, and the Secret workflow are ready; user stories can begin.

---

## Phase 3: User Story 1 - Run the dashboard and its REST backends (Priority: P1) 🎯 MVP

**Goal**: Deploy the frontend, four REST APIs, PVCs, runtime config Secret, and Tailscale ingress;
the browser shows the configured dashboard and reaches APIs only through the same-origin proxy.

**Independent Test**: Reconcile US1 alone, open `https://dashboard.<tailnet>.ts.net/`, confirm the
dashboard shell and configured blocks load, and confirm all four `/api/<module>/` health routes
reach their backends. No MCP client is required.

### Implementation for User Story 1

- [X] T009 [P] [US1] Create `apps/dashboard/bus-catcher-rest.yaml` with Deployment `bus-catcher-rest` (image `ghcr.io/sousa99/bus-catcher-backend:0.2.0`, command `node dist/index.js --http`, env `PORT=3000`/`MCP_PORT=3001`/`DB_PATH=/data/bus-catcher.db`, volume `bus-catcher-data` at `/data`, `/api/health` probes, component label `rest`, `Recreate`, bus-specific resource limits 250m/512Mi to 2/10Gi from data-model.md) and ClusterIP Service `bus-catcher-rest:3000`.
- [X] T010 [P] [US1] Create `apps/dashboard/fly-over-tracker-rest.yaml` with Deployment `fly-over-tracker-rest` (image `ghcr.io/sousa99/fly-over-tracker-backend:0.5.0`, command `node dist/index.js --http`, env `HOST=0.0.0.0`/`PORT=3000`/`MCP_PORT=3001`/`SNAPSHOT_CACHE_TTL_MS=60000`, TCP 3000 probes, component label `rest`, `Recreate`, resource limits) and ClusterIP Service `fly-over-tracker-rest:3000`.
- [X] T011 [P] [US1] Create `apps/dashboard/procrastinator-tracker-rest.yaml` with Deployment `procrastinator-tracker-rest` (image `ghcr.io/sousa99/procrastinator-tracker-backend:0.2.0`, command `sh -c 'node dist/migrate.js && node dist/index.js --http'`, env `PORT=3000`/`MCP_PORT=3001`/`DATABASE_URL=/data/procrastinator.db`, volume `procrastinator-data` at `/data`, `/health` probes, component label `rest`, `Recreate`, resource limits) and ClusterIP Service `procrastinator-tracker-rest:3000`.
- [X] T012 [P] [US1] Create `apps/dashboard/weather-psychic-rest.yaml` with Deployment `weather-psychic-rest` (image `ghcr.io/sousa99/weather-psychic-backend:0.1.0`, command `node dist/index.js --http`, env `HOST=0.0.0.0`/`PORT=3000`/`MCP_PORT=3001`, `/api/health` probes, component label `rest`, `Recreate`, resource limits) and ClusterIP Service `weather-psychic-rest:3000`.
- [X] T013 [P] [US1] Create `apps/dashboard/frontend.yaml` with Deployment `dashboard` (image `ghcr.io/sousa99/home-sweet-home-dashboard:0.1.0`, init container `validate-config` using `python:3.12-alpine@sha256:b658b05ce9c4eb97ec6fc19424818a1f31993659c2b505a532f470e83807815d` and `/check/validate-config.py /config/config.json`, nginx config mount from generated `dashboard-nginx`, `dashboard-config` Secret mount at `/usr/share/nginx/html/config.json`, HTTP `/` probes, `RollingUpdate`, resource limits) and ClusterIP Service `dashboard:80`.
- [X] T014 [P] [US1] Create `apps/dashboard/tailscale-ingress.yaml` named `dashboard`, class `tailscale`, backend `dashboard:80`, TLS host `dashboard`; do not add a Traefik ingress.
- [X] T015 [US1] Create `apps/dashboard/kustomization.yaml` with namespace `dashboard`, resources `namespace.yaml`, `pvc.yaml`, the four REST files, `frontend.yaml`, and `tailscale-ingress.yaml`, plus `configMapGenerator` entries for `dashboard-nginx` from `nginx.conf` and `dashboard-config-check` from `validate-config.py`; add `dashboard` to `apps/kustomization.yaml`.
- [X] T016 [US1] Run `./scripts/validate.sh` from the repository root and fix any render, schema, lint, unit-test, or secret-scan failure caused by the US1 manifests.
- [X] T017 [US1] Resolve dashboard image pullability per `specs/004-dashboard-stack/research.md` R6: verify `ghcr.io/sousa99/home-sweet-home-dashboard:0.1.0` pulls anonymously; if it does not, make the package public or create a `ghcr-pull` Secret and add the imagePullSecrets reference to `apps/dashboard/frontend.yaml`; record the chosen path in `docs/13-dashboard.md`.
- [X] T018 [US1] Create the real `dashboard-config` Secret from an external, validated JSON file using `scripts/create-dashboard-config-secret.sh`; if the frontend pod was waiting, delete it and confirm the init container accepts the file.
- [X] T019 [US1] Reconcile Flux and verify US1 per `specs/004-dashboard-stack/quickstart.md` sections 3–4: the five US1 Deployments (frontend plus four REST) Ready, both PVCs Bound, Ingress has a Tailscale hostname, the HTTPS page returns `200`, all four `/api/<module>/` health routes work, and no REST Service is externally exposed.
- [X] T020 [US1] Run the first bus GTFS ingest through `POST /api/bus/api/refresh`, verify departures for a configured stop, restart the bus REST pod, and confirm the data survives; record the result in `docs/13-dashboard.md`.
- [X] T021 [US1] Stop one REST backend, reload the dashboard, and verify only the affected block/status indicator degrades; restore the pod, confirm recovery, and record the result in `docs/13-dashboard.md`.
- [X] T022 [US1] Test runtime configuration: update the Secret with a valid change via `scripts/create-dashboard-config-secret.sh`, delete the frontend pod, confirm the new value is served; then test an invalid file and confirm the init container fails visibly without serving built-in defaults; record both outcomes in `docs/13-dashboard.md`.
- [X] T023 [US1] Create `docs/13-dashboard.md` with frontend/REST prerequisites, GHCR visibility, Secret creation, access URL, API routes, first-run bus ingest, verification commands, US1 failure behavior, and the current image pins; add the document to `docs/README.md`.

**Checkpoint**: US1 is independently deployable and provides the complete visible dashboard with
working REST APIs. MCP is not required.

---

## Phase 4: User Story 2 - Expose the four MCP servers to in-cluster consumers (Priority: P2)

**Goal**: Run the four MCP servers from the same pinned module images, expose four stable
cluster-internal `/mcp` Services, and document them for `home-sweet-home-agent`.

**Independent Test**: Reconcile US2, then send an MCP initialize request to all four
`<module>-mcp.dashboard.svc.cluster.local:3001/mcp` URLs from a pod in another namespace. No browser
or agent deployment is required.

### Implementation for User Story 2

- [X] T024 [P] [US2] Create `apps/dashboard/bus-catcher-mcp.yaml` with Deployment `bus-catcher-mcp` (image `ghcr.io/sousa99/bus-catcher-backend:0.2.0`, command `node dist/index.js --mcp`, env `PORT=3000`/`MCP_PORT=3001`/`DB_PATH=/data/bus-catcher.db`, volume `bus-catcher-data` at `/data`, TCP 3001 probes, component label `mcp`, `Recreate`, bus-specific 100m/256Mi to 1/1Gi limits) and ClusterIP Service `bus-catcher-mcp:3001`.
- [X] T025 [P] [US2] Create `apps/dashboard/fly-over-tracker-mcp.yaml` with Deployment `fly-over-tracker-mcp` (image `ghcr.io/sousa99/fly-over-tracker-backend:0.5.0`, command `node dist/index.js --mcp`, env `HOST=0.0.0.0`/`PORT=3000`/`MCP_PORT=3002`, TCP 3002 probes) plus an nginx `host-rewrite` sidecar on 3001 using `apps/dashboard/mcp-host-rewrite.conf` to set `Host: localhost`, component label `mcp`, `Recreate`, resource limits, and ClusterIP Service `fly-over-tracker-mcp:3001` targeting `mcp-proxy`.
- [X] T026 [P] [US2] Create `apps/dashboard/procrastinator-tracker-mcp.yaml` with Deployment `procrastinator-tracker-mcp` (image `ghcr.io/sousa99/procrastinator-tracker-backend:0.2.0`, command `sh -c 'node dist/migrate.js && node dist/index.js --mcp'`, env `PORT=3000`/`MCP_PORT=3001`/`DATABASE_URL=/data/procrastinator.db`, volume `procrastinator-data` at `/data`, TCP 3001 probes, component label `mcp`, `Recreate`, resource limits) and ClusterIP Service `procrastinator-tracker-mcp:3001`.
- [X] T027 [P] [US2] Create `apps/dashboard/weather-psychic-mcp.yaml` with Deployment `weather-psychic-mcp` (image `ghcr.io/sousa99/weather-psychic-backend:0.1.0`, command `node dist/index.js --mcp`, env `HOST=0.0.0.0`/`PORT=3000`/`MCP_PORT=3002`, TCP 3002 probes) plus an nginx `host-rewrite` sidecar on 3001 using `apps/dashboard/mcp-host-rewrite.conf` to set `Host: localhost`, component label `mcp`, `Recreate`, resource limits, and ClusterIP Service `weather-psychic-mcp:3001` targeting `mcp-proxy`.
- [X] T028 [US2] Add the four MCP files to `apps/dashboard/kustomization.yaml`.
- [X] T029 [US2] Run `./scripts/validate.sh`, reconcile Flux, and verify all four MCP Deployments and Services are Ready, all MCP endpoints are `ClusterIP`, and none have an Ingress, Tailscale host, NodePort, or LoadBalancer.
- [X] T030 [P] [US2] From a pod in another namespace, send an MCP initialize request to all four URLs in `specs/004-dashboard-stack/contracts/mcp-services.md`; record the exact URLs and expected response in `docs/13-dashboard.md`.
- [X] T031 [P] [US2] Exercise bus-catcher and procrastinator MCP operations that read or write data, then verify the same result through the REST API and the dashboard's next refresh; document the consistency result in `docs/13-dashboard.md`.
- [X] T032 [P] [US2] Disconnect and reconnect a procrastinator MCP client, restart the MCP pod if needed, and verify the task data survives; document the single-session caveat and restart command in `docs/13-dashboard.md` per `specs/004-dashboard-stack/contracts/mcp-services.md`.
- [X] T033 [US2] Add the MCP section to `docs/13-dashboard.md`: URLs, port-forward debugging, single-session behavior, cross-namespace smoke command, and failure behavior.

**Checkpoint**: US1 and US2 work independently; the agent owns consumption but has stable endpoints.

---

## Phase 5: User Story 3 - Operate, back up, and recover the dashboard stack (Priority: P3)

**Goal**: Provide safe SQLite backup/restore, node-reboot recovery, failure diagnosis, documented
version pins, and rollback so the stack is recoverable on the single node.

**Independent Test**: Delete pods, restore a database backup into the PVCs, reboot the node, and
follow the docs for an image-pull failure and a bad module version. Each drill finishes without
manual manifest edits.

### Implementation for User Story 3

- [X] T034 [P] [US3] Create `scripts/pull-dashboard-data.sh`: validate prerequisites, suspend the `apps` Flux Kustomization, scale the four stateful module Deployments to zero, run a temporary pinned `python:3.12-alpine` helper pod that archives both PVCs with SHA-256, copy the archive to `~/backups/home-sweet-lab/dashboard/<timestamp>/`, scale back, resume Flux, and use a trap so Flux/replicas are restored on failure.
- [X] T035 [P] [US3] Create `scripts/restore-dashboard-data.sh`: suspend Flux, stop the stateful writers, verify the archive checksum, extract into `bus-catcher-data` and `procrastinator-data`, restore replicas, resume Flux, and reflect the data in the dashboard/MCP.
- [X] T036 [US3] Run the backup and restore drill per `specs/004-dashboard-stack/quickstart.md` section 7: verify checksum, both databases, dashboard data, MCP reads, PVC binding, and a resumed Flux Kustomization; record the drill date and result.
- [X] T037 [P] [US3] Update `docs/07-secrets-and-unsynced-state.md` with the `dashboard-config` Secret (purpose, creation, rotation, rebuild prerequisite) and the optional `ghcr-pull` fallback.
- [X] T038 [US3] Update `docs/08-backups-and-recovery.md` with the dashboard SQLite backup asset, pull/restore commands, retention, checksum requirement, and the verified drill result.
- [X] T039 [P] [US3] Update `docs/09-limitations.md` with dashboard-specific limitations: Tailscale-only access, no REST/MCP external exposure, single node and local-path data, image visibility, module version skew, MCP single-session, config restart, and no automated offsite backup.
- [X] T040 [US3] Add recovery, update, rollback, and version-pin sections to `docs/13-dashboard.md`: pod loss, config failure, image-pull failure, provider outage, Service recreation, node reboot, per-module pin update, and Git revert rollback.
- [X] T041 [US3] Run the recovery drills in `specs/004-dashboard-stack/quickstart.md` section 8 for pod deletion, missing/invalid config, image-pull failure, external provider outage, and Service recreation; record results in `docs/13-dashboard.md`.
- [ ] T042 [US3] Run the node-reboot drill: reboot `dietpi`, wait for k3s and Flux, verify all nine Deployments, both PVCs, the dashboard URL, all four MCP URLs, and bus/task data; record the result in `docs/13-dashboard.md`.
- [X] T043 [US3] Update `README.md` status, architecture table, access section, repository map, and non-goals to include the dashboard stack and its frontend/REST/MCP split.
- [X] T044 [P] [US3] Update `docs/README.md` with the `13-dashboard.md` status and index entry, and link the dashboard runbook from the relevant secret/backup/limitations documents.

**Checkpoint**: Backups, restore, node recovery, updates, and rollback are documented and exercised.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final consistency, security, and end-to-end validation.

- [X] T045 Review every `apps/dashboard/*.yaml` manifest for pinned images, correct component selectors, `Recreate` on stateful modules, resource limits, no external REST/MCP exposure, no service-account token, and least-privilege security contexts; fix issues in the affected manifests.
- [X] T046 Run `./scripts/validate.sh` from the repository root; confirm Kustomize render, `kubeconform`, `yamllint`, the dashboard validator tests, and `gitleaks` all pass.
- [ ] T047 Run `specs/004-dashboard-stack/quickstart.md` end-to-end on the real cluster, including the final acceptance checklist; record any deviation and fix the runbook or manifests.
- [X] T048 [P] Scan Git for real tailnet identifiers, household coordinates, stop IDs, credentials, SQLite files, and backup archives; confirm `.gitignore` covers `backups/`, `bundles/`, and `secrets/`, and that `apps/dashboard/config.example.json` contains only placeholders.
- [X] T049 [P] Verify `specs/004-dashboard-stack/spec.md` and `specs/004-dashboard-stack/plan.md` are consistent with `docs/13-dashboard.md`: nine Deployments, nine Services, two PVCs, one Tailscale Ingress, no image automation, no direct REST/MCP ingress, and all functional requirements covered by tasks or documentation.

---

## Implementation Status (2026-10-26)

Completed locally: T001–T016, T023–T028, T033–T035, T037–T040, T043–T046, T048–T049.

Remaining: T042 (node reboot) and T047 (end-to-end quickstart). T017, T019, T021, T022, and T041
are complete; the package is public, the frontend is live, and the failure drills passed.

The repository artifacts pass `./scripts/validate.sh`, `kubectl apply --dry-run=server`, nginx
configuration syntax validation, and the Python validator tests. The app was reconciled by Flux;
all eight module pods are Ready. The frontend pod is waiting on the private dashboard image. Live
verification found that fly-over and weather MCP reject the Kubernetes Service Host header, so both
now use the nginx `host-rewrite` sidecar documented in `research.md` R12. All four REST health
checks and all four MCP initialize calls pass from the `home-assistant` namespace. The first GTFS
attempts OOMKilled `bus-catcher-rest` at 512Mi and 2Gi; its limit is now 10Gi, the bus PVC is 10Gi, and
the ingest is being re-run.

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; can start immediately.
- **Foundational (Phase 2)**: Depends on Setup; blocks both US1 and US2.
- **US1 (Phase 3)**: Depends on Foundational. It is the dashboard MVP.
- **US2 (Phase 4)**: Manifests and initialize tests can start after Foundational; the data-consistency
  test (T031) depends on US1 REST. The planned order is US1 then US2.
- **US3 (Phase 5)**: Depends on US1 and US2 for meaningful backup, MCP, and recovery drills.
- **Polish (Phase 6)**: Depends on all desired stories.

### User Story Dependencies

- **US1**: No dependency on US2; independently deployable and testable.
- **US2**: The MCP endpoints are independently testable after Foundational; T031 integrates with US1.
- **US3**: Needs US1 and US2 because it backs up and recovers their data and verifies MCP after a
  reboot.

### Within Each User Story

- Manifest files are created in parallel where they are separate files.
- The Kustomization is updated after its resources exist.
- Validation precedes reconciliation.
- Cluster verification and documentation follow the working deployment.
- Tests/checks must pass before the next story is considered complete.

### Parallel Opportunities

- Setup: T002 and T003 are independent files.
- Foundational: T006 and T008 are independent; T007 depends on the validator contract.
- US1: T009–T014 are separate manifest files and can be written in parallel; T015+ depend on them.
- US2: T024–T027 are separate manifest files and can be written in parallel; T030–T032 can run in
  parallel after T029.
- US3: T034/T035 are separate scripts; T037 and T039 are separate docs; T044 is a separate doc.
- Polish: T048 and T049 are independent checks.

---

## Parallel Example: User Story 1

```text
Task: "Create apps/dashboard/bus-catcher-rest.yaml"
Task: "Create apps/dashboard/fly-over-tracker-rest.yaml"
Task: "Create apps/dashboard/procrastinator-tracker-rest.yaml"
Task: "Create apps/dashboard/weather-psychic-rest.yaml"
Task: "Create apps/dashboard/frontend.yaml"
Task: "Create apps/dashboard/tailscale-ingress.yaml"
```

## Parallel Example: User Story 2

```text
Task: "Create apps/dashboard/bus-catcher-mcp.yaml"
Task: "Create apps/dashboard/fly-over-tracker-mcp.yaml"
Task: "Create apps/dashboard/procrastinator-tracker-mcp.yaml"
Task: "Create apps/dashboard/weather-psychic-mcp.yaml"
```

## Parallel Example: User Story 3

```text
Task: "Create scripts/pull-dashboard-data.sh"
Task: "Create scripts/restore-dashboard-data.sh"
Task: "Update docs/07-secrets-and-unsynced-state.md"
Task: "Update docs/09-limitations.md"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup).
2. Complete Phase 2 (Foundational).
3. Complete Phase 3 (US1).
4. **STOP and VALIDATE**: Reconcile, open the Tailscale dashboard, verify all four REST routes, run
   the bus ingest, and confirm a pod restart preserves data.
5. Deploy/demo the dashboard without MCP.

### Incremental Delivery

1. Setup + Foundational → validator, PVCs, proxy config, Secret workflow ready.
2. US1 → visible dashboard + REST APIs (MVP).
3. US2 → four cluster-internal MCP endpoints for the agent.
4. US3 → backups, restore, node recovery, updates, rollback, and runbooks.
5. Polish → final validation and acceptance.

### Notes

- Do not commit the real `config.json`, GHCR token, SQLite files, or backups.
- Keep image pins in Git; update one module at a time and verify before moving to the next.
- Do not add image automation or direct REST/MCP ingress.
- A manual `kubectl` scale or Flux suspend is limited to the documented backup/restore window; the
  scripts must resume Flux and restore replicas.
