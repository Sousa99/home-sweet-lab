---

description: "Task list for workload image updates"
---

# Tasks: Workload Image Updates

**Input**: Design documents from `/specs/007-update-workload-images/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: No new automated tests are requested. Verification is performed against the live cluster
using the observable checks in `contracts/runtime-verification.md`.

**Organization**: Tasks are grouped by user story so each image update can be implemented and
verified independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Every task includes the exact file path or referenced runbook it operates on

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the target artifacts exist and capture the pre-change baseline.

- [X] T001 [P] Verify both target images resolve publicly in GHCR and the previous tags remain available, following `specs/007-update-workload-images/quickstart.md`
- [X] T002 [P] Capture the current bus and Home Assistant image pins, bus `lastRefresh`/`feedVersion`, and Home Assistant runtime-state listing per `specs/007-update-workload-images/quickstart.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Confirm the GitOps baseline is healthy before changing pins.

**⚠️ CRITICAL**: No user story work should begin until this phase is complete.

- [ ] T003 [P] Confirm the `apps` Flux Kustomization is Ready and `bus-catcher-data` and `home-assistant-config` PVCs are Bound using `specs/007-update-workload-images/contracts/runtime-verification.md`
- [X] T004 [P] Run `./scripts/validate.sh` to establish a passing pre-change baseline for `apps/` and `infrastructure/`

**Checkpoint**: The cluster and repository are ready; US1 and US2 can proceed independently.

---

## Phase 3: User Story 1 - Upgrade bus-catcher to 0.4.0 across REST and MCP (Priority: P1) 🎯 MVP

**Goal**: Move both bus workloads to 0.4.0 and prove the schedule refresh succeeds without OOMKill,
REST and MCP stay consistent, and data survives a pod restart.

**Independent Test**: After reconciling both bus Deployments at 0.4.0, confirm both pods Ready, force
a schedule refresh, confirm freshness advances with no OOMKill, initialize the MCP server, and
confirm data remains after deleting the REST pod.

### Implementation for User Story 1

- [X] T005 [P] [US1] Change the bus REST image from `0.3.0` to `0.4.0` in `apps/dashboard/bus-catcher-rest.yaml`
- [X] T006 [P] [US1] Change the bus MCP image from `0.3.0` to `0.4.0` in `apps/dashboard/bus-catcher-mcp.yaml`
- [X] T007 [US1] Render `apps/dashboard` with `kubectl kustomize` and confirm both bus Deployments reference `0.4.0` and no other fields changed, per `specs/007-update-workload-images/quickstart.md`
- [ ] T008 [US1] Commit both bus pin changes, reconcile Flux, and wait for `bus-catcher-rest` and `bus-catcher-mcp` rollouts using `specs/007-update-workload-images/quickstart.md`
- [ ] T009 [US1] Verify the running pod images, REST `/api/health`, and MCP readiness per `specs/007-update-workload-images/contracts/runtime-verification.md`
- [ ] T010 [US1] Force a bus refresh with `POST /api/refresh?force=true`, poll `/api/status` until complete, and confirm `lastRefresh` advances with no `OOMKilled` per `specs/007-update-workload-images/contracts/runtime-verification.md`
- [ ] T011 [US1] Initialize the bus MCP server and compare a configured stop between REST and MCP, confirming no concurrent-ingest or database-lock error per `specs/007-update-workload-images/contracts/runtime-verification.md`
- [ ] T012 [US1] Delete the `bus-catcher-rest` pod, wait for replacement, and confirm `lastRefresh`, `feedVersion`, and configured stops persist per `specs/007-update-workload-images/contracts/runtime-verification.md`
- [ ] T013 [US1] Verify the dashboard proxy path `/api/bus/api/health` still returns `200` per `specs/007-update-workload-images/contracts/runtime-verification.md`

**Checkpoint**: bus-catcher 0.4.0 is independently deployed, refreshed, consistent, and persistent.

---

## Phase 4: User Story 2 - Roll out the new Home Assistant image and settle the seeding question (Priority: P1)

**Goal**: Roll out `main-20261109193052-7e131ee`, prove the normal seed installs the new tracked
configuration, preserve all runtime state, and record whether any separate seeding was required.

**Independent Test**: After the Home Assistant rollout, confirm all init containers succeed, the new
custom component and automations exist under `/config`, `.storage`/database/secrets/Zigbee state are
preserved, and Home Assistant is Ready with the integration available.

### Implementation for User Story 2

- [X] T014 [US2] Change all four Home Assistant image references to `main-20261109193052-7e131ee` in `apps/home-assistant/deployment.yaml`, preserving every image marker
- [X] T015 [US2] Render `apps/home-assistant` and confirm all four references use the new tag and retain `# {"$imagepolicy": "flux-system:home-assistant"}`, per `specs/007-update-workload-images/quickstart.md`
- [ ] T016 [US2] Commit the Home Assistant pin change, reconcile Flux, and wait for the `home-assistant` rollout using `specs/007-update-workload-images/quickstart.md`
- [ ] T017 [US2] Inspect the `seed-config`, `restore-state`, and `configure-http` init-container logs and confirm all exit `0` with no newly applied bundle per `specs/007-update-workload-images/contracts/runtime-verification.md`
- [ ] T018 [P] [US2] Verify the custom component files and new automations exist under `/config` per `specs/007-update-workload-images/contracts/runtime-verification.md`
- [ ] T019 [P] [US2] Verify `.storage/core.config_entries`, `zigbee.db`, the recorder database, and `secrets.yaml` presence match the pre-change baseline per `specs/007-update-workload-images/contracts/runtime-verification.md`
- [ ] T020 [US2] Verify Home Assistant readiness, `/manifest.json`, and that the `Home Sweet Home Agent` integration is available without a destructive state reset per `specs/007-update-workload-images/contracts/runtime-verification.md`
- [ ] T021 [US2] Record the evidence-based seeding conclusion and any remaining manual integration/Assist pipeline steps in `docs/06-home-assistant.md`

**Checkpoint**: Home Assistant runs the new image with preserved state, and the seeding question is answered with evidence.

---

## Phase 5: User Story 3 - Keep deployment documentation and pins truthful (Priority: P2)

**Goal**: Make the repository documentation match the verified pins, behavior, seeding result, and
rollback path.

**Independent Test**: Read the affected docs from a clean checkout and confirm every pin matches the
manifests, the seeding decision is explicit, the bus OOM caveat is resolved, and no stale version
references remain.

### Implementation for User Story 3

- [ ] T022 [P] [US3] Update the bus pin, resolved OOM outcome, refresh behavior, and 10 GiB memory-limit text in `docs/13-dashboard.md`
- [ ] T023 [P] [US3] Update the current image pin, verification date, and seed decision summary in `docs/06-home-assistant.md`
- [X] T024 [US3] Cross-check `docs/06-home-assistant.md` and `docs/13-dashboard.md` against `apps/dashboard/bus-catcher-*.yaml` and `apps/home-assistant/deployment.yaml` for stale pins or contradictory statements
- [ ] T025 [US3] Run `./scripts/validate.sh` and commit the documentation updates for `docs/06-home-assistant.md` and `docs/13-dashboard.md`

**Checkpoint**: Documentation is reproducible from a clean checkout and matches the deployed pins.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final safety checks and recovery validation across both stories.

- [ ] T026 [P] Review the full repository diff for secrets, tailnet identifiers, private state, and unrelated changes using `specs/007-update-workload-images/contracts/runtime-verification.md`
- [ ] T027 Exercise the rollback drill for both bus workloads and Home Assistant, then restore the new pins, per `specs/007-update-workload-images/contracts/runtime-verification.md`
- [ ] T028 Re-run `./scripts/validate.sh` on the final tree and record the passing result in `specs/007-update-workload-images/tasks.md`
- [ ] T029 Verify every success criterion SC-001 through SC-010 in `specs/007-update-workload-images/spec.md` against the recorded evidence and note any exception

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; T001 and T002 can run in parallel.
- **Foundational (Phase 2)**: Depends on Phase 1; T003 and T004 can run in parallel. Blocks US1 and US2.
- **User Story 1 (Phase 3)**: Depends on Phase 2. Can run in parallel with US2.
- **User Story 2 (Phase 4)**: Depends on Phase 2. Can run in parallel with US1.
- **User Story 3 (Phase 5)**: Depends on US1 and US2 because it records their observed results.
- **Polish (Phase 6)**: Depends on all user stories.

### User Story Dependencies

- **US1 (P1)**: Independent. No dependency on US2.
- **US2 (P1)**: Independent. No dependency on US1.
- **US3 (P2)**: Depends on the evidence produced by US1 and US2.

### Within Each User Story

- US1: edit both manifests in parallel (T005, T006), then render (T007), reconcile (T008), and verify
  in dependency order: health (T009) → refresh (T010) → MCP consistency (T011) → persistence (T012)
  → proxy (T013).
- US2: edit the single Deployment (T014), render (T015), reconcile (T016), then verify init logs
  (T017), tracked config (T018), state preservation (T019), readiness/integration (T020), and record
  the decision (T021).
- US3: update the two docs in parallel (T022, T023), then cross-check (T024), validate, and commit
  (T025).

### Parallel Opportunities

- T001 and T002 (independent baseline checks).
- T003 and T004 (independent readiness checks).
- T005 and T006 (different manifest files).
- US1 and US2 phases can run concurrently on separate branches or by separate operators.
- T018 and T019 (independent read-only Home Assistant checks).
- T022 and T023 (different documentation files).
- T026 is independent of T027/T028 once the implementation is complete.

---

## Parallel Example: User Story 1

```bash
# Edit both bus manifests together:
Task: "Change the bus REST image from 0.3.0 to 0.4.0 in apps/dashboard/bus-catcher-rest.yaml"
Task: "Change the bus MCP image from 0.3.0 to 0.4.0 in apps/dashboard/bus-catcher-mcp.yaml"
```

## Parallel Example: User Story 2

```bash
# After the rollout, run independent read-only checks together:
Task: "Verify custom component and automations under /config"
Task: "Verify runtime state matches the pre-change baseline"
```

## Parallel Example: User Story 3

```bash
# Update both documentation files together:
Task: "Update docs/13-dashboard.md"
Task: "Update docs/06-home-assistant.md"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational.
3. Complete Phase 3: User Story 1.
4. **STOP and VALIDATE**: bus-catcher 0.4.0 refreshes without OOMKill and data persists.
5. Deploy/demo the restored bus capability.

### Incremental Delivery

1. Complete Setup + Foundational → baseline confirmed.
2. Add US1 → verify bus refresh and persistence → deploy.
3. Add US2 → verify Home Assistant seed and state preservation → deploy.
4. Add US3 → update documentation and revalidate.
5. Complete Polish → rollback drill, final validation, success-criteria review.

### Parallel Team Strategy

1. One operator completes Setup + Foundational.
2. Operator A: US1 bus-catcher.
3. Operator B: US2 Home Assistant.
4. After both, one operator completes US3 documentation and Polish.

---

## Notes

- [P] tasks touch different files or are read-only and independent.
- No automated test tasks are included because the feature is a configuration change; the live
  verification contract is the test suite.
- Commit after each logical group: bus pins, Home Assistant pin, bus evidence docs, Home Assistant
  evidence docs.
- Do not use `kubectl set image` as the permanent state; Flux remains the source of truth.
- Stop at each checkpoint and verify the workload independently before proceeding.

---

## Implementation Status (2026-11-09)

Completed locally:

- T001, T002, T004: target images verified public, baseline captured, and `./scripts/validate.sh`
  passed before and after the manifest edits.
- T005-T007: both bus Deployments render with `bus-catcher-backend:0.4.0`.
- T014-T015: all four Home Assistant references render with
  `main-20261109193052-7e131ee` and retain their image markers.
- Partial T022-T023: declared pins, refresh behavior, memory-limit text, and the expected seeding
  behavior are updated. The verification outcome remains pending.
- T024: documentation cross-check completed; no stale declared pins remain.

Blocked at T003 and therefore T008-T013, T016-T021, T025-T029:

- The `apps` Flux Kustomization is not Ready because the `infrastructure` Kustomization is not ready.
- All Flux controllers are in `CrashLoopBackOff` and report that the Kubernetes API at
  `10.43.0.1:443` refuses connections. The source controller also reports a DNS failure resolving
  `github.com`.
- No commit, push, reconciliation, rollout, or live image verification was performed. The cluster is
  still running the previous images.
- After Flux recovers, rerun `/speckit.implement` or execute `quickstart.md` from step 4 and replace
  the pending verification paragraphs in `docs/06-home-assistant.md` and `docs/13-dashboard.md`.
