# Phase 1 Data Model: Workload Image Updates

This feature adds no persistent data structures. It changes image references and verifies the state
that already exists on two volumes. The entities below describe the configuration and runtime state
that the implementation must update, preserve, or record.

## Workload Image Pin

**Represents**: The exact immutable image reference consumed by a workload.

**Fields**:

| Field | Description | Validation |
| ----- | ----------- | ---------- |
| `workload` | Deployment name (`bus-catcher-rest`, `bus-catcher-mcp`, `home-assistant`) | Must match an existing Deployment |
| `manifestPath` | Repository file that owns the reference | Must be under `apps/` |
| `currentImage` | Image reference before the change | Must resolve in GHCR |
| `targetImage` | Image reference after the change | Must resolve in GHCR; no `latest` |
| `imageMarker` | Flux setter marker, where present | Present on all four Home Assistant references; absent for bus-catcher |
| `pairedPins` | Other references that must move together | Bus REST/MCP pair; Home Assistant init and main containers |

**Relationships**:

- One bus workload image pin is shared by the REST and MCP Deployments.
- Four Home Assistant references (seed, restore, HTTP configuration, main container) form one
  lockstep pin set.
- A rollback restores the previous pin values.

**Validation rules**:

- The bus REST and MCP references must be identical.
- All Home Assistant references must be identical and must retain
  `# {"$imagepolicy": "flux-system:home-assistant"}`.
- The target tags must be publicly pullable and must not be mutable aliases.

## Bus Schedule State

**Represents**: The persisted GTFS-derived dataset and refresh metadata shared by the bus REST and
MCP processes.

**Fields**:

| Field | Description | Validation |
| ----- | ----------- | ---------- |
| `database` | SQLite file on `bus-catcher-data` at `/data/bus-catcher.db` | Survives pod replacement |
| `feedVersion` | Identifier of the last ingested upstream feed | Unchanged feed is not re-ingested |
| `lastRefresh` | Timestamp of the last successful ingest | Advances past the pre-upgrade stale value |
| `stale` | Whether the schedule is considered stale | Becomes false after a successful refresh |
| `refreshError` | Last refresh failure, if any | Null or absent after a successful refresh |
| `ingestLock` | Cross-process lock protecting ingestion | Held by at most one process at a time |
| `configuredStops` | Household stop list and thresholds | Preserved across the feed replace |

**State transitions**:

```text
empty/idle
  └─ startup (REST) ──▶ downloading ──▶ ingested (fresh) ──▶ periodic check
                                  └────▶ skipped (unchanged feed)
                                  └────▶ error (refreshError set, old data retained)

any state ──▶ forced refresh ──▶ downloading ──▶ ingested | error
```

**Validation rules**:

- Only the REST process auto-ingests; MCP triggers refreshes through its tool or the REST process.
- A forced refresh must not cause an OOMKill under the existing 10 GiB limit.
- A refresh must not discard `configuredStops`.
- A failed refresh must leave the previous dataset readable and set `refreshError` rather than
  corrupting the database.

## Home Assistant Tracked Configuration

**Represents**: Files baked into the Home Assistant image and copied into `/config` by the seed init
container.

**Fields**:

| Field | Description | Validation |
| ----- | ----------- | ---------- |
| `imagePath` | `/config-seed/` inside the image | Populated by the image build |
| `targetPath` | `/config/` on the PVC | Written by `seed-config` on every pod start |
| `trackedYaml` | `configuration.yaml`, `automations.yaml`, and related tracked files | Present after the rollout |
| `customComponent` | `/config/custom_components/home_sweet_home_agent/` | Present after the rollout, including `manifest.json` and `conversation.py` |
| `removedFiles` | Tracked files removed upstream | Seed does not delete them; must not break startup |

**Relationships**:

- The tracked configuration is the input to the seed step.
- The seed step writes into the same PVC that holds runtime state, without deleting untracked files.
- The custom component becomes available to Home Assistant but is inert until a config entry exists.

**Validation rules**:

- New tracked files must appear under `/config` after the pod restarts.
- The custom component files must be present and readable.
- No tracked file may overwrite `.storage`, databases, secrets, or Zigbee state.

## Home Assistant Runtime State

**Represents**: Private state that must survive the image change and is never committed.

**Fields**:

| Field | Description | Validation |
| ----- | ----------- | ---------- |
| `.storage` | Integration credentials, entity registry, UI state, HTTP proxy settings, Assist pipeline selection | Present before and after the rollout |
| `home-assistant_v2.db` | Recorder database | Present and usable after the rollout |
| `secrets.yaml` | Optional `!secret` values | Preserved if present |
| `zigbee.db` | Zigbee network state | Preserved and updated by Home Assistant |
| `media/`, `tts/`, `www/community/` | Private assets | Preserved |
| `backups/` | Home Assistant backup archives | Preserved; not in Git |

**Relationships**:

- Runtime state depends on the PVC and is independent of the image tag.
- The custom integration config entry and Assist pipeline selection live inside `.storage`.
- A state bundle is only for moving state between hosts or recovering; it is not part of this image
  update.

**Validation rules**:

- Existence and readability must be checked before and after the rollout.
- No state file is uploaded, downloaded, copied manually, or committed as part of this feature.

## Seeding Decision Record

**Represents**: The evidence-based answer to whether Home Assistant needed to be seeded.

**Fields**:

| Field | Description | Validation |
| ----- | ----------- | ---------- |
| `question` | Whether the new image needs a separate seed or state operation | Explicitly stated |
| `checksPerformed` | Commands and observations used to decide | Reproducible from the quickstart |
| `conclusion` | `seed-init-only`, `state-bundle-required`, or `manual-copy-required` | Supported by the checks |
| `manualSteps` | Any UI steps that remain, such as the integration config entry and pipeline selection | Documented |
| `recordedIn` | Documentation file that carries the decision | `docs/06-home-assistant.md` |

**Validation rules**:

- The conclusion must be based on observed files and logs, not on assumption.
- If the conclusion is "seed-init-only", the record must state that no bundle upload was performed.
- Manual `.storage` steps must be listed separately from the seed decision.

## Rollout Evidence

**Represents**: The cluster observations that prove the change succeeded or identify a rollback.

**Fields**:

| Field | Description | Validation |
| ----- | ----------- | ---------- |
| `rolloutStatus` | Deployment availability after reconciliation | Both bus workloads and Home Assistant Ready |
| `podImages` | Image actually running in each pod | Match the committed pins |
| `busHealth` | REST health and MCP initialize result | Both succeed |
| `busRefresh` | Refresh result, freshness, and whether an OOMKill occurred | Successful and no OOMKill |
| `persistenceCheck` | Data still present after a pod restart | Bus data and Home Assistant state preserved |
| `validationResult` | `scripts/validate.sh` outcome | Passed |

**Validation rules**:

- Pod image identity must be confirmed from the cluster, not inferred from the manifest.
- Any OOMKill, missing state file, or failed readiness is a rollback trigger or a documented
  exception with a recovery step.
