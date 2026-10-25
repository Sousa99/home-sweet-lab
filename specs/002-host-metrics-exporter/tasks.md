---
description: "Task list for the host-metrics exporter and Home Assistant integration"
---

# Tasks: Host Metrics Exporter and Home Assistant Integration

**Input**: Design documents from `specs/002-host-metrics-exporter/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: Unit tests are included because `plan.md` and `quickstart.md` require fixture-based
verification of the parsers, metric names, JSON keys, battery status selection, and absence
behavior. The cluster verification tasks exercise the deployed workload.

**Organization**: Tasks are grouped by user story so each story has an independently testable
increment. The Home Assistant UI work itself is performed manually by the operator; the repository
tasks prepare and verify the documented handoff.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: `[US1]`, `[US2]`, or `[US3]`
- Every task includes an exact repository path or the procedure/contract file it operates on

## Path Conventions

This repository is a GitOps infrastructure repository. The workload lives under
`apps/host-metrics/`, operator documentation under `docs/`, and design artifacts under
`specs/002-host-metrics-exporter/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the workload directory and register it with the existing Flux app entry point.

- [X] T001 Create the `monitoring` namespace manifest in `apps/host-metrics/namespace.yaml` with the project labels used by the other workloads.
- [X] T002 Add `host-metrics` to the resources list in `apps/kustomization.yaml` so the existing Flux `apps` Kustomization reconciles it.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the shared exporter runtime and validation wiring that all user stories depend on.

**⚠️ CRITICAL**: T003–T005 must be complete before the collector and manifest tasks in User Story 1.

- [X] T003 Implement the exporter foundation in `apps/host-metrics/exporter.py`: configuration constants for `/host/proc/meminfo`, `/host/proc/1/net`, `/host/sys`, and `/host/root`; snapshot/reading data structures for temperature, memory, storage, IPv4, and battery; safe file-read helpers; the HTTP server; `/healthz`; `/readyz`; logging; and the process entry point.
- [X] T004 [P] Extend `scripts/validate.sh` to run `python3 -m unittest discover -s apps/host-metrics -p 'test_*.py'` after manifest validation, with a clear skip message when `python3` is unavailable.
- [X] T005 [P] Create `apps/host-metrics/kustomization.yaml` with `namespace.yaml`, `deployment.yaml`, and `service.yaml` resources plus a `configMapGenerator` named `host-metrics-script` for `exporter.py`.

**Checkpoint**: The exporter runtime skeleton, validation hook, and Kustomize entry point exist.

---

## Phase 3: User Story 1 - Deploy and verify the exporter (Priority: P1) 🎯 MVP

**Goal**: Deploy the exporter and ClusterIP Service through Flux, verify the pod is Ready on
`dietpi`, and prove the documented metrics endpoint is reachable from the `home-assistant`
namespace.

**Independent Test**: Reconcile the app from Git, confirm the pod is Ready on `dietpi`, and read
`/metrics`, `/ha`, and `/readyz` from a pod in the `home-assistant` namespace. No Home Assistant UI
work is required.

### Tests for User Story 1

> Write T006 before T007–T013. It should fail until the collectors and renderers exist.

- [X] T006 [US1] Add fixture-based unit tests in `apps/host-metrics/test_exporter.py` for meminfo parsing, root filesystem usage, hwmon and thermal-zone selection, fib-trie extraction, route-to-interface mapping, power-supply battery selection, usage math, the exact metric names/labels/units from `contracts/exporter-api.md`, the exact `/ha` keys, and the absent-temperature/absent-battery/unreadable-status paths.

### Implementation for User Story 1

- [X] T007 [US1] Implement memory and root filesystem collection in `apps/host-metrics/exporter.py` using `/host/proc/meminfo` and `statvfs("/host/root")`, including the documented `MemAvailable` fallback and `used = total - available` usage formulas.
- [X] T008 [US1] Implement hwmon and thermal-zone temperature collection in `apps/host-metrics/exporter.py`, including preferred-sensor selection and the documented Celsius conversion.
- [X] T009 [US1] Implement IPv4 collection in `apps/host-metrics/exporter.py` from `/host/proc/1/net/fib_trie` and `/host/proc/1/net/route`, including loopback exclusion, interface mapping, `unknown` fallback, and Tailscale selection.
- [X] T010 [US1] Implement host battery status collection in `apps/host-metrics/exporter.py` from `/host/sys/class/power_supply/*/type` and `status`, preserving the raw kernel string, exposing all batteries, and selecting the lexicographically first preferred battery.
- [X] T011 [US1] Implement the `/metrics` renderer in `apps/host-metrics/exporter.py` with the exact `host_system_temperature_celsius`, `host_metrics_temperature_available`, memory, filesystem, `host_network_ipv4_info`, `host_battery_status_info`, `host_metrics_battery_available`, and `host_metrics_info` names, labels, and units from `contracts/exporter-api.md`.
- [X] T012 [US1] Implement the `/ha` JSON renderer in `apps/host-metrics/exporter.py` with the exact flat keys from `contracts/exporter-api.md`, including `battery_status`, `battery_device`, `battery_path`, and `battery_statuses`, and null/empty semantics for absent sources.
- [X] T013 [US1] Run `python3 -m unittest discover -s apps/host-metrics -p 'test_*.py'` and fix all parser, rendering, battery-selection, and contract failures in `apps/host-metrics/exporter.py` and `apps/host-metrics/test_exporter.py`.
- [X] T014 [US1] Create `apps/host-metrics/deployment.yaml` with one replica, `nodeSelector` `kubernetes.io/hostname: dietpi`, a control-plane toleration, the digest-pinned `python:3.12-alpine@sha256:b658b05ce9c4eb97ec6fc19424818a1f31993659c2b505a532f470e83807815d` image, port `9100`, `/readyz` startup/readiness probes, `/healthz` liveness, requests `10m`/`32Mi`, limits `100m`/`96Mi`, and the read-only hostPath mounts for `/proc/meminfo`, `/proc/1/net`, `/sys`, and `/`, plus the script ConfigMap volume referencing `host-metrics-script` so Kustomize applies the generated hash suffix.
- [X] T015 [P] [US1] Create `apps/host-metrics/service.yaml` as a `ClusterIP` Service named `host-metrics` on port `9100` targeting the named `http` container port; do not add an Ingress, LoadBalancer, NodePort, hostPort, or Tailscale exposure.
- [X] T016 [US1] Harden `apps/host-metrics/deployment.yaml`: `runAsNonRoot`, UID/GID 65534, `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true`, `capabilities.drop: ["ALL"]`, `seccompProfile: RuntimeDefault`, `automountServiceAccountToken: false`, no privileged mode, no hostNetwork, no hostPID, and no writable host mounts.
- [X] T017 [US1] Run `kubectl kustomize apps` and `./scripts/validate.sh`; fix Kustomize, kubeconform, yamllint, secret-scan, or unit-test failures in `apps/host-metrics/` and `scripts/validate.sh`.
- [X] T018 [US1] Reconcile Flux and verify the workload using `specs/002-host-metrics-exporter/quickstart.md`: `flux reconcile kustomization apps --with-source`, `kubectl -n monitoring rollout status deployment/host-metrics`, and confirm the pod is Ready on `dietpi` with the generated `host-metrics-script-<hash>` ConfigMap.
- [X] T019 [US1] Verify `/metrics`, `/ha`, and `/readyz` from the `home-assistant` namespace using `specs/002-host-metrics-exporter/quickstart.md`; confirm every available metric family, the battery status keys, and `/readyz` 200. If the host has no battery, confirm `battery_status: null` and `host_metrics_battery_available 0`; if `/proc/1/net` is unreadable, apply the documented `/proc` fallback from `research.md`.
- [X] T020 [US1] Verify there is no external exposure by inspecting `apps/host-metrics/service.yaml` and `apps/host-metrics/deployment.yaml`: ClusterIP only, no Ingress, no LoadBalancer/NodePort, no hostPort, no hostNetwork, no privileged mode, and no hostPID.
- [X] T021 [US1] Run the pod replacement check in `specs/002-host-metrics-exporter/quickstart.md`: delete the exporter pod, wait for the replacement to become Ready, and confirm `/metrics` returns HTTP 200 without manual action.

**Checkpoint**: User Story 1 is independently deployable and verifiable from Git; the endpoint and
all currently supported source families are proven from the Home Assistant namespace.

---

## Phase 4: User Story 2 - Create Home Assistant sensors through the UI (Priority: P2)

**Goal**: Document the exact metric contract and manual UI steps so the operator can create
temperature, RAM, storage, battery status, Tailscale IPv4, and optional all-IPv4 sensors without
Home Assistant YAML, HACS, or repository changes.

**Independent Test**: Following only `docs/11-host-metrics.md` and
`contracts/home-assistant-ui.md`, create the sensors in the Home Assistant UI and observe values
with the expected units or states.

- [X] T022 [US2] Create `docs/11-host-metrics.md` with the endpoint URLs, exact metric names/labels/units, `/ha` key table, battery-status semantics including raw states and multiple-battery preferred selection, absent/unreadable behavior, the 10-minute Scrape cadence, security/exposure notes, and step-by-step UI instructions for temperature, RAM usage, storage usage, battery status, Tailscale IPv4, and optional all-IPv4 sensors.
- [X] T023 [P] [US2] Add document 11 to the index in `docs/README.md` with its status and scope.
- [X] T024 [P] [US2] Update `README.md` with the exporter in the status, architecture diagram, documentation table, and repository map.
- [X] T025 [P] [US2] Update `docs/09-limitations.md` with the upstream Docker Hub dependency, the UI-only 10-minute polling cadence, battery absence and unreadable-status behavior, the read-only host `/` mount, and the deliberate exclusion of NUT/UPS, battery percentage, battery health, and battery runtime.
- [X] T026 [US2] Compare every documented `/ha` key, template, unit, device class, state class, and availability template in `docs/11-host-metrics.md` and `contracts/home-assistant-ui.md` against the running exporter; correct any mismatch.
- [X] T027 [US2] Add a manual UI handoff and verification checklist to `docs/11-host-metrics.md` for the operator to record entity IDs and observed states; do not modify Home Assistant YAML, HACS, automations, or the Home Assistant configuration repository.

**Checkpoint**: The operator has a complete, verified UI-only procedure for all supported sensors,
including battery status.

---

## Phase 5: User Story 3 - Recover and troubleshoot the exporter (Priority: P3)

**Goal**: Document and exercise recovery for exporter restarts, node reboots, missing temperature,
missing battery, unreadable battery status, hostPath failures, changing IPs, exporter downtime, and
Flux drift.

**Independent Test**: Follow only `docs/11-host-metrics.md` and
`specs/002-host-metrics-exporter/quickstart.md` to reproduce each degraded state, confirm sensors
are unavailable rather than stale or fabricated, and restore normal operation.

- [X] T028 [US3] Add recovery and failure sections to `docs/11-host-metrics.md` for exporter down, pod restart, node reboot, no temperature sensor, no battery, unreadable battery status, hostPath permissions/missing paths, multiple or changing IPv4 addresses, and manual changes being reverted by Flux.
- [X] T029 [US3] Add exact diagnostic and recovery command blocks to `docs/11-host-metrics.md` for Flux status, pod placement, logs/events, `/metrics`, `/ha`, `/readyz`, Service exposure checks, and the `/proc/1/net` fallback.
- [X] T030 [US3] Run the pod restart drill from `specs/002-host-metrics-exporter/quickstart.md`; confirm the replacement pod is Ready within 2 minutes and record the observed behavior in `docs/11-host-metrics.md`.
- [X] T031 [US3] Verify the no-temperature, no-battery, and unreadable battery-status paths through `apps/host-metrics/test_exporter.py` and, when the host has a battery, the live `/ha` response; record the expected unavailable states in `docs/11-host-metrics.md`.
- [ ] T032 [US3] Run the coordinated node reboot drill from `specs/002-host-metrics-exporter/quickstart.md`; confirm the node, Flux reconciliation, pod readiness on `dietpi`, endpoint reachability, and current IPv4/battery values; record the result in `docs/11-host-metrics.md`.
- [X] T033 [US3] Verify Flux reverts a manual change (for example a temporary replica-count change) to `apps/host-metrics/deployment.yaml`; restore the desired state and record the observation in `docs/11-host-metrics.md`.
- [X] T034 [US3] Verify the hostPath failure behavior with a fixture-based local run or a controlled temporary check; confirm an unreadable memory/root source makes `/readyz` 503 while an unreadable hwmon or battery status only removes that reading; record the result in `docs/11-host-metrics.md`.

**Checkpoint**: Every documented failure mode has an observed or test-backed expected behavior and a
recovery path.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, security review, and documentation consistency across all stories.

- [X] T035 Run the full `./scripts/validate.sh` after all manifest, script, test, and documentation changes; resolve every failure in `apps/host-metrics/`, `scripts/validate.sh`, `README.md`, and `docs/`.
- [ ] T036 Run the complete P1–P3 quickstart in `specs/002-host-metrics-exporter/quickstart.md`, including the operator UI handoff; record actual results and any remaining manual steps in `docs/11-host-metrics.md`.
- [X] T037 Perform the security and boundary review across `apps/host-metrics/`, `docs/11-host-metrics.md`, `README.md`, and `docs/09-limitations.md`: zero secrets, zero real tailnet identifiers or runtime IPs, no Home Assistant repository changes, no HACS/YAML, no Prometheus/Grafana/alerting/long-term storage, no external exposure, and an immutable pinned image digest.
- [X] T038 Review the final diff for `apps/host-metrics/`, `apps/kustomization.yaml`, `scripts/validate.sh`, `docs/11-host-metrics.md`, `docs/09-limitations.md`, `docs/README.md`, and `README.md`; fix inconsistencies and do not commit unless explicitly requested.

---

## Pending / Blocked

- T032 requires a coordinated maintenance-window node reboot and post-reboot Flux verification.
- T036 is superseded by the MQTT UI in `specs/003-host-metrics-mqtt-device/`; do not create legacy Scrape sensors. Use `docs/12-host-metrics-mqtt.md` instead.

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup; blocks User Story 1 and all later stories.
- **User Story 1 (Phase 3)**: Depends on Foundational. Delivers the exporter and endpoint contract.
- **User Story 2 (Phase 4)**: Depends on User Story 1 for live contract verification; the documentation can be drafted earlier but must be verified against the running `/ha`.
- **User Story 3 (Phase 5)**: Depends on User Story 1 and the operator-facing documentation from User Story 2.
- **Polish (Phase 6)**: Depends on all desired user stories.

### User Story Dependencies

- **US1 (P1)**: No dependency on US2 or US3. This is the MVP.
- **US2 (P2)**: Depends on US1 for endpoint verification and the operator UI handoff.
- **US3 (P3)**: Depends on US1 and US2 because recovery procedures reference the documented sensors and endpoint.

### Within Each User Story

- US1: T006 tests first (expected to fail) → T007–T012 collectors/renderers → T013 unit tests →
  T014/T015 manifests → T016 hardening → T017 static validation → T018 Flux deployment → T019–T021
  endpoint, exposure, and restart verification.
- US2: T022 main operator guide → T023–T025 indexes/limitations in parallel → T026 contract check →
  T027 manual UI handoff checklist.
- US3: T028/T029 recovery documentation → T030–T034 drills and recorded observations.
- Polish: T035 validation → T036 end-to-end quickstart → T037 security review → T038 final diff.

### Parallel Opportunities

- T004 and T005 can run alongside T003.
- T014 and T015 can run in parallel because they create different manifest files.
- T023, T024, and T025 can run in parallel because they update different documentation files.
- No other task should be parallelized when it edits the same file (`apps/host-metrics/exporter.py`,
  `apps/host-metrics/test_exporter.py`, or `docs/11-host-metrics.md`).

---

## Parallel Example: User Story 1 manifests

```bash
Task: "Create apps/host-metrics/deployment.yaml with probes, resources, security context, and hostPath mounts"
Task: "Create apps/host-metrics/service.yaml as a ClusterIP Service on port 9100"
```

## Parallel Example: User Story 2 documentation

```bash
Task: "Add document 11 to docs/README.md"
Task: "Update README.md status, architecture, and documentation table"
Task: "Update docs/09-limitations.md with Docker Hub, 10-minute polling, and battery limitations"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational.
3. Complete Phase 3: User Story 1.
4. **STOP and VALIDATE**: Reconcile from Git, confirm the pod is Ready on `dietpi`, read the endpoint
   from `home-assistant`, verify battery/temperature availability, and confirm no external exposure.
5. Deploy/demo the endpoint.

### Incremental Delivery

1. Setup + Foundational → exporter skeleton and validation wiring.
2. US1 → working exporter and ClusterIP Service; verify the endpoint and restart behavior.
3. US2 → documented Home Assistant UI flow; the operator creates and verifies sensors.
4. US3 → recovery and failure documentation; exercise pod restart, no-battery/no-temperature,
   hostPath failure, Flux drift, and node reboot.
5. Polish → full validation, security review, and documentation consistency.

### Notes

- The battery status feature is optional hardware-wise. If `dietpi` exposes no
  `/sys/class/power_supply` battery, the exporter must still pass US1 with
  `battery_status: null` and `host_metrics_battery_available 0`; the battery sensor is unavailable by
  design.
- Do not add Home Assistant YAML, HACS, automations, a NUT/UPS service, USB/device access,
  Prometheus, Grafana, or any external exposure path.
- Do not commit runtime IPv4 addresses, tailnet identifiers, secrets, or state bundles.
- Commit only when the user explicitly requests it; this task list ends with review, not commit.