# Feature Specification: MQTT Device Grouping for Host Metrics

**Feature Branch**: `main`

**Created**: 2026-10-25

**Status**: Draft

**Input**: Add a cluster-internal MQTT broker and MQTT discovery to the existing host-metrics
exporter so Home Assistant presents CPU temperature, RAM usage, storage usage, battery status,
Tailscale IPv4, and all IPv4 addresses as entities of one device named `home-sweet-lab-server`.
The HTTP endpoints remain for debugging. Home Assistant is configured through the UI; the Home
Assistant configuration repository is not changed.

## Clarifications

### Session 2026-10-25

- Q: How far should the `home-sweet-lab-server` rename go? → A: Device name, entity IDs, and MQTT topics.
- Q: Which MQTT authentication model? → A: Two users (`exporter`, `homeassistant`) with ACLs.

## User Scenarios & Testing

### User Story 1 - Deploy the broker and MQTT exporter (Priority: P1)

The household operator reconciles a Mosquitto broker and an MQTT-enabled host-metrics exporter
through Flux. The exporter publishes retained discovery, state, and availability messages to the
broker. The HTTP endpoint remains reachable at `host-metrics.monitoring.svc.cluster.local:9100`.

**Independent Test**: Reconcile from Git, confirm the broker and exporter are Ready, and inspect the
retained MQTT topics with an authorized client. No Home Assistant UI work is required.

**Acceptance Scenarios**:

1. **Given** the broker Secret exists, **When** Flux reconciles, **Then** `mosquitto` and
   `host-metrics` are Ready in `monitoring`, and the broker is a ClusterIP Service on 1883.
2. **Given** the exporter is connected, **When** discovery is inspected, **Then** six retained discovery messages under `homeassistant/sensor/` share the device identifier
   `home-sweet-lab-server`.
3. **Given** the exporter is connected, **When** state is inspected, **Then**
   `home-sweet-lab-server/state` is retained and contains the documented JSON keys.
4. **Given** the exporter is connected, **When** availability is inspected, **Then** the main and
   per-source topics are `online`, and the broker is the only MQTT endpoint.
5. **Given** the exporter pod is deleted, **When** the broker publishes its Last Will, **Then**
   availability becomes `offline`; after replacement, it returns to `online`.

### User Story 2 - Add the Home Assistant MQTT device (Priority: P2)

The household operator adds the MQTT integration in the Home Assistant UI and receives one device
named `home-sweet-lab-server` with the six host-metric entities. The sensors update automatically
without a Scrape integration.

**Independent Test**: Add the MQTT integration with the broker, verify one device and six entities,
and observe values update within 60 seconds.

**Acceptance Scenarios**:

1. **Given** the broker and exporter are Ready, **When** the operator enters the broker URL and
   the `homeassistant` credentials, **Then** the MQTT integration connects.
2. **Given** discovery messages are retained, **When** the integration connects, **Then** one
   device `home-sweet-lab-server` contains the six expected entities.
3. **Given** the entities exist, **When** 60 seconds elapse, **Then** values for temperature, RAM,
   storage, battery, and IPv4 have been published and displayed.
4. **Given** the MQTT entities are verified, **When** Scrape was previously used, **Then** the
   Scrape integration and its sensors are removed without losing the MQTT entities.
5. **Given** the exporter is stopped, **When** the Last Will is processed, **Then** all entities
   become unavailable and recover after restart.

### User Story 3 - Recover and migrate (Priority: P3)

The operator can recover from exporter, broker, Home Assistant, and node restarts, and can migrate
from the legacy Scrape integration.

**Independent Test**: Restart each component, observe availability and discovery republish, and
confirm no duplicate or stale entities.

**Acceptance Scenarios**:

1. **Given** the broker restarts, **When** it returns, **Then** the exporter reconnects and
   republishes discovery, state, and availability.
2. **Given** Home Assistant restarts, **When** it publishes `homeassistant/status=online`, **Then**
   the exporter republishes discovery, state, and availability.
3. **Given** temperature or battery is unavailable, **When** state is published, **Then** only the
   affected entity becomes unavailable.
4. **Given** the node reboots, **When** k3s and Flux return, **Then** the broker and exporter
   recover and the device returns without manual reconfiguration.
5. **Given** the broker Secret is missing or wrong, **When** the pods start, **Then** the failure
   is visible and documented without exposing credentials.

## Edge Cases

- The broker is down; the exporter retries and the HA entities are unavailable.
- The MQTT Secret is missing, has the wrong password, or is rotated; pods fail visibly or the
  exporter logs authentication failure.
- ACLs deny a topic; the exporter or HA logs a failure, and the operator verifies the ACL file.
- The broker restarts and loses retained messages; the exporter republishes on reconnect.
- Home Assistant restarts; the birth message triggers discovery republish.
- The exporter restarts; LWT marks entities unavailable, then discovery/state return.
- The host has no battery or temperature sensor; only the affected per-source availability topic
  goes offline.
- Multiple batteries or changing IPv4 addresses; the preferred battery and current addresses are
  republished.
- Scrape sensors already exist; entity IDs collide or are duplicated. Migrate by verifying MQTT,
  removing Scrape, and deleting orphaned entities.
- The custom exporter image is unavailable; the deployment stays in image pull failure until the
  GHCR package is public/pullable.
- The node is renamed; out of scope. The Kubernetes node, hostname, and Linux user remain `dietpi`.
- The MQTT broker is cluster-internal; no external client can connect.

## Requirements

### Functional Requirements

- **FR-001**: The broker MUST be a Flux-managed workload in `monitoring`, exposed only through a
  ClusterIP Service on port 1883.
- **FR-002**: The broker MUST use the pinned `eclipse-mosquitto:2` image and run without privileged
  mode, host networking, host ports, or a writable root filesystem.
- **FR-003**: MQTT authentication MUST use separate `exporter` and `homeassistant` users with ACLs;
  credentials MUST be supplied by a manually created Secret and never committed.
- **FR-004**: The exporter MUST publish retained discovery for exactly one device with identifier
  `home-sweet-lab-server`.
- **FR-005**: The device MUST contain CPU temperature, RAM usage, storage usage, battery status,
  Tailscale IPv4, and optional all-IPv4 entities with the exact IDs in
  `contracts/mqtt-discovery.md`.
- **FR-006**: The exporter MUST publish retained state to `home-sweet-lab-server/state` every 30
  seconds by default.
- **FR-007**: The exporter MUST publish retained availability to
  `home-sweet-lab-server/availability` and per-source topics, with Last Will `offline`.
- **FR-008**: The exporter MUST subscribe to `homeassistant/status` and republish discovery/state
  when Home Assistant comes online.
- **FR-009**: The exporter MUST keep `/metrics`, `/ha`, `/healthz`, and `/readyz` available.
- **FR-010**: The exporter MUST be built as a custom image with `paho-mqtt`, published to GHCR, and
  updated by Flux image automation.
- **FR-011**: The repository MUST document the broker, manual Secret creation/rotation, ACLs,
  discovery topics, HA MQTT UI steps, migration, and recovery.
- **FR-012**: The Home Assistant integration MUST be configured in the UI; no Home Assistant YAML,
  HACS, automations, or configuration-repository changes are introduced.
- **FR-013**: The legacy Scrape integration MUST be documented as legacy and removed after the
  MQTT device is verified.
- **FR-014**: The feature MUST NOT add Prometheus, Grafana, alerting, external MQTT access, TLS, or
  battery percentage/health/runtime.
- **FR-015**: Validation MUST include unit tests for discovery/state/availability, YAML/Kustomize
  validation, broker ACL checks, and cluster recovery drills.

### Key Entities

- **Mosquitto broker**: ClusterIP MQTT service with two users and ACLs.
- **MQTT Secret**: Manual credentials and password file; never committed.
- **MQTT discovery message**: Retained HA discovery config for one entity.
- **MQTT state message**: Retained JSON snapshot on `home-sweet-lab-server/state`.
- **Availability topics**: Main and per-source online/offline topics.
- **Home Assistant device**: `home-sweet-lab-server`, containing six entities.
- **Legacy Scrape integration**: The previous one-device-per-sensor path, to be removed after MQTT.

## Success Criteria

- **SC-001**: Flux reconciles the broker and exporter within 10 minutes; both are Ready on `dietpi`.
- **SC-002**: Six retained discovery messages share the `home-sweet-lab-server` device identifier.
- **SC-003**: Home Assistant shows exactly one `home-sweet-lab-server` device with six entities.
- **SC-004**: Values update within 60 seconds without a Scrape integration.
- **SC-005**: Exporter deletion makes all entities unavailable via LWT; restart restores them.
- **SC-006**: Broker restart and Home Assistant restart cause automatic republish without manual
  sensor recreation.
- **SC-007**: The node reboot drill restores the broker, exporter, and HA device.
- **SC-008**: No external MQTT exposure, no plaintext credentials in Git, and no Home Assistant
  repository changes.
- **SC-009**: The migration removes Scrape sensors and leaves no duplicate or stale entities.

## Out of Scope

- Renaming the Kubernetes node, hostname, OS, or Linux user from `dietpi`.
- Home Assistant YAML, HACS, automations, scenes, or dashboards.
- MQTT TLS, external MQTT access, or a public broker.
- Prometheus, Grafana, alerting, long-term storage, per-container metrics.
- Battery percentage, health, runtime, or NUT/UPS integration.
- Broker persistence/PVC; retained messages are ephemeral and republished by the exporter.

## Dependencies

- Health of the existing `host-metrics` exporter and `monitoring` namespace.
- `eclipse-mosquitto:2` pinned image and `paho-mqtt==2.1.0`.
- GHCR package publishing and Flux image automation.
- Manual `mosquitto-auth` Secret creation and rotation.
- Home Assistant MQTT integration, configured via the UI.
- Cluster-internal DNS from Home Assistant to `mosquitto.monitoring.svc.cluster.local`.

## Assumptions

- The broker runs in `monitoring` to share the Secret and namespace with the exporter.
- The broker is ephemeral; the exporter republishes retained messages after a restart.
- MQTT is plain TCP inside the cluster; auth and ACLs are the control boundary.
- The custom exporter image is public in GHCR; if private, an image pull Secret is required.
- The Kubernetes node remains `dietpi`; `home-sweet-lab-server` is the HA device identity.
- The user performs the Home Assistant MQTT UI steps and removes Scrape after verification.
