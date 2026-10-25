# Implementation Plan: MQTT Device Grouping for Host Metrics

**Branch**: `main` | **Date**: 2026-10-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-host-metrics-mqtt-device/spec.md`

## Summary

Add a cluster-internal Mosquitto broker in `monitoring` and extend the host-metrics exporter with
MQTT discovery, state, and availability publishing. Home Assistant adds the MQTT integration through
the UI and receives one device, `home-sweet-lab-server`, containing CPU temperature, RAM usage,
storage usage, battery status, Tailscale IPv4, and all IPv4 addresses. The HTTP exporter remains for
debugging; the legacy Scrape integration is removed after MQTT is verified.

## Technical Context

**Language/Version**: Python 3.12 for the exporter; YAML/Kustomize; GitHub Actions; Home Assistant
2026.10.4 MQTT integration.

**Primary Dependencies**: `eclipse-mosquitto:2` pinned digest, `paho-mqtt==2.1.0`, GHCR, Flux
image automation, Home Assistant MQTT integration. No HACS, Home Assistant YAML, or Prometheus.

**Storage**: Broker is ephemeral (`persistence false`, emptyDir data/log). No PVC. Retained
discovery/state is republished by the exporter after broker restarts.

**Testing**: Unit tests for discovery/state/availability; local MQTT integration test with a test
broker; `scripts/validate.sh`; cluster ACL/topic verification; HA device verification; restart and
node-reboot drills.

**Target Platform**: Single amd64 `dietpi` k3s node; `home-sweet-lab-server` is the HA device
name only.

**Project Type**: GitOps-managed Kubernetes workload plus a custom exporter image and operator
documentation.

**Performance Goals**: State publish every 30 seconds; broker and exporter under 64 MiB; MQTT
message volume tiny.

**Constraints**: ClusterIP only; no external MQTT, ingress, hostNetwork, hostPID, hostPort, or
privileged mode; non-root; read-only root filesystems; no secrets in Git; no node rename; no HA
YAML/HACS.

**Scale/Scope**: One broker, one exporter, two MQTT users, one HA device, six entities, one node.

## Constitution Check

| Principle | Result | Evidence |
| --------- | ------ | -------- |
| I. GitOps as source of truth | PASS | Broker and exporter manifests are in `apps/host-metrics`; Flux reconciles them. Only the MQTT Secret is manual, per the constitution. |
| II. Reproducible host bootstrap | PASS | Docs cover Secret creation, broker, exporter, HA UI, ACLs, and recovery. |
| III. Public repositories, private state | PASS | MQTT credentials are a manual Secret and HA `.storage`; never committed. |
| IV. Local-first, documented cloud dependencies | PASS | Broker and exporter run locally. GHCR and Docker Hub are documented image dependencies. |
| V. Recoverability before optimization | PASS | Ephemeral broker state is republished; restart and reboot procedures are documented. |
| VI. Small, reviewable, validated changes | PASS | Two workloads, one custom image, focused tests, and docs. Images are pinned/digested. |
| VII. Clear repository boundaries | PASS | Home Assistant configuration remains untouched; only the MQTT UI integration is documented. |
| Technology standards | PASS | Exporter image is published to GHCR with immutable tags; the broker is an upstream digest-pinned image. |

## Project Structure

```text
apps/host-metrics/
├── Dockerfile
├── requirements.txt
├── exporter.py
├── mqtt_discovery.py
├── mqtt_publisher.py
├── test_exporter.py
├── test_mqtt_publisher.py
├── deployment.yaml
├── service.yaml
├── namespace.yaml
├── image-automation.yaml
├── kustomization.yaml
└── mqtt/
    ├── configmap.yaml
    ├── deployment.yaml
    ├── service.yaml
    └── kustomization.yaml

.github/workflows/publish-host-metrics.yml

docs/
├── 12-host-metrics-mqtt.md
├── 11-host-metrics.md          # mark Scrape as legacy
├── README.md
└── 09-limitations.md

README.md
specs/003-host-metrics-mqtt-device/
```

**Structure Decision**: Keep the broker and exporter in the existing `monitoring` namespace and
`apps/host-metrics` app so they share the manual Secret and one Flux reconciliation path. The
custom exporter image moves the script out of the ConfigMap and adds `paho-mqtt`. The HTTP Service
and endpoints remain unchanged.

## Design Decisions

### Broker

- Mosquitto `Deployment` with `eclipse-mosquitto:2@sha256:860aeb...`
- ClusterIP Service `mosquitto` on 1883
- ConfigMap: `mosquitto.conf` and ACL file
- Manual Secret `mosquitto-auth`: `passwd`, exporter/HA usernames and passwords
- Non-root UID/GID 1883, read-only root, all capabilities dropped, emptyDir data/log
- TCP probes; no PVC; no external exposure

### MQTT authentication and ACLs

Two users:

- `exporter`: write discovery, state, availability; read `homeassistant/status`
- `homeassistant`: read discovery/state/availability/status; write `homeassistant/status`

The exact ACL is in `contracts/mqtt-discovery.md`.

### Exporter image and MQTT publisher

- Custom image publishes to GHCR with immutable tags
- Flux `ImageRepository`, `ImagePolicy`, and `ImageUpdateAutomation` update the deployment
- `mqtt_discovery.py` builds the one-device discovery payloads
- `mqtt_publisher.py` handles connection, LWT, retained discovery/state/availability, reconnect,
  HA birth, and 30-second state publishing
- `exporter.py` starts MQTT when `MQTT_HOST` is set; HTTP endpoints remain
- Launcher script/config removed; script is in the image

### Home Assistant device and entities

- Device identifier/name: `home-sweet-lab-server`
- Entity IDs: `sensor.home_sweet_lab_server_*`
- State topic: `home-sweet-lab-server/state`
- Discovery prefix: `homeassistant`
- Per-source availability for temperature, battery, and IPv4
- No Scrape integration; remove it after MQTT verification

## Security Trade-offs

| Trade-off | Reason | Mitigation |
| --------- | ------ | ---------- |
| Plain MQTT inside the cluster, no TLS | Avoid certificate management for a cluster-internal broker in v1. | Auth + ACLs; ClusterIP only; no external exposure; TLS is a future feature. |
| Ephemeral broker | Avoid another PVC and backup path. | Exporter republishes retained discovery/state on reconnect and HA birth. |
| Manual MQTT Secret | The repository is public; secrets are never committed. | Document creation, rotation, and deletion; least-privilege users/ACLs. |
| Custom GHCR image | `paho-mqtt` is a new dependency. | Pin paho and the base image; CI tests; immutable tags; public package. |
| Broker reachable by any pod | NetworkPolicy is unreliable on this k3s node. | MQTT auth and ACLs are the boundary; no external exposure. |

## Complexity Tracking

| Change | Why Needed | Simpler Alternative Rejected Because |
| ------ | ---------- | ------------------------------------ |
| Custom exporter image + GHCR workflow | MQTT requires `paho-mqtt`, which the stock Python image cannot provide without runtime pip. | Runtime pip install needs network/writable storage and adds supply-chain risk; a first-party image is reproducible. |
| Mosquitto workload | HA MQTT discovery needs a broker. | No existing broker exists in the cluster; an external broker is not documented and adds a cloud/LAN dependency. |
| Per-source availability topics | Preserve unavailable behavior for missing temperature/battery/IP. | A single availability topic would show `unknown` for absent optional sources. |

## Verification Plan

1. Unit tests for discovery payloads, device grouping, entity IDs, state rendering, availability,
   and absent-source behavior.
2. Local MQTT integration test with a test broker and `paho-mqtt`.
3. `scripts/validate.sh` for Kustomize, kubeconform, yamllint, gitleaks, and unit tests.
4. Cluster: broker/exporter Ready; ACL checks with `mosquitto_sub`/`mosquitto_pub`; retained
   discovery and state present.
5. HA UI: add MQTT integration; verify one device and six entities; values update within 60 seconds.
6. Recovery: exporter down/restart, broker restart, HA restart, node reboot, Secret failure.
7. Migration: remove Scrape and orphaned entities; verify no duplicates.
8. Security: no external MQTT, no plaintext credentials in Git, no HA repository changes.
