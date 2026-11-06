# Implementation Plan: Battery Level Percentage

**Branch**: `005-battery-level` | **Date**: 2026-11-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-battery-level/spec.md`

## Summary

Add host battery level as a percentage alongside the existing battery status. The exporter reads
the level from the already-mounted read-only host `power_supply` interface, exposes a new metric,
adds flat JSON keys, publishes a seventh MQTT discovery entity, and keeps status behavior unchanged.
Missing or unreadable levels are represented as absent, never as zero, and do not affect readiness.

## Technical Context

**Language/Version**: Python 3.12 (existing `host-metrics` exporter)

**Primary Dependencies**: Python standard library; `paho-mqtt==2.1.0` for MQTT publishing

**Storage**: None; stateless in-memory collection per scrape/publish cycle

**Testing**: `python -m unittest discover -s apps/host-metrics -p 'test_*.py'`; Kustomize and
kubeconform validation per repository guidance

**Target Platform**: Linux host `dietpi`, k3s single node, container image
`python:3.12-alpine` pinned by digest

**Project Type**: Single service (host metrics exporter) with GitOps manifests and documentation

**Performance Goals**: Existing 30-second publish cycle; one additional small file read per battery
per collection; no measurable change to scrape latency

**Constraints**: No privileged mode, host networking, host ports, host PID, writable host mounts,
or host command execution; read-only `/host/sys` only; non-root UID/GID 65534; no secrets

**Scale/Scope**: One node, one exporter replica, zero or more batteries; typical host has one
battery (`BAT0`)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment | Result |
| --------- | ---------- | ------ |
| I. GitOps as source of truth | All code, manifests, ACLs, and docs are committed; Flux reconciles the exporter. No manual resource apply is required. | PASS |
| II. Reproducible host bootstrap | No host install, package, or manual bootstrap change; the existing `/host/sys` mount is reused. | PASS |
| III. Public repositories, private state | No secrets or household data added. The battery percentage is host telemetry already adjacent to battery status and contains no credentials. | PASS |
| IV. Local-first, documented cloud dependencies | No new cloud or external dependency; battery data stays on the household host and cluster-internal MQTT. | PASS |
| V. Recoverability before optimization | The exporter remains stateless; no data migration, PVC, or backup change. Restart republishes discovery and state. | PASS |
| VI. Small, reviewable, validated changes | Additive field, metric, JSON key, entity, contract, docs, and unit tests; no image or dependency change. | PASS |
| VII. Clear repository boundaries | Changes stay in this repository's exporter, docs, and specs; Home Assistant configuration is untouched. | PASS |
| Technology standards | No new images, Helm charts, or secrets; existing Python image and Mosquitto remain pinned. | PASS |

No violations; Complexity Tracking is not required.

## Project Structure

### Documentation (this feature)

```text
specs/005-battery-level/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── battery-level-additions.md
└── tasks.md             # Phase 2 output (/speckit.tasks; not created here)
```

### Source Code (repository root)

```text
apps/host-metrics/
├── exporter.py             # BatteryReading, collection, metrics, /ha JSON
├── mqtt_discovery.py       # Seventh sensor and discovery payload
├── mqtt_publisher.py       # No logic change expected; uses discovery/state output
├── mqtt/configmap.yaml     # Broker ACL entries for the new discovery topic
├── test_exporter.py        # Collection and render tests
├── test_mqtt_publisher.py  # Discovery count and payload tests
├── deployment.yaml         # No change expected (existing /host/sys mount)
└── requirements.txt        # No change expected

docs/
├── 11-host-metrics.md      # HTTP/metric contract and legacy Scrape table
├── 12-host-metrics-mqtt.md # Device entity table, verification, limitations
└── 09-limitations.md       # Remove battery-percentage limitation
```

**Structure Decision**: Extend the existing single-service exporter in `apps/host-metrics`. No new
module, service, manifest, or package is introduced.

## Implementation Approach

1. Extend `BatteryReading` with an optional integer `level_percent` while keeping `status` required.
2. Read `capacity` from each battery directory under `/host/sys/class/power_supply/`, parse it as an
   integer, constrain values to `0..100`, and leave the level `None` when the file is missing,
   unreadable, or non-numeric.
3. Add `host_battery_level_percent{device,path}` as a gauge family for readings that have a level.
4. Add `battery_level_percent` (preferred) and `level_percent` per battery to the flat JSON used by
   `/ha` and the MQTT state topic.
5. Add a `battery_level` MQTT discovery sensor with `%` unit, `battery` device class, `measurement`
   state class, `mdi:battery` icon, and battery-source availability.
6. Update the Mosquitto ACL for exporter write and Home Assistant read of the new discovery topic.
7. Update the HTTP, MQTT, and limitations documentation and the feature contract.
8. Extend unit tests for collection, metrics, JSON, discovery, and state; validate Kustomize and
   Kubernetes schemas.

## Phase 0: Research

See [research.md](./research.md). All technical unknowns are resolved; no `NEEDS CLARIFICATION`
remains.

## Phase 1: Design & Contracts

See [data-model.md](./data-model.md), [contracts/battery-level-additions.md](./contracts/battery-level-additions.md),
and [quickstart.md](./quickstart.md).

## Post-Design Constitution Check

The design stays additive and read-only. The only rendered manifest change is the Mosquitto ACL
ConfigMap; the exporter Deployment, mounts, probes, resources, image, and secrets are unchanged.
All principles continue to pass.

## Complexity Tracking

No constitution violations. Not applicable.
