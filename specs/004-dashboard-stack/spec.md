# Feature Specification: Dashboard Stack on k3s

**Feature Branch**: `main`

**Created**: 2026-10-26

**Status**: Draft

**Input**: Integrate `home-sweet-home-dashboard` into the cluster: run the four module REST APIs, the
four module MCP servers, and the dashboard frontend itself on the DietPi node, managed by Flux.

## Clarifications

### Session 2026-10-26

- Q: How should the dashboard frontend be reachable? → A: Tailscale only, at
  `https://dashboard.<tailnet>.ts.net/`, following the Home Assistant ingress pattern.
- Q: How should the four MCP servers be reachable? → A: Cluster-internal only, for
  `home-sweet-home-agent` and other in-cluster consumers; `kubectl port-forward` is the documented
  debugging path. No Tailscale ingress for MCP.
- Q: Should browser clients reach the module REST APIs directly? → A: No. The browser uses the
  dashboard's same-origin `/api/<module>/` routes; the frontend proxies to the REST Services, which
  remain cluster-internal. Only the dashboard is exposed over Tailscale.

## User Scenarios & Testing

### User Story 1 - Run the dashboard and its REST backends (Priority: P1)

The household operator merges dashboard manifests and Flux reconciles the dashboard frontend plus
the four module REST backends into the cluster. The TV/large-screen browser opens the dashboard over
Tailscale and sees the clock, flights, weather, tasks, bus stops, and per-module status. Widget
requests are proxied same-origin to the module APIs.

**Why this priority**: This is the visible household value and the minimum viable integration.
Without the frontend and REST APIs, the MCP servers have no data source and the dashboard cannot be
evaluated.

**Independent Test**: Reconcile from Git, open the dashboard URL from a tailnet device, confirm every
configured block renders live data, and confirm each `/api/<module>/` route reaches its backend. No
MCP client or agent deployment is required.

**Acceptance Scenarios**:

1. **Given** the dashboard manifests are merged to the tracked branch, **When** Flux reconciles,
   **Then** the dashboard namespace contains the frontend, four REST backends, Services, PVCs, the
   runtime configuration, and the Tailscale Ingress, and all workloads are Ready on `dietpi`.
2. **Given** the workloads are Ready, **When** a tailnet device requests
   `https://dashboard.<tailnet>.ts.net/`, **Then** the response is HTTPS `200` and the dashboard
   shell loads with no console errors caused by missing backend routes.
3. **Given** the dashboard is loaded, **When** the enabled blocks render, **Then** the clock,
   closest-flight panel, flight map, weather, task deck, configured bus stop cards, and status strip
   display data or a clearly unavailable state.
4. **Given** a widget requests `/api/bus/`, `/api/tasks/`, `/api/fly/`, or `/api/weather/`, **When**
   the reverse proxy forwards the request, **Then** it reaches the matching REST backend without
   CORS errors, Docker-only DNS assumptions, or stale upstream addresses, using only the dashboard
   hostname.
5. **Given** a bus refresh is triggered, **When** the ingest completes, **Then** departures for the
   configured stops appear and persist across a backend pod restart.
6. **Given** a task is created through the tasks REST API, **When** the dashboard refreshes, **Then**
   the task appears and survives a backend pod restart.
7. **Given** one backend is stopped, **When** the dashboard is reloaded, **Then** the frontend still
   loads and only the affected block reports unavailable; the remaining blocks continue to work.
8. **Given** the household configuration changes, **When** the operator updates the runtime
   configuration and restarts the frontend pod, **Then** the dashboard reflects the change without
   rebuilding or republishing any image.

---

### User Story 2 - Expose the four MCP servers to in-cluster consumers (Priority: P2)

The four module MCP servers run from the same published module images in MCP mode. Each exposes a
stable cluster-internal `/mcp` endpoint that `home-sweet-home-agent` can consume. Bus and task MCP
operations read and write the same data as their REST counterparts.

**Why this priority**: The MCP servers are the agent-facing half of the integration. They add value
only after the backends and data storage are working, and they are independent of the dashboard UI.

**Independent Test**: From a pod in another namespace, request each MCP Service and complete a
representative MCP call (list bus departures, list tasks, fetch weather, fetch flights). No browser
or agent deployment is required.

**Acceptance Scenarios**:

1. **Given** the MCP workloads are reconciled, **When** their pods are Ready, **Then** four
   ClusterIP Services expose `/mcp` on a stable cluster DNS name and port.
2. **Given** a consumer pod in another namespace, **When** it resolves each documented MCP URL,
   **Then** the connection succeeds and the server responds to MCP requests.
3. **Given** bus or task data exists, **When** an MCP call reads or writes it, **Then** the result is
   consistent with the REST API and the dashboard's next refresh.
4. **Given** the MCP servers are running, **When** cluster exposure is inspected, **Then** there is
   no MCP Ingress, Tailscale host, load balancer, node port, host port, or host networking.
5. **Given** the procrastinator MCP server is single-session per container lifetime, **When** its
   client disconnects and cannot reconnect, **Then** the documented restart procedure restores the
   session without losing task data.
6. **Given** an MCP pod is deleted, **When** Kubernetes replaces it, **Then** the Service endpoint
   returns and the server recovers without manual reconfiguration.

---

### User Story 3 - Operate, back up, and recover the dashboard stack (Priority: P3)

The household operator can update module versions independently, back up and restore the SQLite
data, recover from pod and node failures, and diagnose configuration, image-pull, and upstream
dependency failures.

**Why this priority**: A single-node household service must be recoverable without a monitoring
stack. This protects the value delivered by P1 and P2 after the first failure or upgrade.

**Independent Test**: Delete pods, reboot the node, restore a database backup into a fresh PVC, and
follow the documentation for an unavailable image and a bad module version.

**Acceptance Scenarios**:

1. **Given** the dashboard stack is Ready, **When** the node reboots, **Then** Flux recreates all
   workloads, the dashboard returns `200`, the MCP Services resolve, and bus/task data is intact.
2. **Given** the bus or tasks PVC is lost, **When** the operator restores the latest documented
   backup, **Then** the database opens, the dashboard shows the restored data, and the restore is
   recorded.
3. **Given** a module image is unavailable or the dashboard GHCR package is private without a pull
   credential, **When** pods start, **Then** the failure is visible as `ImagePullBackOff` and the
   documented fix restores the stack without changing application code.
4. **Given** a module version is incompatible, **When** the operator reverts the per-module image pin
   and configuration, **Then** Flux reconciles the previous combination and the dashboard recovers.
5. **Given** the runtime configuration Secret is missing or invalid, **When** the frontend starts,
   **Then** the failure is visible and documented rather than silently serving the wrong household
   location or stops.
6. **Given** an external data provider is unreachable, **When** the dashboard refreshes, **Then**
   only the weather or flight block degrades; tasks, bus, clock, and backend health remain usable.

---

### Edge Cases

- The dashboard image's bundled nginx configuration expects Docker's embedded DNS resolver. In
  Kubernetes this breaks upstream resolution; the cluster must supply a Kubernetes-compatible
  proxy configuration, not rely on the image default.
- The dashboard GHCR package is not anonymously pullable while the module backend packages are.
  A missing pull credential must fail visibly and be documented.
- The runtime configuration contains the household location, bus stop IDs, and display choices. It
  must not enter Git, and its absence must not silently fall back to a different location.
- A single household configuration Secret is mounted over the image default; a partially written or
  invalid JSON file must be rejected visibly instead of rendering an empty dashboard.
- Bus and task SQLite databases are written by both REST and MCP processes. Concurrent access must
  not silently corrupt data or create divergent copies; the plan must choose a verified access
  model.
- The bus schedule starts empty until a one-off GTFS ingest runs. A failed or slow ingest must not
  make the dashboard unusable; the bus block degrades and the operator can retry.
- The tasks database starts empty; an empty deck is a valid state, not an error.
- Flights and weather depend on external providers. Provider outages, rate limits, or DNS failures
  must degrade only those blocks.
- The node's architecture must match the published backend images (`linux/amd64`). A mismatched or
  emulated node must be visible in pod state and documented.
- The single-session procrastinator MCP server loses its session after a client restart; the data
  must survive the container restart.
- A frontend replica restart during use causes a brief page reload; TV reconnection is acceptable.
- A backend crash leaves the dashboard shell available; the status strip or block indicates the
  failure.
- The node disk fills; SQLite writes fail, pods may be evicted, and the condition is documented with
  verification commands.
- Tailscale is down or an ACL denies the device; the frontend is unreachable but the workloads and
  MCP Services continue to operate inside the cluster.
- A module's frontend package and backend image are versioned independently; a mismatch may render
  or call APIs incorrectly. The version pins and rollback procedure must be documented.
- Home Assistant is also running on the node. Dashboard resource limits must prevent a runaway
  backend from starving Home Assistant.
- A manual `kubectl` change to a workload is reverted by Flux; manual edits are not a supported fix.

## Requirements

### Functional Requirements

- **FR-001**: The dashboard frontend, four REST backends, four MCP servers, namespace, Services,
  PVCs, runtime configuration, prose, and Flux reconciliation entry MUST live in this repository and
  be applied only through GitOps reconciliation.
- **FR-002**: The new app MUST be a self-contained `apps/dashboard` Kustomization and MUST be added
  to the existing `apps` Kustomization; the `apps` Flux Kustomization remains the delivery path.
- **FR-003**: The namespace MUST contain exactly the documented workloads: one frontend, four REST
  backends, and four MCP servers. The frontend and REST backends MUST run from published images;
  the MCP servers MUST run from the same published module images with their MCP command.
- **FR-004**: Every image MUST be pinned to an immutable version tag or digest. `latest` MUST NOT be
  used. Dashboard components and each module backend version MUST be independently documented and
  independently updatable.
- **FR-005**: Every image MUST be pullable by the cluster. Because the dashboard GHCR package is not
  currently anonymously pullable, the operator MUST resolve this by making the package public or by
  creating a documented image pull Secret; the failure mode MUST be documented.
- **FR-006**: The frontend MUST be served by a ClusterIP Service and exposed only through a Tailscale
  Ingress using the short hostname `dashboard`, with a Tailscale-issued TLS certificate. The
  documented URL is `https://dashboard.<tailnet>.ts.net/`.
- **FR-007**: The frontend MUST NOT be exposed through Traefik, a load balancer, a node port, a host
  port, or the public internet.
- **FR-008**: The frontend MUST proxy same-origin `/api/bus/`, `/api/tasks/`, `/api/fly/`, and
  `/api/weather/` requests to the matching REST Services. The proxy configuration MUST work under
  Kubernetes DNS and MUST NOT depend on Docker's `127.0.0.11` resolver. Browser clients MUST NOT
  require a separate REST API hostname or direct REST ingress.
- **FR-009**: The REST backends MUST each expose a ClusterIP Service on a stable name and port and
  MUST be reachable from the frontend by cluster DNS. They MUST NOT be externally exposed.
- **FR-010**: The four REST backends MUST provide the module HTTP APIs required by the dashboard:
  bus departures and GTFS refresh, tasks, flight snapshots, and weather.
- **FR-011**: The dashboard MUST be runtime-configurable for clock, bus stops, flight location and
  radius, task behavior, weather location, status polling, and placeholders. Changes MUST NOT
  require an image rebuild.
- **FR-012**: The runtime dashboard configuration MUST be supplied from a manually managed Kubernetes
  object, not committed to Git, because it contains household location and stop identifiers. The
  repository MUST document its schema, creation, update, backup, and validation.
- **FR-013**: A missing, unreadable, or invalid runtime configuration MUST fail visibly; the
  frontend MUST NOT silently substitute a different household location or stop list.
- **FR-014**: The frontend MUST remain available when an individual backend is down, and the
  affected block MUST show an unavailable state while unaffected blocks continue to update.
- **FR-015**: The frontend and every backend and MCP workload MUST define readiness and liveness
  probes appropriate to its process, plus CPU and memory requests and limits that protect Home
  Assistant and the node.
- **FR-016**: Bus-catcher and procrastinator-tracker data MUST persist in SQLite across pod
  replacement, rescheduling, and node reboot through a PersistentVolumeClaim on the default storage
  class.
- **FR-017**: The REST and MCP processes for bus-catcher and procrastinator-tracker MUST use the same
  underlying data. The plan MUST choose and verify an access model that avoids silent divergence or
  corruption from concurrent writers.
- **FR-018**: Fly-over-tracker and weather-psychic are stateless and MUST NOT receive a
  PersistentVolumeClaim.
- **FR-019**: The repository MUST document a consistent backup and restore procedure for the
  dashboard SQLite databases, including where the live copy lives, where backups are pulled, how
  integrity is verified, and how restore is exercised. Database files and backups MUST NOT enter
  Git.
- **FR-020**: The four MCP servers MUST expose streamable HTTP MCP endpoints at `/mcp` through four
  ClusterIP Services with stable cluster DNS names and documented ports.
- **FR-021**: The MCP Services MUST be reachable from other cluster namespaces for
  `home-sweet-home-agent` and other in-cluster consumers. The exact URLs MUST be documented for that
  repository.
- **FR-022**: The MCP servers MUST NOT be exposed through any Ingress, Tailscale host, load balancer,
  node port, host port, or public endpoint. Local debugging MUST use documented `kubectl
  port-forward` commands.
- **FR-023**: MCP read and write operations for bus and tasks MUST be consistent with the REST APIs
  and the dashboard. The single-session behavior of the procrastinator MCP server MUST be documented
  with a restart and reconnect procedure that preserves data.
- **FR-024**: Every workload MUST recover automatically after pod deletion, backend crash, Flux
  reconciliation, and node reboot without manual `kubectl apply`.
- **FR-025**: The feature MUST document the first-run data steps: a one-off bus GTFS ingest, adding
  configured stops, verifying departures, and the empty-but-valid initial task state.
- **FR-026**: The feature MUST document external data dependencies: the GTFS source, the live flight
  feed, and the keyless weather provider, including their purpose, failure behavior, and local
  degradation.
- **FR-027**: The feature MUST document the observed deployment, access, data, MCP, update, backup,
  restore, and recovery procedures in a new `docs/` document, add it to the documentation index,
  and update the README architecture, status, repository map, and related-repository sections.
- **FR-028**: The feature MUST update the limitations document to state that the dashboard stack is
  now migrated, and to record the new single-node, storage, access, image, version-skew, and MCP
  session limitations.
- **FR-029**: Manifest validation MUST cover the new app: rendered Kustomization, Kubernetes schema
  validation, YAML linting, and secret scanning must pass before merge.
- **FR-030**: The feature MUST NOT modify the `home-sweet-home-dashboard` repository, the module
  repositories, the Home Assistant configuration repository, or their published images. Any
  cluster-specific nginx or runtime configuration MUST be supplied by this repository.
- **FR-031**: The feature MUST NOT deploy `home-sweet-home-agent`, LLM calls, conversation
  orchestration, or MCP authorization. It provides stable endpoints for that separate repository.
- **FR-032**: The feature MUST NOT add public internet exposure, SSO, dashboard authentication, MCP
  authentication, automated offsite backups, high availability, multi-node scheduling, or replicated
  storage.
- **FR-033**: The feature MUST NOT commit real tailnet names or addresses, household coordinates,
  bus stop identifiers, credentials, tokens, database files, or backup archives. Documentation uses
  placeholders such as `<tailnet>`.
- **FR-034**: The version matrix MUST record the pinned dashboard image, each MCP/REST backend image,
  each embedded components package, and the compatibility/rollback expectations. Rollback MUST be a
  Git revert of the pins.
- **FR-035**: The dashboard stack MUST define resource requests and limits such that a runaway
  backend or MCP process cannot starve Home Assistant or the single node; actual usage and available
  node capacity MUST be verified during deployment.

### Key Entities

- **Dashboard frontend**: The nginx-served single-page application and same-origin API proxy exposed
  through Tailscale.
- **Module REST backend**: One of four module HTTP services that owns module data or fetches external
  data.
- **Module MCP server**: One of four streamable HTTP MCP services consumed inside the cluster.
- **Module database**: The SQLite file for bus-catcher or procrastinator-tracker, persisted on a
  PVC and shared by REST and MCP access paths.
- **Runtime dashboard configuration**: The JSON document with clock, stops, locations, task and
  status behavior; supplied manually and never committed.
- **Dashboard PVC**: The local-path volume holding the SQLite databases.
- **Tailscale Ingress**: The single external access path for the dashboard, using the short hostname
  `dashboard`.
- **MCP Service endpoint**: The stable cluster-internal URL that the agent repository consumes.
- **Image pin matrix**: The documented per-component image tags and dashboard package versions.
- **Dashboard backup**: The pulled and checksum-verified copy of the SQLite databases used for
  restore.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A merged dashboard change produces a working dashboard within 10 minutes, with no
  manual deployment commands.
- **SC-002**: Household viewers can open the dashboard from a tailnet device and receive a
  successful page load within 5 seconds on 100% of 10 consecutive attempts.
- **SC-003**: The dashboard displays live data for all enabled blocks: clock, flights closest and
  map, weather, tasks, every configured bus stop, and the status strip.
- **SC-004**: All four `/api/<module>/` routes work through the frontend for 100% of the documented
  smoke calls, with no CORS errors and no `502` caused by upstream resolution.
- **SC-005**: A runtime configuration change is visible in the dashboard within 5 minutes of the
  operator update and one frontend pod restart, with no image rebuild.
- **SC-006**: All four MCP endpoints respond from another in-cluster consumer within 5 seconds,
  using only the documented URLs.
- **SC-007**: A task or bus data change made through an MCP call is visible in the REST API and on
  the dashboard's next refresh, and survives a pod restart.
- **SC-008**: After deliberate deletion of any dashboard-stack pod, the affected capability is
  available again within 2 minutes without operator action.
- **SC-009**: After a full node restart, the dashboard is usable, all four MCP endpoints respond,
  and bus/task data is intact within 10 minutes of the cluster returning.
- **SC-010**: An external access audit finds exactly one remote entry point for the dashboard and
  none for the REST or MCP services.
- **SC-011**: Secret and repository scanning find zero committed credentials, remote-access
  identifiers, household locations, stop identifiers, database files, or backup archives.
- **SC-012**: A backup/restore drill restores both SQLite databases into a fresh PVC, passes an
  integrity check, and leaves the dashboard and MCP reads working; the drill date and result are
  recorded.
- **SC-013**: The bus GTFS first-run ingest completes and departures appear for configured stops;
  a failed ingest leaves the bus block unavailable without breaking other blocks.
- **SC-014**: A per-module rollback restores the previous working dashboard/backend combination
  within 10 minutes using only committed changes.
- **SC-015**: During normal dashboard use, Home Assistant remains available and the node shows no
  memory pressure or workload evictions.

## Out of Scope

- Deploying or configuring `home-sweet-home-agent`, LLM calls, conversation behavior, or MCP
  authorization.
- Changes to `home-sweet-home-dashboard`, the module repositories, their images, or their published
  packages.
- Changes to Home Assistant configuration or adding dashboard entities to Home Assistant.
- Public internet exposure, DNS names, cert-manager, SSO, dashboard authentication, or MCP
  authentication.
- Exposing REST APIs or MCP servers through Traefik, Tailscale, or any external endpoint.
- High availability, multiple replicas for stateful modules, replicated storage, snapshots, or
  automated offsite backups.
- Automated image updates for the dashboard stack; pins are updated deliberately per module.
- Automated GTFS ingestion, task seeding, or weather/flight provider fallbacks beyond what the
  published modules already implement.
- Fixing upstream module bugs, module API version skew, or changing the dashboard's layout and
  widgets.

## Dependencies

- A healthy single-node k3s cluster on `dietpi` with Flux reconciling this repository.
- The Tailscale Kubernetes Operator, an existing `operator-oauth` Secret, HTTPS enabled, and
  tailnet ACLs that allow household devices to reach `tag:k8s` port 443.
- Published images: `ghcr.io/sousa99/home-sweet-home-dashboard` plus the bus-catcher,
  fly-over-tracker, procrastinator-tracker, and weather-psychic backend images.
- Pull access to the dashboard GHCR package, either by making it public or by creating a manual
  image pull Secret.
- The published module images are `linux/amd64`; the DietPi node must match or emulation must be
  explicitly accepted.
- A manually created runtime configuration Secret containing the household dashboard JSON.
- `local-path` storage for the bus and task SQLite databases.
- Outbound internet access for GTFS ingest, live flight data, and weather.
- The separate `home-sweet-home-agent` repository consuming the documented MCP URLs.

## Assumptions

- The dashboard runs in a new `dashboard` namespace, the frontend Service is named `dashboard`, and
  the Tailscale hostname is `dashboard.<tailnet>.ts.net`.
- The dashboard image is consumed unmodified. Because its bundled nginx configuration targets Docker
  Compose, a cluster-specific proxy configuration is supplied by this repository through a
  ConfigMap or equivalent mount.
- The four REST backends and four MCP servers map one-to-one to the four modules. The frontend-only
  current-time module has no backend.
- Bus-catcher and procrastinator-tracker are the only stateful modules. Fly-over-tracker and
  weather-psychic are stateless and depend on external providers.
- Bus and task REST/MCP processes can safely share a single SQLite data volume when run in the same
  pod or otherwise coordinated; the plan verifies this rather than assuming it.
- The household configuration is sensitive because it reveals location and travel habits; a manual
  Kubernetes Secret is an acceptable v1 boundary, consistent with the repository's manual-secret
  policy.
- The dashboard frontend is used by household devices on the tailnet; a TV that cannot join the
  tailnet would require a future LAN exposure decision and is out of scope.
- The published images are trusted and versioned independently; the operator updates them
  deliberately and accepts module frontend/backend skew only as documented.
- Existing single-node, backup, and recovery limitations from the baseline specification still
  apply.
