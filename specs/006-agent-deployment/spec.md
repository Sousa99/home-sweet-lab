# Feature Specification: Agent Workload Deployment

**Feature Branch**: `main`

**Created**: 2026-11-07

**Status**: Draft

**Input**: User description: "Deploy the Home Sweet Home agent (home-sweet-home-agent) as a
Flux-managed workload on the dietpi k3s cluster, using in-cluster Service DNS for module MCP sources
and Home Assistant, HTTP health probes, cluster security conventions, out-of-band secrets, and Flux
image automation for new `main-*` tags."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run the agent as a Flux-managed workload (Priority: P1)

The household operator merges the agent manifests to the tracked branch. Flux reconciles a new
agent namespace containing the agent Deployment, a cluster-internal Service, and supporting
configuration. The agent pod starts on the DietPi node, reads its non-secret configuration from a
ConfigMap, reads its credentials from manual Secrets, and becomes Ready once the LLM provider is
available.

**Why this priority**: Nothing else in this feature has value until the agent runs under GitOps on
the real cluster and becomes Ready. This is the minimum viable integration.

**Independent Test**: Reconcile from Git, confirm Flux owns the agent namespace and Deployment,
confirm the pod is Ready on the `dietpi` node, and confirm the expected objects exist. No external
client is required.

**Acceptance Scenarios**:

1. **Given** the agent manifests are merged to the tracked branch, **When** Flux reconciles,
   **Then** the agent namespace, Deployment, ConfigMap, Service, and image automation objects exist
   and Flux reports them as managed.
2. **Given** the required manual Secrets exist, **When** the Deployment starts a pod, **Then** the
   pod schedules on `dietpi` and becomes Ready.
3. **Given** the agent pod is Ready, **When** the operator inspects it, **Then** it is configured
   through a ConfigMap for non-secret settings and through Secret-backed environment variables for
   credentials.
4. **Given** the agent starts, **When** no caller tokens are configured, **Then** startup fails as
   designed and the failure is visible; the repository documents the manual step that fixes it.

---

### User Story 2 - Reachable from inside the cluster with authenticated and unauthenticated checks (Priority: P1)

An in-cluster consumer reaches the agent through a stable ClusterIP Service on port 3400. The
unauthenticated liveness and readiness endpoints are usable by Kubernetes probes, and the
authenticated application endpoint still requires a bearer token.

**Why this priority**: The probes drive pod health, and the authenticated endpoint is the actual
service surface. Both are needed for the workload to be useful and safe.

**Independent Test**: From a temporary pod in another namespace, request the agent Service and
confirm `/healthz` and `/readyz` respond without credentials while `/health` rejects requests
without a bearer token.

**Acceptance Scenarios**:

1. **Given** the agent pod is running, **When** an in-cluster request reaches `GET /healthz`,
   **Then** it returns `200` without a bearer token.
2. **Given** the LLM provider is configured and the agent is not draining, **When** an in-cluster
   request reaches `GET /readyz`, **Then** it returns `200` without a bearer token.
3. **Given** the LLM provider is not ready or the agent is draining, **When** `/readyz` is requested,
   **Then** it returns `503`.
4. **Given** any configured module MCP source or Home Assistant is unavailable, **When** `/readyz`
   is requested, **Then** it remains `200` and degraded operation is supported.
5. **Given** the agent is running, **When** `GET /health` is requested without a valid bearer token,
   **Then** the request is rejected; with a valid bearer token it succeeds.
6. **Given** the Service is reconciled, **When** cluster exposure is inspected, **Then** it is a
   ClusterIP Service with no Ingress, load balancer, node port, host port, or host networking.
7. **Given** the agent Service exists, **When** the operator inspects reachability, **Then**
   `/conversation` and other authenticated routes are not publicly reachable.

---

### User Story 3 - Endpoints use in-cluster Service DNS (Priority: P2)

The agent talks to its module MCP sources and Home Assistant through stable cluster DNS names rather
than `localhost` or Docker-style hostnames, so the workload works when scheduled as a pod.

**Why this priority**: Without correct service discovery the agent cannot use its tools, but this
depends on the agent already running (P1).

**Independent Test**: Inspect the ConfigMap and confirm every endpoint is a cluster DNS URL; from
inside the agent pod, resolve each hostname and reach the `/mcp` path.

**Acceptance Scenarios**:

1. **Given** the module MCP services are running in the dashboard namespace, **When** the agent
   resolves its configured URLs, **Then** bus, flights, tasks, and weather MCP endpoints are reached
   by in-cluster Service DNS.
2. **Given** Home Assistant is running in the home-assistant namespace, **When** the agent resolves
   its configured URL, **Then** the MCP path is reached by in-cluster Service DNS.
3. **Given** the configuration is inspected, **When** non-secret settings are reviewed, **Then**
   endpoints are supplied by a ConfigMap and no secret values are present in it.

---

### User Story 4 - Apply cluster security and resource conventions (Priority: P2)

The agent workload follows the same security and resource conventions as the other household
workloads so it cannot escalate privileges, write to its image filesystem, or starve the node.

**Why this priority**: These controls protect the single-node cluster and Home Assistant, but they
do not block initial operation and can be verified independently.

**Independent Test**: Inspect the rendered Deployment and confirm the pod and container security
settings, service account token setting, node selection, resources, and grace period match the
documented conventions.

**Acceptance Scenarios**:

1. **Given** the Deployment is rendered, **When** its pod security settings are reviewed, **Then**
   it runs as non-root with uid/gid 1000, does not mount a service account token, and targets the
   `dietpi` node with the amd64 architecture.
2. **Given** the container security context is reviewed, **When** it is inspected, **Then** the root
   filesystem is read-only, privilege escalation is disabled, and all capabilities are dropped.
3. **Given** the Deployment is reviewed, **When** resources are inspected, **Then** CPU and memory
   requests and limits are defined.
4. **Given** the agent drains for up to five seconds on shutdown, **When** the Deployment is
   reviewed, **Then** the termination grace period is at least 15 seconds.

---

### User Story 5 - Credentials stay out of Git and are supplied manually (Priority: P2)

The operator creates the caller-token, LLM, and Home Assistant credentials out of band as cluster
Secrets. The Deployment references them and never commits them. The plaintext bearer token for
clients is generated separately and not stored in this repository.

**Why this priority**: The agent intentionally fails without caller tokens, and leaking credentials
in a public repository is unacceptable. This is required for a real deployment but can be verified
after the workload shape exists.

**Independent Test**: Confirm the repository contains no secret material, confirm each Secret is
referenced by key, and confirm the documented creation commands produce a Ready agent.

**Acceptance Scenarios**:

1. **Given** the repository is scanned, **When** secret scanning runs, **Then** no caller tokens,
   LLM keys, Home Assistant tokens, GHCR credentials, or tailnet identifiers are found.
2. **Given** the caller-token Secret is missing, **When** the agent starts, **Then** startup fails
   visibly and the documentation explains how to generate and create the Secret.
3. **Given** the LLM Secret is missing, **When** the agent starts, **Then** readiness reports not
   ready and the documentation explains the required key.
4. **Given** the Home Assistant Secret is omitted, **When** the agent runs, **Then** it reports that
   source unavailable while continuing to operate.
5. **Given** the caller token is generated, **When** the operator inspects the cluster Secret,
   **Then** it contains only the hash map and the plaintext bearer token is delivered to the caller
   separately, as documented.
6. **Given** the image is published publicly in GHCR, **When** the pod starts, **Then** no pull
   secret is required.

---

### User Story 6 - New agent image tags roll out automatically (Priority: P3)

When the agent publishing workflow publishes a new `main-*` image, Flux discovers the tag, selects it,
and updates the Deployment image setter so the workload rolls forward without manual edits.

**Why this priority**: Automation reduces toil but is not required for the first deployment; it can be
verified after the workload is running.

**Independent Test**: Publish or wait for a new `main-*` tag, confirm the image policy selects it,
and confirm Flux commits the Deployment update and the rollout succeeds.

**Acceptance Scenarios**:

1. **Given** a new tag matching the agent tag convention is published, **When** the image policy
   scans, **Then** it selects the newest matching tag.
2. **Given** the image policy selects a new tag, **When** the update automation runs, **Then** it
   updates the agent image field in `./apps/agent` and commits and pushes to the tracked branch.
3. **Given** the updated image is public and valid, **When** Flux reconciles, **Then** the Deployment
   rolls to the new image and the pod becomes Ready.
4. **Given** a non-matching tag is published, **When** the image policy scans, **Then** it is
   ignored.

---

### User Story 7 - Documentation enables operation and recovery (Priority: P3)

The operator can read the repository documentation to deploy, verify, update, troubleshoot, and
recover the agent and its manual Secrets.

**Why this priority**: The household lab must be reproducible from documentation alone, but this
trails the working deployment.

**Independent Test**: Follow the new documentation from a clean checkout and confirm it leads to a
Ready agent and working probes.

**Acceptance Scenarios**:

1. **Given** the feature is merged, **When** the operator reads the docs, **Then** they find the
   agent deployment, configuration, secret creation, probe verification, image automation, and
   recovery procedures.
2. **Given** the repository documentation index and README are reviewed, **When** the agent feature
   is checked, **Then** the architecture, status, repository map, and related repositories reflect
   the new workload.
3. **Given** the validation script is run, **When** the feature is complete, **Then** it renders and
   validates the new app and passes without secret findings.

---

### Edge Cases

- The caller-token Secret is missing or empty; startup fails as designed and the failure is
  documented rather than silently serving unauthenticated requests.
- The tokens are supplied as a mounted `tokens.json` file instead of the environment hash map; the
  configuration must support the documented file-based alternative.
- The LLM key is missing or the provider is unreachable; the pod may start but readiness stays `503`
  and the condition is documented.
- A module MCP source or Home Assistant is down; readiness stays `200`, the affected capability is
  unavailable, and the rest of the agent continues.
- Home Assistant is intentionally not configured; the agent reports the source unavailable and
  remains ready.
- The agent receives SIGTERM during a rollout or node shutdown; it drains for up to five seconds and
  terminates within the grace period.
- The pod is scheduled on a non-amd64 or non-`dietpi` node; scheduling must be constrained so the
  published image runs on the intended node.
- The image tag does not match the documented convention; the ImagePolicy must ignore it.
- A new tag matches but the image is broken; the operator can revert the image pin through Git and
  recover.
- The public GHCR package becomes private; image pulls fail visibly and the documented remediation
  applies.
- The agent's logs fill its writable space; the read-only root filesystem must not cause unexpected
  writes, and any required writable location must be explicitly provided.
- The Service is accidentally exposed through an Ingress; review must catch it because the Service
  is intended to remain cluster-internal.
- A manual `kubectl` change to the Deployment is reverted by Flux; manual edits are not a supported
  operation.
- The node reboots; Flux recreates the workload and the pod returns to Ready without manual action.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The agent workload MUST be added as a self-contained `apps/agent` Kustomization
  containing a namespace, Deployment, ClusterIP Service on port 3400, non-secret configuration, and
  Flux image automation objects.
- **FR-002**: The new app MUST be added to the existing `apps` Kustomization so the existing Flux
  delivery path reconciles it.
- **FR-003**: The Deployment MUST run the published agent image with an immutable, sortable tag and
  MUST NOT use `latest`.
- **FR-004**: The image field MUST carry the Flux image setter marker so the update automation can
  change it.
- **FR-005**: Image automation MUST include an ImageRepository, an ImagePolicy that filters the agent
  tag pattern and selects alphabetically ascending, and an ImageUpdateAutomation that updates
  `./apps/agent`, matching the existing workload pattern.
- **FR-006**: The agent MUST listen on port 3400 bound to `0.0.0.0`, run with `NODE_ENV=production`,
  and read the non-secret settings from a ConfigMap.
- **FR-007**: The non-secret ConfigMap MUST include host, port, environment, module MCP URLs, Home
  Assistant MCP URL, LLM base URL, LLM model, timeouts, policy, and log level.
- **FR-008**: Every configured endpoint MUST use in-cluster Service DNS, not `localhost` or
  Docker-style hostnames.
- **FR-009**: The bus, flights, tasks, weather, and Home Assistant URLs MUST match the documented
  cluster Services and `/mcp` paths.
- **FR-010**: Liveness MUST use HTTP `GET /healthz` and readiness MUST use HTTP `GET /readyz` on port
  3400.
- **FR-011**: Probes MUST remain unauthenticated and MUST NOT depend on MCP sources or Home
  Assistant, so degraded operation does not cause restarts.
- **FR-012**: The Deployment MUST set a termination grace period of at least 15 seconds to cover the
  agent's five-second drain.
- **FR-013**: The pod MUST schedule on the `dietpi` node with the amd64 architecture.
- **FR-014**: The pod MUST run as non-root with uid and gid 1000 and MUST NOT mount a service
  account token.
- **FR-015**: The container MUST use a read-only root filesystem, disable privilege escalation, and
  drop all capabilities.
- **FR-016**: The container MUST define CPU and memory requests and limits.
- **FR-017**: The Service MUST be ClusterIP and cluster-internal; the feature MUST NOT add an
  Ingress, load balancer, node port, host port, or public exposure.
- **FR-018**: The authenticated `/conversation` route and the authenticated `/health` route MUST NOT
  be exposed outside the cluster; `/health` MUST continue to require a bearer token.
- **FR-019**: Caller authentication MUST be supplied by an out-of-band Secret referenced through
  environment variables, containing either the single-line JSON hash map or a mounted tokens file
  path as documented.
- **FR-020**: The LLM API key MUST be supplied by an out-of-band Secret and referenced by key; it
  MUST NOT be committed.
- **FR-021**: The Home Assistant long-lived token MUST be supplied by an out-of-band Secret and
  referenced by key; when omitted, the feature MUST remain operational and report that source
  unavailable.
- **FR-022**: No GHCR pull secret MUST be required; the documentation MUST state the package is
  public and describe the failure and remediation if that changes.
- **FR-023**: The feature MUST document the out-of-band creation of each Secret, including the
  caller-token generation command, and MUST state that the plaintext bearer token is delivered to
  the caller separately and never committed.
- **FR-024**: The repository MUST NOT contain caller tokens, hashes, LLM keys, Home Assistant
  tokens, pull credentials, or real tailnet identifiers; identities use placeholders.
- **FR-025**: The feature MUST document deployment, probe verification from inside the cluster,
  image update, troubleshooting, and recovery procedures, and MUST add them to the documentation
  index.
- **FR-026**: The README architecture, status, repository map, and related repositories MUST be
  updated to include the agent workload.
- **FR-027**: The feature MUST pass the repository validation script, including rendering the new
  Kustomization, Kubernetes schema validation, YAML linting, and secret scanning.
- **FR-028**: The feature MUST NOT change agent runtime code, conversation behavior, proactive
  triggers, the Home Assistant conversation adapter, or migrate the module services.
- **FR-029**: The feature MUST NOT add public exposure, authentication for the probes, high
  availability, multiple replicas, replicated storage, or automated secret management.
- **FR-030**: The workload MUST recover automatically after pod deletion, Flux reconciliation, and
  node reboot without manual `kubectl apply`.

### Key Entities

- **Agent workload**: The Flux-managed Deployment running the published agent image on the DietPi
  node.
- **Agent Service**: The stable cluster-internal endpoint on port 3400 used by in-cluster consumers
  and probes.
- **Agent ConfigMap**: The non-secret settings, including service endpoints, LLM base/model, and
  runtime policy.
- **Agent Secrets**: The manually created caller-token, LLM key, and Home Assistant token objects,
  each referenced by key and never committed.
- **Caller token**: The plaintext bearer credential delivered to a client, with only its hash map
  stored in the cluster.
- **Module MCP endpoint**: One of the bus, flights, tasks, or weather in-cluster `/mcp` URLs.
- **Home Assistant MCP endpoint**: The in-cluster Home Assistant `/api/mcp` URL.
- **Image automation objects**: The ImageRepository, ImagePolicy, and ImageUpdateAutomation that
  roll new `main-*` tags into the Deployment.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A merged agent change produces a Ready agent pod on the DietPi node within 10 minutes,
  with no manual deployment commands.
- **SC-002**: From inside the cluster, `/healthz` returns `200` without credentials on 100% of
  attempts while the process is alive.
- **SC-003**: With the LLM key present, `/readyz` returns `200` within 5 seconds on 100% of attempts.
- **SC-004**: With the LLM key absent or the provider unavailable, `/readyz` returns `503` and the
  condition is visible through pod status and logs.
- **SC-005**: With any MCP source or Home Assistant unavailable, `/readyz` remains `200` and the
  remaining capabilities continue to operate.
- **SC-006**: `/health` rejects 100% of requests without a valid bearer token and accepts requests
  with one.
- **SC-007**: A new matching `main-*` tag updates the Deployment and produces a Ready pod within 15
  minutes without manual edits.
- **SC-008**: An external access audit finds zero publicly reachable agent endpoints and confirms the
  Service is ClusterIP only.
- **SC-009**: Secret and repository scanning find zero committed credentials, token hashes, pull
  credentials, or real tailnet identifiers.
- **SC-010**: After deliberate pod deletion or a node reboot, the agent returns to Ready within 5
  minutes without operator action.
- **SC-011**: During normal agent operation, Home Assistant remains available and the node shows no
  memory pressure or workload evictions.
- **SC-012**: `scripts/validate.sh` passes with the new app included.

## Out of Scope

- Agent runtime, code, image, build, or publishing-workflow changes; these belong to
  `home-sweet-home-agent`.
- The Home Assistant conversation adapter, LLM prompt design, conversation behavior, and proactive
  triggers.
- Public internet exposure, Ingress, SSO, caller-token rotation automation, or secret management
  operators.
- Migrating the module REST or MCP services, changing their images, or modifying the dashboard stack.
- High availability, multiple replicas, replicated storage, or multi-node scheduling.
- Automated backup or restore of agent state; the agent is stateless for this deployment.
- Changes to Home Assistant configuration or creation of its long-lived token.

## Dependencies

- A healthy single-node k3s cluster on `dietpi` with Flux reconciling this repository.
- The published public image `ghcr.io/sousa99/home-sweet-home-agent` with a `main-*` tag.
- The dashboard namespace module MCP Services running on port 3001 with `/mcp` paths.
- Home Assistant running at `home-assistant.home-assistant.svc.cluster.local:8123` with the `/api/mcp`
  path.
- A manually created caller-token Secret.
- A manually created LLM key Secret.
- Optionally, a manually created Home Assistant long-lived token Secret.
- Outbound internet access from the cluster to the remote OpenAI-compatible LLM endpoint.
- A Linux amd64 node matching the published image architecture.

## Assumptions

- The agent namespace is `agent`, the Deployment and Service are named `agent`, and the Service port
  is 3400.
- The agent is single-replica and stateless; no PersistentVolumeClaim is required.
- The image runs as the `node` user with uid and gid 1000.
- The existing `dashboard` namespace hosts the module MCP Services on port 3001 and the existing
  `home-assistant` namespace hosts Home Assistant on port 8123.
- The LLM endpoint is OpenAI-compatible and reachable over the internet; its base URL and model are
  non-secret and belong in the ConfigMap.
- LLM timeouts and policy defaults are supplied through the ConfigMap and can be adjusted later
  without an image rebuild.
- Readiness intentionally ignores MCP sources because degraded operation is supported.
- A single caller may exist initially; additional callers require regenerating the hash map Secret
  and restarting the pod, which is documented.
- The existing image automation pattern (Setters strategy, tracked `main` branch, `fluxcdbot` author)
  applies unchanged to the agent.
- The image tag convention remains `main-YYYYMMDDHHMMSS-<7-char-sha>` and is produced by the agent
  publishing workflow.
- Existing single-node, backup, and recovery limitations from the baseline specification still
  apply.
