# Feature Specification: Host Metrics Exporter and Home Assistant Integration

**Feature Branch**: `main`

**Created**: 2026-10-25

**Status**: Draft

**Input**: Deploy a Flux-managed host-metrics exporter for the single DietPi node, expose it only
inside the cluster, and document the exact metric contract and Home Assistant UI steps needed to
show CPU temperature, RAM usage, storage usage, IP address(es), and host battery charging status.
The Home Assistant integration is performed manually by the household operator through the UI; the
Home Assistant configuration repository and its YAML are not changed.

## Clarifications

### Session 2026-10-25

- Q: What is the source of the charging/discharging status you want Home Assistant to show? → A: Host battery via Linux `power_supply`.

## User Scenarios & Testing _(mandatory)_

### User Story 1 - Deploy and verify the exporter (Priority: P1)

The household operator merges a change to this repository. Flux reconciles a host-metrics exporter
and an internal Service into the `monitoring` namespace, schedules the exporter on `dietpi`, and
the operator confirms the metrics endpoint is reachable from the `home-assistant` namespace.

**Why this priority**: Nothing else in this feature works until the exporter is running and its
endpoint is reachable from the workload that will consume it. This story is the minimum viable
delivery and proves the security boundary at the same time.

**Independent Test**: Reconcile the exporter from Git, confirm the pod is Ready on `dietpi`, and
retrieve the documented metrics endpoint from a pod or debug session in the `home-assistant`
namespace. No Home Assistant UI work is required.

**Acceptance Scenarios**:

1. **Given** the exporter manifests are merged to the tracked branch, **When** Flux reconciles, **Then** the `monitoring` namespace contains the exporter workload and its Service, and the exporter pod is Ready on `dietpi`.
2. **Given** the exporter is Ready, **When** the documented endpoint is requested from the `home-assistant` namespace, **Then** the response is HTTP 200 and contains temperature, memory, root filesystem, IPv4, and battery-status metric families when those sources are present.
3. **Given** the exporter is running, **When** cluster exposure is inspected, **Then** the Service is internal-only and there is no external ingress, load balancer, node port, host port, or host networking.
4. **Given** the exporter reports values, **When** they are compared with the host's own readings, **Then** temperature is in degrees Celsius, memory and filesystem values are in bytes, the reported IPv4 addresses match the host's active interfaces, and the battery status matches the host's `power_supply` status.
5. **Given** the exporter pod is deleted, **When** Kubernetes replaces it, **Then** the endpoint returns to HTTP 200 without manual intervention.

---

### User Story 2 - Create Home Assistant sensors through the UI (Priority: P2)

The household operator follows the repository documentation to create Home Assistant sensors for
CPU/system temperature, RAM usage, storage usage, IP address(es), and host battery charging status
using only the Home Assistant UI. The sensors show current values and update over time.

**Why this priority**: This delivers the visible household value. It depends on P1 but is otherwise
independent: the exporter can be verified before any sensor exists.

**Independent Test**: Following only the documented UI steps on a running Home Assistant instance,
create the five sensor groups and observe values change after a host load, a battery state change,
or an exporter restart.

**Acceptance Scenarios**:

1. **Given** the exporter endpoint is reachable from Home Assistant, **When** the operator follows the documented UI steps, **Then** a temperature sensor, a memory usage sensor, a storage usage sensor, at least one IP address sensor, and a battery status sensor exist.
2. **Given** the sensors exist, **When** the exporter is queried at its documented scan interval, **Then** each sensor shows a value with the documented unit or state rather than remaining unknown or unavailable.
3. **Given** memory or filesystem usage changes on the host, **When** the next scan interval elapses, **Then** the corresponding Home Assistant sensor reflects the change.
4. **Given** the host battery changes between charging and discharging, **When** the next scan interval elapses, **Then** the battery status sensor reflects the new state.
5. **Given** the exporter is restarted, **When** the next scan interval elapses, **Then** the sensors recover and resume updating without reconfiguration.
6. **Given** the host has more than one active IPv4 address, **When** the operator follows the documentation, **Then** the operator can display the Tailscale address specifically and can optionally display the other interface addresses without ambiguity.
7. **Given** the host has more than one battery, **When** the operator follows the documentation, **Then** the preferred battery status is shown without ambiguity and the other battery statuses remain available in the machine-readable endpoint.

---

### User Story 3 - Recover and troubleshoot the exporter (Priority: P3)

The household operator can determine why a metric or sensor is missing and can restore normal
operation after an exporter restart, a node reboot, or a host without a usable temperature sensor or
battery.

**Why this priority**: A single-node household service must be diagnosable without a monitoring
stack. This story protects the P1 and P2 value after the first failure.

**Independent Test**: Simulate an exporter restart, a missing temperature or battery source, and a
node reboot; follow the documentation to confirm the expected degraded state, recovery behavior, and
verification commands.

**Acceptance Scenarios**:

1. **Given** the exporter is stopped or crash-looping, **When** the operator checks the documented status and log commands, **Then** the failure is visible and the Home Assistant sensors report unavailable rather than a stale or fabricated value.
2. **Given** the exporter restarts, **When** it becomes Ready, **Then** the metrics endpoint and the previously configured Home Assistant sensors recover automatically.
3. **Given** the node reboots, **When** k3s and Flux return, **Then** the exporter is reconciled, becomes Ready on `dietpi`, and reports current IP addresses.
4. **Given** the host exposes no usable temperature sensor, **When** the exporter runs, **Then** temperature metrics are absent or explicitly marked unavailable while memory, storage, IP, and battery metrics continue to be exposed, and the documentation explains the limitation.
5. **Given** the host exposes no battery, **When** the exporter runs, **Then** battery status is absent or explicitly marked unavailable while the other metrics continue to be exposed, and the documentation explains the limitation.
6. **Given** a host path is missing or unreadable, **When** the exporter starts, **Then** the failure is logged and the remaining metrics are still served, or the exporter fails visibly if it cannot start at all.

---

### Edge Cases

- The host has no hwmon device and no thermal zone, or the only sensor reports an implausible value; temperature must not be fabricated and the other metrics must remain available.
- A temperature source exists at first boot but disappears later; the exporter must not crash and Home Assistant must surface the missing series as unavailable or stale rather than zero.
- The host has no battery, or `/sys/class/power_supply` has no device whose `type` is `Battery`; battery status must not be fabricated, the other metrics must remain available, and the Home Assistant battery sensor must be unavailable.
- The host has more than one battery; all statuses must be exposed with device labels, and the preferred battery for the Home Assistant sensor must be chosen deterministically and documented.
- A battery reports `Full`, `Not charging`, or `Unknown` instead of `Charging` or `Discharging`; the raw kernel status must be exposed and the Home Assistant sensor must show that status rather than inventing a charging/discharging value.
- A battery is removed or its status file becomes unreadable; the status series must disappear or become unavailable, not retain a stale value.
- The host is on AC power with a full battery; `Full` is a valid status distinct from `Charging` and `Discharging`, and the documentation must explain the difference.
- The host has multiple active IPv4 addresses (Tailscale, LAN, bridge, virtual interface); each series must be distinguishable by interface, and the documentation must identify the Tailscale address as the stable one.
- A LAN or DHCP address changes or a virtual interface disappears; old address series must not persist indefinitely and the Tailscale sensor must remain stable.
- The Tailscale interface is down during boot; IP metrics may be incomplete until it returns, and Home Assistant sensors must recover without reconfiguration.
- The exporter pod is evicted, deleted, restarts, or is rescheduled; the Service must route to the replacement and the endpoint must recover automatically.
- The exporter is down for longer than the Home Assistant scan interval; sensors must become unavailable or clearly stale, not retain a plausible but wrong value.
- The Home Assistant UI-only integration polls every 10 minutes and offers no scan-interval field; the documentation must set that expectation, and a faster cadence is a non-goal rather than a defect.
- The node reboots and k3s, Flux, the container runtime, or the network comes back in a different order; the exporter must converge without manual commands.
- A required host path is absent, renamed by a host upgrade, or unreadable due to permissions; failures must be visible in logs and documented with verification steps.
- The exporter cannot be scheduled because the node label or hostname is wrong or the node is cordoned; the pod must remain pending and the condition must be documented.
- The internal Service name, port, or namespace is changed; every documented Home Assistant resource URL and the metric contract must be updated in the same change.
- Home Assistant restarts, its configuration is restored from a backup, or its network namespace changes; its sensors must reconnect using the documented internal URL without edits in the Home Assistant repository.
- A manual change is made to the exporter with `kubectl`; Flux must revert it at the next reconciliation, and the documentation must say so.
- The single node is offline; no metrics are available, and recovery is covered by the existing node-rebuild and reboot procedures.

## Requirements _(mandatory)_

### Functional Requirements

- **FR-001**: The exporter workload, its namespace, its Service, and its Flux reconciliation entry MUST live in this repository and be applied only through the cluster's GitOps reconciliation.
- **FR-002**: The exporter pod MUST be scheduled on the `dietpi` node and MUST not be intentionally scheduled to any other node.
- **FR-003**: The exporter MUST be exposed only through a cluster-internal (ClusterIP) Service. It MUST NOT use an Ingress, a Tailscale ingress or host, a load balancer, a node port, a host port, or host networking.
- **FR-004**: The Service MUST have a stable DNS name, namespace, and port, and the repository MUST document the exact reachable endpoint from the `home-assistant` namespace.
- **FR-005**: The exporter MUST serve an HTTP metrics endpoint that returns HTTP 200 when the exporter is healthy, with a content type suitable for line-oriented metric scraping.
- **FR-006**: The exporter MUST expose at least one CPU or system temperature metric when a hwmon device or thermal zone is available, in degrees Celsius, with labels that identify the source device, chip, or sensor.
- **FR-007**: The exporter MUST expose memory total and memory available in bytes, and the repository MUST document how memory usage and usage percentage are derived for Home Assistant.
- **FR-008**: The exporter MUST expose root filesystem size and available space in bytes for the series whose mount point is `/`, with a label that identifies the mount point.
- **FR-009**: The exporter MUST expose every active non-loopback IPv4 address, or at minimum the Tailscale IPv4 address, as a metric whose labels identify the network interface.
- **FR-010**: The metrics contract documentation MUST list the exact emitted metric names, units, labels, one example value per metric family, and the meaning of an absent or unavailable series, including battery status.
- **FR-011**: The exporter MUST provide a stable machine-readable representation of the same host values that can be consumed by a Home Assistant integration configured entirely through the UI, without HACS and without editing Home Assistant YAML.
- **FR-012**: The repository MUST document step-by-step Home Assistant UI instructions for creating temperature, memory usage, storage usage, IP address, and battery status sensors, including the integration to add, the resource URL, the value extraction for each sensor, units, device class or state class where applicable, and the scan interval.
- **FR-013**: The documentation MUST state that the Home Assistant UI work is performed manually by the household operator and MUST NOT modify the Home Assistant configuration repository, add Home Assistant YAML, or add Home Assistant automations.
- **FR-014**: The documentation MUST explain how to derive a percentage or used-bytes value for memory and storage from the exported metrics, including which values are numerator and denominator.
- **FR-015**: The exporter MUST run without privileged mode, MUST use the least privilege needed to read host values, MUST use read-only host mounts where host files are mounted, and MUST NOT require a secret.
- **FR-016**: The exporter container image MUST be publicly pullable and referenced by an immutable tag or digest, consistent with the repository image policy.
- **FR-017**: The exporter MUST define modest CPU and memory requests and limits so that a failure cannot starve the single node or Home Assistant.
- **FR-018**: The exporter MUST recover automatically after a pod restart, eviction, or rescheduling, and its Service endpoint MUST return to HTTP 200 without manual intervention.
- **FR-019**: After a node reboot, the exporter MUST be recreated and become Ready through normal GitOps reconciliation, and it MUST report the host's current IP addresses.
- **FR-020**: When a metric source is unavailable, the exporter MUST continue serving the metrics it can collect and MUST log the condition; if it cannot start, the failure MUST be visible in pod status and logs.
- **FR-021**: The documentation MUST describe the behavior of Home Assistant sensors when the exporter is down, when a metric is missing, and when the host has no temperature sensor or no battery, including how to make the affected entity visibly unavailable rather than misleading.
- **FR-022**: The documentation MUST include verification commands for: Flux reconciliation, pod readiness and node placement, Service type and absence of external exposure, endpoint reachability from the `home-assistant` namespace, presence of each required metric family, and recovery after a pod restart.
- **FR-023**: The documentation MUST include operational recovery procedures for an exporter crash, a pod restart, a node reboot, a missing or unreadable host path, a missing temperature source, and a missing or unreadable battery status source.
- **FR-024**: The repository's manifest validation workflow MUST be able to render and validate the new namespace, workload, and Service before merge.
- **FR-025**: The feature MUST NOT add Prometheus, Grafana, alerting rules, long-term metric storage, per-container metrics, or any external access path.
- **FR-026**: The feature MUST NOT introduce secrets, tokens, private keys, real tailnet identifiers, or household data into the repository or documentation.
- **FR-027**: The user-facing documentation MUST be added to the repository documentation index and linked from the relevant README sections so an operator can find the metric contract, UI steps, and recovery procedures without reading the specification.
- **FR-028**: The exporter MUST expose the charging/discharging status of every host battery found under `/sys/class/power_supply` whose `type` is `Battery`, with labels identifying the battery device, the raw kernel status, and the source path.
- **FR-029**: The battery status value MUST be the raw kernel `status` string, such as `Charging`, `Discharging`, `Full`, `Not charging`, or `Unknown`; the exporter MUST NOT fabricate a charging/discharging value when the kernel reports another state.
- **FR-030**: When the host has multiple batteries, the exporter MUST expose all of them with device labels and MUST choose a deterministic preferred battery for the single Home Assistant status sensor; the selection rule MUST be documented.
- **FR-031**: When the host has no battery or the status source is unreadable, the battery status series MUST be absent or the value MUST be null, the exporter MUST expose an availability indicator, the other metrics MUST continue to work, and the Home Assistant battery sensor MUST become unavailable rather than displaying a fabricated value.
- **FR-032**: Battery status collection MUST use the existing read-only `/sys` access. It MUST NOT add a NUT/UPS service, USB or device access, privileged mode, or a new secret.
- **FR-033**: The documentation MUST include verification and recovery steps for battery status changes, an absent battery, an unreadable status file, and a battery that disappears at runtime.

### Metric Contract

The contract below defines what must be measurable. The implementation plan chooses whether these
are emitted by a general-purpose host exporter or a small custom exporter, and fixes the exact
metric names. The documentation produced by the feature must map each row to the exact emitted
name.

| Measurement | Required semantics | Unit | Required labels | Absent-source behavior |
| ----------- | ------------------ | ---- | --------------- | ---------------------- |
| CPU/system temperature | Current die, package, or thermal-zone temperature | Degrees Celsius | Source device/chip and sensor identity | No series when no usable sensor exists; documentation explains the limitation |
| Memory total | Total usable host memory | Bytes | None required | Metric unavailable only if the host memory source is unreadable |
| Memory available | Memory available for new allocations | Bytes | None required | Metric unavailable only if the host memory source is unreadable |
| Memory usage | Used bytes and/or percentage derived from total and available | Bytes or percent | None required | Unavailable when total or available is unavailable |
| Root filesystem size | Capacity of the filesystem mounted at `/` | Bytes | Mount point `/` | Unavailable if the root filesystem cannot be read |
| Root filesystem available | Space available on `/` | Bytes | Mount point `/` | Unavailable if the root filesystem cannot be read |
| Root filesystem usage | Used bytes and/or percentage derived from size and available | Bytes or percent | Mount point `/` | Unavailable when size or available is unavailable |
| IPv4 address | Each active non-loopback IPv4 address, including Tailscale when present | Address carried in a label; the numeric sample value is `1` | Interface name, address label, and stable interface identity where available | Active addresses appear and disappear with the interfaces; no fabricated address |
| Battery charging status | Raw kernel `power_supply` status for each host battery | No unit; the status string is carried in a label and the numeric sample value is `1` | Battery device name, raw status, and source path | No series when no battery exists; availability indicator is `0`; documentation explains the limitation |

### Key Entities

- **Exporter Workload**: The GitOps-managed process scheduled on `dietpi` that reads host metrics and serves them over HTTP.
- **Internal Service**: The cluster-only network identity and stable DNS name through which Home Assistant reaches the exporter.
- **Host Metric Sample**: A timestamped value with a unit and labels representing temperature, memory, filesystem, an IPv4 address, or battery status.
- **Battery Status Reading**: The raw kernel charging/discharging status of a host `power_supply` battery, with the battery device and source path.
- **Metric Contract**: The documented mapping from household-visible measurements to exact emitted metric names, labels, units, and absence semantics.
- **Home Assistant Sensor**: A manually created UI entity that reads the exporter through a built-in integration and displays a household-visible value.
- **Household Operator**: The person who merges the GitOps change, performs the Home Assistant UI steps, and follows recovery procedures.

## Success Criteria _(mandatory)_

### Measurable Outcomes

- **SC-001**: A merged exporter change is reconciled into the cluster and the exporter pod is Ready on `dietpi` within 10 minutes, with no manual `kubectl` apply.
- **SC-002**: From a pod in the `home-assistant` namespace, the documented metrics URL returns HTTP 200 within 5 seconds on 100% of 10 consecutive requests while the exporter is Ready.
- **SC-003**: The endpoint contains temperature (when supported), memory total, memory available, root filesystem size, root filesystem available, at least the Tailscale IPv4, and battery status (when supported) in every complete sample.
- **SC-004**: A household operator following only the documentation can create all five sensor groups in under 15 minutes and see a non-unknown value for each supported measurement.
- **SC-005**: Each Home Assistant sensor updates within two scan intervals of a measurable host change, and all sensors resume updating within two scan intervals after an exporter restart.
- **SC-006**: After a deliberate exporter pod deletion, the endpoint is reachable again within 2 minutes without operator action.
- **SC-007**: After a node reboot, the exporter is Ready and the endpoint is reachable within 10 minutes of k3s becoming available, without operator action.
- **SC-008**: Inspecting the cluster shows zero external exposure paths for the exporter: no Ingress, no load balancer, no node port, no host port, and no host networking.
- **SC-009**: On a host without a usable temperature sensor, the exporter remains Ready and all other supported metrics remain available; the documentation identifies the missing temperature sensor and the expected unavailable state.
- **SC-010**: Secret scanning and repository review find zero credentials, tokens, real tailnet identifiers, state bundles, or Home Assistant repository changes introduced by this feature.
- **SC-011**: The documented recovery procedures restore normal operation for a stopped exporter, a node reboot, and a missing host path, as demonstrated on the real cluster.
- **SC-012**: On a host with a battery, the Home Assistant battery sensor shows the current kernel status (`Charging`, `Discharging`, `Full`, `Not charging`, or `Unknown`) and changes within two scan intervals of a real status change; on a host without a battery, the sensor is unavailable and the other sensors remain functional.

## Out of Scope

- Editing the Home Assistant configuration repository, adding Home Assistant YAML, or adding automations, scripts, scenes, or dashboards.
- Prometheus, Grafana, alerting, recording rules, long-term metric storage, and historical analysis.
- Per-container, per-pod, or per-application metrics.
- External access to the exporter, including Traefik ingress, Tailscale ingress, load balancers, node ports, and host ports.
- High availability, multi-node scheduling, and replicated metrics storage.
- IPv6 address reporting, network throughput, disk I/O, uptime, battery charge percentage, battery health, battery runtime, and other host metrics not listed in the metric contract.
- NUT, UPS daemons, USB battery/device access, and any charging-status source other than the host's Linux `power_supply` battery interface.
- Automatic creation or provisioning of Home Assistant sensors.
- Changing the Home Assistant Scrape polling cadence. The UI-only integration polls every 10 minutes; a different cadence would require Home Assistant YAML or HACS.

## Dependencies

- A healthy single-node k3s cluster on `dietpi` with Flux reconciling this repository.
- A working `home-assistant` namespace and a Home Assistant user with administrator access to the UI.
- A container image for the chosen exporter that is publicly pullable and can be pinned immutably.
- Host access to memory, filesystem, hwmon or thermal-zone data, network interface information, and `/sys/class/power_supply` battery status, readable without privileged mode or a secret.
- Tailscale enrolled on the host, with an IPv4 address on a dedicated interface.
- A Home Assistant built-in integration that can be configured entirely through the UI and can extract values from the exporter's machine-readable representation without HACS or YAML edits.

## Assumptions

- The node is named `dietpi`, is the only schedulable node, and hosts both Home Assistant and the exporter.
- The exporter is named `host-metrics`, lives in the `monitoring` namespace, and is reached at the documented internal URL on port 9100 unless the plan documents a different stable value.
- The Tailscale IPv4 address is the stable address the household operator wants to display; LAN and other active IPv4 addresses are exposed when the host provides them.
- The root filesystem mounted at `/` is the filesystem of interest for storage usage.
- The charging-status source is a host battery exposed by Linux `power_supply` with `type: Battery`; no NUT, UPS daemon, USB device access, or separate battery integration is added.
- The host may have no battery. If it does not, battery status is unavailable, the other metrics continue to work, and a battery sensor in Home Assistant is unavailable rather than fabricated.
- Memory total and available are sufficient to derive the displayed memory usage; the exporter or Home Assistant may perform that derivation.
- The Home Assistant built-in Scrape integration can consume the exporter's JSON representation through the UI. Planning verified that it supports the required resource URL, selector, value template, availability template, unit, device class, and state class. Its UI does not expose a scan interval, so it polls every 10 minutes; faster polling would require YAML or HACS and is out of scope.
- The household operator is authorized to merge to the tracked branch and to administer Home Assistant.
- No metric is invented when its host source is unavailable; an unavailable sensor is preferable to a misleading value.
- The exporter is a convenience for household visibility, not an availability-critical service; brief unavailability during restarts and reboots is acceptable.
- The existing single-node limitations, backup procedures, and node-rebuild procedures remain unchanged by this feature.
