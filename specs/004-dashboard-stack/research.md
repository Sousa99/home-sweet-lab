# Phase 0 Research: Dashboard Stack on k3s

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

All unknowns in the implementation plan are resolved below. No `NEEDS CLARIFICATION` markers
remain.

## R1. Deployment topology

**Decision**: Create nine Deployments: one frontend, four REST backends, and four MCP servers. Each
module gets a `-rest` Deployment and a `-mcp` Deployment from the same pinned image, with separate
Services that select `app.kubernetes.io/component: rest` or `app.kubernetes.io/component: mcp`.

**Rationale**:

- The spec and user request treat REST APIs and MCPs as separate runtimes. The published Compose
  file also runs them as separate processes.
- Separate pods give independent readiness, restart, and rollout behavior. A failing REST process
  must not remove the MCP endpoint from service, and restarting a single-session MCP container must
  not restart the REST API.
- A single Service selecting both pods would route `port 3000` traffic to MCP-only pods, where that
  port is not the MCP listener. Separate component labels and Services prevent this.

**Alternatives considered**:

- **Four pods with REST + MCP containers**: fewer pods and shared volumes, but pod-level readiness
  couples the two endpoints, and restarting one container is less observable. Rejected.
- **One process serving both HTTP and MCP**: the published images document `--http` and `--mcp`
  modes separately; combined mode is not documented. Rejected.

## R2. Stateful data placement

**Decision**: Two 1 GiB `local-path` PVCs: `bus-catcher-data` and `procrastinator-data`. Each is
mounted at `/data` in both the REST and MCP pod for that module. Fly-over-tracker and
weather-psychic have no PVC.

**Rationale**:

- The module images write SQLite at `DB_PATH=/data/bus-catcher.db` and
  `DATABASE_URL=/data/procrastinator.db`.
- A single node means an RWO volume can be mounted by multiple pods on that node; both processes
  need the same files, matching the Compose bind mount.
- Separate PVCs isolate module data and make backup, restore, and deletion per module
  understandable.

**Alternatives considered**:

- **One shared PVC for both modules**: simpler backup, but couples module lifecycle and file
  ownership with no operational benefit.
- **A PVC per container**: REST and MCP would diverge, violating the data-consistency requirement.
- **`emptyDir`**: data would be lost on pod replacement and would break the persistence requirement.

**Risk to verify on the cluster**: two pods mounting the same RWO `local-path` volume. The single
node makes this valid; the deployment drill must confirm both processes can read and write without
`Multi-Attach` errors and that SQLite locking is acceptable at household traffic levels. If not,
fall back to a two-container module pod or a single coordinated accessor.

## R3. Kubernetes-compatible frontend proxy

**Decision**: Replace the image's `/etc/nginx/conf.d/default.conf` with
`apps/dashboard/nginx.conf` mounted from a generated ConfigMap. Use static upstreams
`bus-catcher-rest:3000`, `procrastinator-tracker-rest:3000`, `fly-over-tracker-rest:3000`, and
`weather-psychic-rest:3000`, preserving the `/api/<module>` prefix stripping from the published
configuration.

**Rationale**:

- The published `nginx.conf` uses `resolver 127.0.0.11`, which is Docker's embedded DNS and does not
  exist in Kubernetes. The upstream service names would not resolve.
- Service ClusterIPs are stable, so resolving the Service names once at nginx startup is sufficient.
  No runtime variable resolver is required.
- Keeping the rewrite rules identical to the published Compose/Vite proxy preserves widget behavior:
  `/api/bus/api/health` becomes `/api/health`, `/api/tasks/health` becomes `/health`, and so on.

**Alternatives considered**:

- **Modify the dashboard repository**: out of scope and would require a new image.
- **Expose each REST API with an Ingress and have the browser call it**: rejected by the user;
  adds unauthenticated external endpoints and CORS.
- **Hardcode `10.43.0.10` as the resolver**: cluster-specific and brittle; unnecessary when the
  upstreams are Services with stable ClusterIPs.

**Trade-off**: If a module Service is deleted and recreated with a different ClusterIP, the frontend
pod must be restarted. Service names and ClusterIPs are stable in normal Flux reconciliation; the
runbook records the restart requirement if a Service is recreated.

## R4. Runtime dashboard configuration

**Decision**: Supply `config.json` as a manually created Secret named `dashboard-config` in the
`dashboard` namespace. Mount it read-only at `/usr/share/nginx/html/config.json`. A Python init
container validates it before nginx starts, using the same `validate-config.py` that the repo tests
and the operator runs before creating the Secret.

**Rationale**:

- The dashboard's `loadConfig()` catches every error and deep-merges over `DEFAULT_CONFIG`. A
  missing or malformed file therefore silently falls back to a built-in location, which violates the
  requirement to fail visibly rather than show a different household location.
- The JSON contains home coordinates, stop IDs, and display choices. The repository is public, so it
  must not be committed. A Kubernetes Secret is consistent with the repository's manual-secret
  policy.
- An init container can fail the pod before nginx serves the SPA, making the problem visible in
  `kubectl describe pod` and events. Python 3.12 is already pinned in the host-metrics image and has
  a standard-library JSON parser.

**Alternatives considered**:

- **Commit a ConfigMap**: leaks household location and travel patterns.
- **Bake the config into an image**: requires a rebuild and puts private data in Git/image layers.
- **Rely on the SPA's defaults**: explicitly rejected by the spec.
- **Validate only with `kubectl` outside the cluster**: does not protect against a later edit or a
  partial Secret update.

**Validation scope**: syntactically valid JSON, required `flights.location` and `weather.location`
objects with numeric coordinates, `bus.stops` array, stop IDs/names, and basic type/range checks for
clock, tasks, and status. The validator never prints values, only the failing path and reason.

## R5. External access

**Decision**: A Tailscale Ingress with short hostname `dashboard` exposes only the frontend Service.
REST Services and MCP Services remain ClusterIP. Local debugging uses `kubectl port-forward`.

**Rationale**:

- Matches the established Home Assistant pattern and the operator's clarification.
- Browser clients do not need direct REST ingress: the frontend proxy makes API calls same-origin.
  This avoids four unauthenticated Tailscale hostnames and CORS handling.
- MCP servers have no built-in authentication. Exposing them on the tailnet would let any tailnet
  member call them; cluster-internal access is the safer boundary for the agent.

**Alternatives considered**:

- **Traefik/LAN or public ingress for the dashboard**: rejected by the operator; the TV/display is
  on the tailnet.
- **Per-API Tailscale ingress**: rejected; adds surface without browser need.
- **MCP Tailscale ingress**: rejected for v1; use port-forward for debugging.

## R6. Image availability and pins

**Decision**: Pin the dashboard to `ghcr.io/sousa99/home-sweet-home-dashboard:0.1.0` and the module
backends to `0.2.0`, `0.5.0`, `0.2.0`, and `0.1.0`. Resolve the dashboard package visibility by
making it public; if that is not possible, create a `ghcr-pull` Secret and add
`imagePullSecrets: [{name: ghcr-pull}]` to the frontend Deployment. No Flux image automation is
added.

**Rationale**:

- During specification, the four backend images were anonymously pullable but the dashboard image
  was not; the release workflow had succeeded, so this is a package-visibility issue rather than a
  missing build.
- The dashboard repository is public and the image contains no live household state; making the
  package public matches the other GHCR images and avoids a long-lived token.
- The dashboard and modules version independently. Automatic updates could combine an untested
  frontend package with a backend image. Pins plus a documented matrix and Git revert are safer.

**Alternatives considered**:

- **Use `latest`**: mutable and violates the constitution.
- **Add image automation for semver tags**: version tags are release tags, not build-immutable
  `main-<timestamp>-<sha>` tags; automated selection adds risk with little household benefit.
- **Always require a pull Secret**: introduces a credential even when the package can be public.

## R7. Health probes

**Decision**:

| Workload | Startup/readiness/liveness |
| -------- | -------------------------- |
| Frontend | HTTP `GET /` on port 80 |
| Bus REST | HTTP `GET /api/health` on 3000 |
| Tasks REST | HTTP `GET /health` on 3000 |
| Weather REST | HTTP `GET /api/health` on 3000 |
| Fly REST | TCP 3000 (no documented local health endpoint; avoid an external-feed probe) |
| All MCP | TCP 3001 |

**Rationale**: Probes must reflect local process readiness, not external provider health. Using the
flight feed endpoint as a liveness probe would restart the backend during an adsb.lol outage. The
frontend probe uses `/`, which remains healthy when a module is down.

**Alternatives considered**: a single HTTP probe for every service (not available for fly/MCP), and
using the fly feed for liveness (couples restart behavior to a third party).

## R8. Resource sizing

**Decision**: Each REST/MCP container requests `50m` CPU and `128Mi` memory and limits to `500m` CPU
and `512Mi` memory, except `bus-catcher-rest`, which requests `100m`/`256Mi` and limits to `1` CPU
and `2Gi` memory. The frontend requests `25m`/`32Mi` and limits to `250m`/`128Mi`.

**Rationale**: Eight Node processes plus nginx on a 15 GiB, 8 vCPU node. Total requests are about
`475m` and `1.19Gi`; total limits are about `4.75` cores and `5.63Gi`. That leaves substantial
headroom for Home Assistant, Flux, Tailscale, and k3s. The first GTFS ingest OOMKilled
`bus-catcher-rest` at 512Mi during validation, so that one container gets 2Gi; the rest stay small.

**Alternatives considered**: no limits (unsafe on a single node) and very small limits (risk of
OOMKill during Node startup). The values are validated during deployment and adjusted only with a
recorded reason.

## R9. Backup and restore strategy

**Decision**: Use a maintenance-window stop-copy-start procedure. `pull-dashboard-data.sh` suspends
the `apps` Flux Kustomization, scales the four stateful module Deployments to zero, runs a temporary
pinned Python helper pod that tar-and-hashes both PVC contents, copies the archive to the Mac,
scales back to one, resumes Flux, and reconciles. `restore-dashboard-data.sh` reverses the process
and verifies checksums before extraction. The scripts use traps to resume Flux and restore replicas
on failure.

**Rationale**:

- SQLite is not safe to copy while a writer is active without a checkpoint/backup API.
- The household dashboard can tolerate a short maintenance window; it is not a real-time safety
  service.
- Suspending Flux prevents it from reverting the temporary scale-down during the window.
- The existing repository already uses helper pods and checksum-verified state archives for Home
  Assistant, so this fits the operating model.

**Alternatives considered**:

- **Online SQLite backup through the module's `better-sqlite3`**: possible, but adds a
  library-dependent script and more failure modes for a low-traffic service. Deferred.
- **Copying the live files without stopping writers**: risks inconsistent backups.
- **Automated CronJob**: out of scope; the repository's backup model is manual and recorded.

## R10. No image automation

**Decision**: No new `ImageRepository`, `ImagePolicy`, or `ImageUpdateAutomation` resources.

**Rationale**: The dashboard's release artifact is a semver tag and `latest`; it does not publish
immutable `main-<timestamp>-<sha>` tags. Independent dashboard and backend pins already make module
updates deliberate. Flux image automation would add write-back commits without resolving the
frontend/backend compatibility question.

## R11. Validation additions

**Decision**: Add `apps/dashboard/test_validate_config.py` and run it from `scripts/validate.sh`.
Keep the existing Kustomize render, `kubeconform`, `yamllint`, and `gitleaks` checks; the dashboard
app is included automatically by the `apps` Kustomization. Add cluster smoke tests to
`quickstart.md` rather than CI, because they require the real cluster.

**Rationale**: The only new repo-owned executable logic is the config validator. The manifests are
covered by the existing render/schema/lint pipeline. The nginx config is validated by a real
frontend deployment; a local `nginx -t` is optional and not guaranteed on the Mac.

## R12. Fly-over and weather MCP Host-header workaround

**Decision**: Run an nginx sidecar named `host-rewrite` in the `fly-over-tracker-mcp` and
`weather-psychic-mcp` pods. The MCP process listens on `0.0.0.0:3002`; nginx listens on `3001`, proxies
to `127.0.0.1:3002`, sets `Host: localhost` and `Origin: http://localhost`, disables buffering, and
keeps long SSE read/send timeouts. The public Service still exposes port `3001`.

**Rationale**:

- The published fly-over and weather MCP servers call `createMcpHonoApp()` from
  `@modelcontextprotocol/hono`. When no `host` option is passed, that helper defaults to
  `127.0.0.1` and installs localhost DNS-rebinding validation. A request with a Kubernetes Service
  DNS Host header is rejected with `Invalid Host: <service>`.
- The bus-catcher and procrastinator MCP servers accept the Service DNS Host and need no sidecar.
- Rewriting Host inside the pod keeps the consumer contract simple: the agent uses the same
  `<module>-mcp.dashboard.svc.cluster.local:3001/mcp` URLs for all four modules. It also strips or
  normalizes Origin for browser-originated requests.
- The nginx sidecar is pinned by digest, uses small resource limits, and keeps the MCP process off the public Service
  surface; nginx reaches it over loopback inside the pod.

**Alternatives considered**:

- **Require every MCP client to send `Host: localhost`**: fragile across clients and not enforceable
  in the documented agent interface.
- **Modify the module images**: out of scope and would require new releases.
- **Use a shared MCP reverse proxy**: adds a fifth Service and a fan-out layer for only two modules.
- **Expose the MCP port directly**: still fails Host validation and is not a fix.

**Verification**: an MCP `initialize` request from the `home-assistant` namespace must return a
result for all four Service URLs. The sidecar's liveness/readiness probes use TCP 3001; the MCP
process probes use TCP 3002.
