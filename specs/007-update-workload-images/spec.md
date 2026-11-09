# Feature Specification: Workload Image Updates

**Feature Branch**: `main`

**Created**: 2026-11-09

**Status**: Draft

**Input**: User description: "there is a new version of bus-catcher 0.4.0, and a new version of home-sweet-home-home-assistant home-sweet-home-home-assistant:main-20261109193052-7e131ee. not sure if the home-sweet-home-home-assistant needs to be seeded"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Upgrade bus-catcher to 0.4.0 across REST and MCP (Priority: P1)

The household operator updates the bus-catcher image pin used by both the REST and MCP workloads to
0.4.0, lets Flux reconcile the change, and confirms that the new version loads and refreshes the bus
schedule without exhausting memory. The dashboard bus block and the agent's bus MCP tool then serve
current data.

**Why this priority**: The currently deployed 0.3.0 refresh was OOMKilled at the 10 GiB limit and the
bus data is stale. The new version is the intended fix, so this is the minimum change that restores
the bus capability.

**Independent Test**: Update both bus deployments to 0.4.0, reconcile, confirm both pods are Ready,
trigger or wait for a schedule refresh, and confirm no container is OOMKilled while the REST API and
MCP tool return schedule data newer than the previous stale dataset.

**Acceptance Scenarios**:

1. **Given** the repository pins bus-catcher 0.3.0, **When** the operator changes the pin to 0.4.0 in
   both the REST and MCP manifests, **Then** both workloads reference the same new version.
2. **Given** the updated manifests are reconciled, **When** the rollout completes, **Then** both bus
   pods are Ready and their health/port probes pass.
3. **Given** the new version starts with an existing bus database, **When** the schedule loads or
   refreshes, **Then** the ingest completes without an OOMKill and the dataset is updated.
4. **Given** the schedule has been refreshed, **When** the operator checks the REST API and the MCP
   tool, **Then** both read consistent data from the same persisted database.
5. **Given** the REST and MCP processes run together, **When** a refresh is attempted, **Then** only
   one process performs the ingest and no concurrent-ingest error is surfaced to users.
6. **Given** a pod restarts after the upgrade, **When** it comes back, **Then** the schedule data
   persisted on the volume is still available.
7. **Given** the new version misbehaves, **When** the operator reverts both pins to 0.3.0, **Then**
   the workloads return to their previous Ready state.

---

### User Story 2 - Roll out the new Home Assistant image and settle the seeding question (Priority: P1)

The household operator rolls out
`ghcr.io/sousa99/home-sweet-home-home-assistant:main-20261109193052-7e131ee` and determines, from
evidence rather than assumption, whether the existing persistent state must be seeded again. The
rollout must install any new tracked configuration while preserving `.storage`, databases, secrets,
and Zigbee state.

**Why this priority**: The new image adds tracked configuration, including a custom integration. The
update is only safe and useful if the new tracked files reach `/config` and existing household state
survives.

**Independent Test**: Roll out the new tag, watch the seed, restore, and proxy init steps complete,
confirm the new tracked files exist under `/config` (including the custom integration), confirm
existing runtime state is unchanged, and record whether any separate state-bundle or seeding
operation was needed.

**Acceptance Scenarios**:

1. **Given** the Deployment pins the previous Home Assistant image, **When** the operator updates all
   image references to the new tag, **Then** the init containers and the main container use the same
   new tag and keep their image update markers.
2. **Given** the updated Deployment is reconciled, **When** the pod restarts, **Then** the seed,
   restore-state, and HTTP configuration init containers complete successfully.
3. **Given** the new image contains new tracked configuration, **When** the pod starts, **Then** the
   new tracked files are present under `/config`, including the custom integration directory.
4. **Given** the persistent volume already contains `.storage`, the recorder database, secrets, and
   Zigbee state, **When** the new pod starts, **Then** that state is preserved and usable.
5. **Given** the rollout completes, **When** the operator inspects the seeding evidence, **Then** the
   repository records whether a separate state seed, state-bundle upload, or manual file copy was
   required.
6. **Given** the new integration is present, **When** the operator checks Home Assistant, **Then** the
   integration can be added or remains configured without errors, and existing automations load.
7. **Given** the new image is unsuitable, **When** the operator reverts the image reference to the
   previous tag, **Then** Home Assistant returns to its previous Ready state without state loss.

---

### User Story 3 - Keep deployment documentation and pins truthful (Priority: P2)

The operator can read the repository documentation after the change and see the exact current image
pins, the bus-catcher 0.4.0 behavior change, the Home Assistant seeding decision, the verification
performed, and the rollback steps.

**Why this priority**: The repository is the source of truth for a single-node lab. Stale pins,
unrecorded manual steps, or an undocumented seeding decision would make the next recovery harder.

**Independent Test**: Read the affected docs from a clean checkout and confirm every stated pin
matches the manifests, the seeding decision is explicit, and the verification and rollback steps are
reproducible.

**Acceptance Scenarios**:

1. **Given** the change is complete, **When** the operator reads the dashboard documentation,
   **Then** the bus backend pin is 0.4.0 and the prior OOM caveat is updated to reflect the verified
   outcome.
2. **Given** the change is complete, **When** the operator reads the Home Assistant documentation,
   **Then** the image pin, seeding decision, manual integration steps, and verification are current.
3. **Given** the repository is validated, **When** the standard manifest validation is run, **Then**
   the changed apps render and pass strict schema validation.
4. **Given** the documentation is reviewed, **When** the public repository is scanned, **Then** no
   secrets, tokens, tailnet identifiers, or private state have been added.

### Edge Cases

- bus-catcher 0.4.0 still exceeds the memory limit during a full GTFS refresh; the increase or
  out-of-cluster ingest fallback must remain documented instead of silently failing.
- The new bus version needs a database schema migration or refuses the existing database; the
  operator must detect it before declaring success and document the recovery path.
- The upstream bus feed is unchanged, so no re-ingest occurs; freshness must be judged from the
  status timestamps rather than assuming a refresh happened.
- Automatic schedule refresh is disabled or misconfigured; the deployed defaults must be verified
  and documented.
- Only one of the two bus workloads is updated, leaving REST and MCP on different versions or
  incompatible database expectations.
- The new Home Assistant tag is not selected by image automation; the operator must be able to pin it
  explicitly and explain why.
- The seed copies new tracked files but does not delete removed tracked files; stale files must not
  break Home Assistant startup.
- A new tracked automation references an entity or device that does not exist in the household state;
  the failure must be visible and documented, not hidden.
- The persistent volume is full or nearly full before the rollout; state preservation and startup
  must be checked before and after.
- The custom integration requires a config entry or pipeline selection that lives only in
  `.storage`; omitting that manual step must leave Home Assistant running with the capability simply
  unavailable.
- The new image cannot be pulled publicly; the failure must be visible and the documented
  remediation must apply.
- A manual `kubectl` change is reverted by Flux; only Git changes are supported.
- The node reboots during or after the rollout; both workloads must return to Ready and data must
  survive.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Both bus-catcher workloads (REST and MCP) MUST use the same 0.4.0 image reference.
- **FR-002**: All Home Assistant image references (seed, restore, HTTP configuration, and main
  container) MUST use `main-20261109193052-7e131ee` and MUST keep their image update markers.
- **FR-003**: The image references MUST remain immutable tags; `latest` MUST NOT be used.
- **FR-004**: The change MUST be delivered through the existing Flux-managed app Kustomizations,
  without manual `kubectl` changes as the permanent state.
- **FR-005**: After reconciliation, both bus workloads MUST become Ready and pass their existing
  health and port probes.
- **FR-006**: The operator MUST verify that bus-catcher 0.4.0 completes a schedule load or refresh
  without an OOMKill and with the configured resource limits.
- **FR-007**: The operator MUST verify that REST and MCP read consistent bus data from the shared
  persisted database and that only one process ingests at a time.
- **FR-008**: The operator MUST verify that bus data persists across a pod restart after the upgrade.
- **FR-009**: After the Home Assistant rollout, the new tracked configuration MUST be present under
  `/config`, including the custom integration.
- **FR-010**: The rollout MUST preserve `.storage`, the recorder database, secrets, and Zigbee state.
- **FR-011**: The repository MUST record an evidence-based decision on whether Home Assistant needed
  a separate seed, state-bundle upload, or manual file copy, including what was checked.
- **FR-012**: The operator MUST verify that Home Assistant becomes Ready, loads its automations, and
  makes the new integration available without requiring a destructive state reset.
- **FR-013**: The repository documentation MUST state the exact bus-catcher and Home Assistant image
  pins after the change.
- **FR-014**: The documentation MUST describe the bus-catcher 0.4.0 behavior change, the Home
  Assistant seeding outcome, the verification performed, and the rollback steps.
- **FR-015**: The changed manifests MUST render and pass strict schema validation before
  reconciliation.
- **FR-016**: No secrets, tokens, tailnet identifiers, private state, databases, or backups MUST be
  introduced into Git.
- **FR-017**: The operator MUST be able to revert either workload to its previous image pin through
  Git and recover the previous Ready state.

### Key Entities *(include if feature involves data)*

- **Workload image pin**: The exact immutable image reference used by a workload; bus-catcher has
  two pins that must move together, and Home Assistant has four references that must stay in lockstep.
- **Bus schedule data**: The persisted GTFS-derived dataset and its freshness metadata, shared by the
  REST and MCP workloads.
- **Home Assistant tracked configuration**: Files baked into the image and copied to `/config` by the
  seed step, including YAML and the custom integration.
- **Home Assistant runtime state**: Private state on the persistent volume (`.storage`, recorder
  database, secrets, Zigbee state) that must survive the image change.
- **Seeding decision record**: The documented conclusion about whether the existing state needed to be
  re-seeded and the evidence that supports it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Both bus workloads run 0.4.0 and reach Ready within 10 minutes of reconciliation.
- **SC-002**: A bus schedule load or refresh completes with zero OOMKills, and the reported schedule
  freshness advances past the previously stale data.
- **SC-003**: REST and MCP return consistent bus data, and no concurrent-ingest failure is observed
  during the upgrade verification.
- **SC-004**: Bus data remains available after a pod restart, with no loss of the persisted dataset.
- **SC-005**: Home Assistant runs the new image, reaches Ready, and 100% of the pre-upgrade private
  state (`.storage`, database, secrets, Zigbee state) remains present.
- **SC-006**: The new tracked configuration, including the custom integration, is confirmed present
  under `/config` after the rollout.
- **SC-007**: The seeding decision is recorded with the checks performed, so another operator can
  reproduce the same conclusion in under 10 minutes.
- **SC-008**: Documentation states the exact resulting pins and the verification and rollback steps,
  with zero stale version references in the affected documents.
- **SC-009**: Manifest validation passes for every changed app with no secret findings.
- **SC-010**: Either workload can be rolled back to its previous pin and return to Ready within 10
  minutes.

## Assumptions

- The 0.4.0 bus-catcher and `main-20261109193052-7e131ee` Home Assistant images are published publicly
  in GHCR and are pullable by the cluster without credentials.
- The new Home Assistant image is built from the `7e131ee` configuration commit, whose tracked changes
  are configuration and a custom integration rather than runtime state.
- The existing Home Assistant seed init container copies new tracked files into `/config` on every
  pod start and does not delete untracked files, so new tracked configuration should arrive through
  the normal rollout. This is the expected answer to the seeding question and MUST be verified rather
  than assumed in the final record.
- No separate state-bundle upload is expected because the change does not intentionally modify
  unsynced household state; if verification shows otherwise, the documented state-bundle procedure
  applies.
- The new custom integration may still require an operator UI step to create its config entry and to
  select it as the Assist conversation agent; those values live in `.storage` and are outside Git.
- bus-catcher 0.4.0 is database-compatible with the existing bus database or performs its own
  forward migration; this MUST be verified during rollout.
- The cluster and Flux are healthy, and the existing resource limits remain appropriate until the
  memory-bounded refresh proves otherwise.
- The existing automations added to tracked configuration reference entities and devices that are
  already present in the household state.
- The previous image pins remain published so rollback is possible.
