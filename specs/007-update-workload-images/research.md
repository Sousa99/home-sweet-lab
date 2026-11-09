# Phase 0 Research: Workload Image Updates

## Image availability and identity

### Decision

Use `ghcr.io/sousa99/bus-catcher-backend:0.4.0` for both bus workloads and
`ghcr.io/sousa99/home-sweet-home-home-assistant:main-20261109193052-7e131ee` for all four Home
Assistant image references.

### Rationale

Both tags were verified pullable from GHCR by resolving their manifests anonymously:

```text
sousa99/bus-catcher-backend:0.4.0                                  -> HTTP 200
sousa99/home-sweet-home-home-assistant:main-20261109193052-7e131ee -> HTTP 200
```

The Home Assistant image config reports
`org.opencontainers.image.revision=7e131eed46127fef807df7494032f67587629bab`, matching the requested
tag suffix. It also reports Home Assistant core `2026.11.1`. The bus-catcher image tag is immutable
and matches the release requested by the operator.

### Alternatives considered

- **Leave Home Assistant to image automation only**: rejected for this change because the operator
  provided an explicit tag and the documentation must record the exact pin that was verified. Keeping
  the setter markers preserves future automation.
- **Use a digest instead of the tag**: valid under the constitution, but the existing workloads and
  Home Assistant automation use tag references. Switching formats would add churn without changing
  behavior. Tags are immutable in these publishing workflows.

## bus-catcher 0.4.0 behavior

### Decision

Update both bus Deployments together and do not add new environment variables in the same change.

### Rationale

The 0.4.0 release changes include:

- Automatic schedule load on startup when the database is empty, plus a periodic staleness check.
- Streaming, memory-bounded GTFS ingest instead of loading the full feed in memory.
- Skipping re-ingest when the upstream feed is unchanged.
- A crash-safe lock preventing REST and MCP from ingesting concurrently.
- A new `refreshError` status field and `force` support on REST and MCP refresh.

The defaults are suitable for this deployment: `SCHEDULE_AUTO_REFRESH=true` and
`SCHEDULE_CHECK_INTERVAL_MS=900000` (15 minutes). The REST process owns ingestion; MCP does not
auto-ingest. No manifest change is required to obtain the fix.

### Alternatives considered

- **Explicitly set the new variables in the manifests**: rejected for now. Explicitly pinning defaults
  adds configuration noise and a second place to maintain. The defaults are documented instead.
- **Update only the REST Deployment**: rejected. Both processes share the same SQLite file and must
  use the same binary version to avoid mixed database expectations.
- **Keep 0.3.0 and only raise memory**: rejected. The release specifically fixes the ingest memory
  behavior; raising limits alone already failed to make the refresh reliable.

## Bus memory limit

### Decision

Retain the existing 10 GiB limit on `bus-catcher-rest` and the existing 1 GiB limit on
`bus-catcher-mcp` for this rollout.

### Rationale

The new ingest is memory-bounded, so observing success under the current limit proves the fix. The
10 GiB limit was chosen for the previous in-memory ingest and is intentionally generous for the
first run. Lowering it is a separate optimization that should follow observed peak usage rather than
be bundled with the version change.

The dashboard documentation currently disagrees with the manifest in one place: the first-run text
says 8 GiB while the Deployment and data model say 10 GiB. The docs update will make this consistent
with the manifest.

### Alternatives considered

- **Lower the limit immediately**: rejected. Without a measured peak, this risks reintroducing an
  OOMKill during the first successful refresh.
- **Raise the limit above 10 GiB**: rejected. The node has about 15 GiB total and the existing limit
  already exceeds the release's expected needs; raising it would reduce headroom for other workloads.

## Bus database compatibility

### Decision

Treat the existing bus database as forward-compatible and verify it during rollout.

### Rationale

The 0.4.0 changes are in schedule loading, GTFS ingest, refresh coordination, and status reporting.
The release does not add a new Drizzle migration for the stored data model. The refresh path disables
foreign-key enforcement during the feed replace and preserves the configured stop list, which is the
existing behavior. Startup applies any pending migrations as before.

### Alternatives considered

- **Delete or rebuild the PVC before upgrading**: rejected. It would lose the configured stop list and
  violates the recoverability principle for no proven benefit.
- **Run an out-of-cluster pre-migration**: rejected. No schema change requires it, and the workload
  should remain GitOps-managed.

## Home Assistant seeding

### Decision

Do not perform a separate state seed, state-bundle upload, or manual file copy. Rely on the existing
`seed-config` init container during the rollout and record the evidence.

### Rationale

The Deployment runs an init container that executes `cp -a /config-seed/. /config/` on every pod
start. The rollout replaces the pod, so the new image's tracked configuration is copied into the
existing PVC. The new image contains tracked configuration plus
`config/custom_components/home_sweet_home_agent/`; `COPY config/ /config-seed/` includes both. The
seed overwrites tracked files and does not delete untracked files. It does not touch `.storage`,
databases, secrets, media, or Zigbee state.

The `restore-state` init container only applies bundles found under `/config/import/`. No new bundle
is placed there, so the existing state is not re-applied. The expected outcome is therefore:

- No state-bundle upload needed.
- No manual `/config` copy needed.
- New custom component present after the pod restarts.
- Existing `.storage`, recorder database, secrets, and Zigbee state preserved.

This expectation must still be verified because "seed" could mean tracked configuration, private
state, or both. The evidence checks in the quickstart distinguish them.

### Alternatives considered

- **Upload and re-apply the latest state bundle**: rejected. It is unnecessary, risks overwriting
  newer runtime state, and would make the rollout non-idempotent.
- **Copy files directly into the pod**: rejected. Flux and the seed init container would conflict, and
  the change would not be reproducible from Git.

## Home Assistant custom integration setup

### Decision

Treat the integration config entry and Assist pipeline selection as manual operator steps outside this
repository's automation.

### Rationale

The adapter is shipped in the image, but its configuration entry (agent URL and bearer token) and the
selected conversation agent live in `.storage` on the PVC, not in tracked YAML. The adapter's owning
repository documents the UI steps. This repository owns image deployment and cluster resources, so
its documentation must point to those steps and verify that the integration is available, without
claiming to automate `.storage` content.

Omitting the manual step does not prevent Home Assistant from becoming Ready; it only leaves the new
Assist capability unavailable.

### Alternatives considered

- **Commit a `.storage` entry**: rejected. It contains credentials and private state, and it is
  explicitly unsynced.
- **Automate the config flow from this repository**: rejected as out of scope. It would cross the
  repository boundary and require handling a secret token in cluster configuration.

## Validation and rollback

### Decision

Gate on `scripts/validate.sh`, then verify on the real cluster. Rollback is a Git revert of the image
pins followed by Flux reconciliation.

### Rationale

The repository constitution requires validation before reconciliation and recovery paths tested on
the real cluster. `scripts/validate.sh` already renders `apps/` and `infrastructure/`, runs
`kubeconform`, lints YAML, runs Python and shell tests, and scans for secrets. The cluster checks in
the quickstart cover the behaviors that cannot be proven by rendering.

### Alternatives considered

- **Rely on Flux reconciliation alone**: rejected. It would not prove ingest success, state
  preservation, or integration availability.
- **Use `kubectl set image` for rollback**: rejected. It is not the source of truth and Flux reverts
  it.
