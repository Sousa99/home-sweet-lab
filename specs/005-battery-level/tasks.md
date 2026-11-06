# Tasks: Battery Level Percentage

**Input**: Design documents from `/specs/005-battery-level/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Included because FR-012 explicitly requires unit tests for level collection, projections,
and absent-level behavior.

**Organization**: Tasks are grouped by user story so each increment is independently testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Every task names an exact file path or command

## Path Conventions

- Exporter code and tests: `apps/host-metrics/`
- MQTT broker config: `apps/host-metrics/mqtt/`
- Operator docs: `docs/`
- Feature design: `specs/005-battery-level/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the baseline and that no new host or deployment surface is needed.

- [X] T001 Run the baseline exporter tests before changes with `python -m unittest discover -s apps/host-metrics -p 'test_*.py'` and record the passing result.
- [X] T002 [P] Inspect `apps/host-metrics/deployment.yaml` and confirm the existing read-only `/host/sys` mount already exposes `power_supply/*/capacity`; no manifest change is required.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add the optional battery level to the shared runtime model and flat JSON used by both
HTTP and MQTT. No user story can be completed until this phase is done.

**⚠️ CRITICAL**: User story work starts only after this phase.

- [X] T003 Add failing tests in `apps/host-metrics/test_exporter.py` for `BatteryReading.level_percent` and `collect_batteries` reading `capacity`: readable value, missing file, non-numeric value, out-of-range numeric value, and the `0`/`100` boundaries.
- [X] T004 Implement optional `level_percent` and `level_path` on `BatteryReading` and read/validate `capacity` in `collect_batteries` in `apps/host-metrics/exporter.py`; keep status-required battery selection unchanged.
- [X] T005 Add failing tests in `apps/host-metrics/test_exporter.py` for `render_ha` output: preferred `battery_level_percent`, per-battery `level_percent`, and null values when the level is absent.
- [X] T006 Implement the flat JSON additions in `render_ha` in `apps/host-metrics/exporter.py`, preserving every existing key and type.

**Checkpoint**: The shared model and JSON contract are ready; US1 and US2 can proceed.

---

## Phase 3: User Story 1 - See battery percentage in Home Assistant (Priority: P1) 🎯 MVP

**Goal**: Publish a seventh MQTT discovery entity and allow the broker so Home Assistant shows
`Battery level` on the existing `home-sweet-lab-server` device.

**Independent Test**: Reconcile the exporter and broker, inspect retained discovery/state, and
confirm `sensor.home_sweet_lab_server_battery_level` exists and updates with the host percentage.

### Tests for User Story 1 ⚠️

- [X] T007 [US1] Update `apps/host-metrics/test_mqtt_publisher.py` with failing discovery tests: seven messages, the `home_sweet_lab_server_battery_level` topic, and the expected unit, device class, state class, icon, value template, and battery availability.

### Implementation for User Story 1

- [X] T008 [US1] Add the `battery_level` sensor entry to `SENSORS` in `apps/host-metrics/mqtt_discovery.py` with name `Battery level`, unit `%`, device class `battery`, state class `measurement`, icon `mdi:battery`, and `{{ value_json.battery_level_percent }}`.
- [X] T009 [US1] Add the exporter write and Home Assistant read ACL entries for `homeassistant/sensor/home_sweet_lab_server_battery_level/config` in `apps/host-metrics/mqtt/configmap.yaml`.

**Checkpoint**: US1 is functional; the device has seven entities and the battery level appears in Home Assistant.

---

## Phase 4: User Story 2 - Use battery level from the HTTP exporter (Priority: P2)

**Goal**: Expose `host_battery_level_percent` from `/metrics` while the flat JSON from `/ha` already
carries the level from the foundational phase.

**Independent Test**: Query `/metrics` and `/ha` and confirm a battery-level series per readable
battery and the preferred/per-battery JSON keys.

### Tests for User Story 2 ⚠️

- [X] T010 [US2] Add failing tests in `apps/host-metrics/test_exporter.py` for `host_battery_level_percent` presence on a readable battery and omission for a status-only battery, while `host_battery_status_info` and `host_metrics_battery_available` remain unchanged.

### Implementation for User Story 2

- [X] T011 [US2] Implement the `host_battery_level_percent{device,path}` gauge family in `render_metrics` in `apps/host-metrics/exporter.py`, using the capacity path and omitting devices without a level.

**Checkpoint**: US2 is functional; the HTTP metric and JSON reflect the battery level without touching the MQTT path.

---

## Phase 5: User Story 3 - Stay usable when a battery cannot report its level (Priority: P3)

**Goal**: Guarantee that missing batteries or levels degrade only the affected value and never
readiness, status behavior, or other host metrics.

**Independent Test**: Run the exporter against no-battery, status-only, unreadable-level,
multiple-battery, and boundary fixtures; confirm unaffected metrics and availability.

### Tests for User Story 3 ⚠️

- [X] T012 [US3] Add failing degradation tests in `apps/host-metrics/test_exporter.py` for no battery, a status-only battery, multiple batteries, absent/unreadable `capacity`, and unchanged `/readyz` behavior.

### Implementation for User Story 3

- [X] T013 [US3] Adjust `collect_batteries`, `render_metrics`, and `render_ha` in `apps/host-metrics/exporter.py` as needed so a missing level is null/omitted, a real `0%` is preserved, and battery status plus readiness behavior are unchanged.
- [X] T014 [P] [US3] Add availability regression tests in `apps/host-metrics/test_mqtt_publisher.py` confirming battery availability still derives from readable status and a missing level does not change the battery availability topic.

**Checkpoint**: All three stories work together; degraded hosts keep every unrelated metric.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Align the operator documentation and run full validation.

- [X] T015 [P] Update `docs/11-host-metrics.md`: add `host_battery_level_percent` to the metric tables, add `battery_level_percent` and per-battery `level_percent` to the `/ha` key list, and describe absence behavior.
- [X] T016 [P] Update `docs/12-host-metrics-mqtt.md`: change the device from six to seven entities, add the battery-level entity row, and document missing-level recovery.
- [X] T017 [P] Update `docs/09-limitations.md` to remove the "battery percentage out of scope" limitation and state the new supported behavior.
- [X] T018 [P] Review `specs/005-battery-level/contracts/battery-level-additions.md` against the implemented metric labels, JSON keys, discovery metadata, and ACL entries; fix any mismatch.
- [X] T019 Run full validation: `python -m unittest discover -s apps/host-metrics -p 'test_*.py'`, `kubectl kustomize apps/host-metrics`, and `kubeconform -strict -summary apps/host-metrics`.
- [X] T020 Run the `specs/005-battery-level/quickstart.md` cluster checks: Flux reconciliation, `/metrics`, `/ha`, `/readyz`, seven MQTT discovery messages, state keys, and the Home Assistant entity.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; T002 is parallel.
- **Foundational (Phase 2)**: Depends on Setup; blocks US1 and US2.
- **US1 (Phase 3)**: Depends on Foundational; no dependency on US2.
- **US2 (Phase 4)**: Depends on Foundational; no dependency on US1.
- **US3 (Phase 5)**: Depends on Foundational plus US1 (availability path) and US2 (metric omission).
- **Polish (Phase 6)**: Depends on all desired stories.

### Story Dependencies

- **US1 (P1)**: Independent after Foundational; delivers the MVP Home Assistant entity.
- **US2 (P2)**: Independent after Foundational; delivers the HTTP metric.
- **US3 (P3)**: Integrates US1 and US2 because it validates both availability and metric omission.

### Within Each Story

- Write failing tests before implementation (T003 → T004, T005 → T006, T007 → T008, T010 → T011, T012/T014 → T013).
- Keep `apps/host-metrics/exporter.py` edits sequential: T004 → T006 → T011 → T013.
- Keep `apps/host-metrics/test_exporter.py` edits sequential: T003 → T005 → T010 → T012.
- T009 is independent of code files and can follow T008.

### Parallel Opportunities

- T002 runs while baseline tests run.
- T014 can run in parallel with T012/T013 because it edits `test_mqtt_publisher.py`.
- T015, T016, T017, and T018 edit different documentation/contract files and can run together.
- After Foundational, US1 and US2 can be assigned to different people; US3 follows both.

---

## Parallel Example: Documentation

```text
Task: "Update docs/11-host-metrics.md metric tables"
Task: "Update docs/12-host-metrics-mqtt.md entity table"
Task: "Update docs/09-limitations.md battery limitation"
Task: "Review specs/005-battery-level/contracts/battery-level-additions.md"
```

## Parallel Example: User Story 3 tests

```text
Task: "Add degradation tests in apps/host-metrics/test_exporter.py"
Task: "Add availability regression tests in apps/host-metrics/test_mqtt_publisher.py"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Complete Phase 1 (Setup).
2. Complete Phase 2 (Foundational model and flat JSON).
3. Complete Phase 3 (US1 discovery, ACL).
4. **STOP and VALIDATE**: Inspect seven retained discovery messages and confirm the Home Assistant
   battery-level entity updates.

### Incremental Delivery

1. Foundational + US1 → Home Assistant shows the battery percentage (MVP).
2. Add US2 → `/metrics` exposes `host_battery_level_percent`.
3. Add US3 → degraded battery cases are covered by tests and preserve all other metrics.
4. Polish → docs and contract match the shipped behavior; run quickstart on the cluster.

### Notes

- Every `[P]` task edits a different file from its parallel peers.
- Tests are required by FR-012 and run in the existing standard-library `unittest` suite.
- No new dependency, image, Secret, or Deployment change is expected.
- Do not commit; implementation and verification only unless the user asks.
