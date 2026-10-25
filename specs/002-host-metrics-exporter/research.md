# Phase 0 Research: Host Metrics Exporter and Home Assistant Integration

**Feature**: `specs/002-host-metrics-exporter`
**Date**: 2026-10-25
**Status**: Complete; no `NEEDS CLARIFICATION` remains.

## R1 — Exporter implementation

### Decision

Implement a small Python 3.12 standard-library HTTP exporter in
`apps/host-metrics/exporter.py`, delivered through a Kustomize `configMapGenerator` and run from
`python:3.12-alpine` pinned by digest
(`sha256:b658b05ce9c4eb97ec6fc19424818a1f31993659c2b505a532f470e83807815d`).

### Rationale

- The required data set is small and can be collected from `/proc`, `/sys`, a `power_supply`
  battery status file when present, and one `statvfs` call.
- A custom exporter can serve both Prometheus text at `/metrics` and the flat JSON projection at
  `/ha` that Home Assistant's UI-only Scrape integration can consume.
- Node Exporter does not expose host IPv4 addresses. Its `netdev` address-info collector uses Go's
  `net.Interfaces()`, which enumerates the container network namespace unless host networking is
  used. Host networking is forbidden by the specification.
- Adding Node Exporter plus a textfile-writing sidecar would require a second process, a shared
  writable volume, a scheduler loop, and a fragile Prometheus-text parser in Home Assistant.
- Keeping the script in Git and injecting it with `configMapGenerator` keeps the implementation
  reviewable and testable without a custom image build.

### Alternatives considered

| Alternative | Why rejected |
| ----------- | ------------ |
| Node Exporter only | No host IPv4 address metric; cannot satisfy the IP requirement without host networking or a sidecar. |
| Node Exporter + textfile sidecar | More moving parts, a writable shared volume, duplicate collectors, and still no clean JSON projection for Home Assistant. |
| Custom Go binary and GHCR image | Adds a build workflow, package publishing, tag policy, and image automation for a single-file script; higher operational surface. |
| `hostNetwork: true` | Exposes port 9100 on host interfaces, violating the no-external-exposure requirement; also forbidden by the specification. |
| Privileged container with `nsenter` | Broader than needed and violates least privilege. |

## R2 — Host access without host networking or host PID sharing

### Decision

Use read-only hostPath mounts:

- `/proc/meminfo` → `/host/proc/meminfo`
- `/proc/1/net` → `/host/proc/1/net`
- `/sys` → `/host/sys`
- `/` → `/host/root`

Do not use `hostNetwork`, `hostPID`, `hostIPC`, `hostPort`, or `privileged`.

### Rationale

- `/proc/meminfo` is a single file and does not require mounting all of `/proc`.
- `/proc/1/net` is the host init process's network namespace view. Mounting that directory gives
  the exporter the host's `fib_trie` and `route` tables without joining the host network or PID
  namespace.
- `/sys` must be mounted as a whole because `/sys/class/hwmon/hwmon*` entries are symlinks into
  `/sys/devices`; mounting only `/sys/class/hwmon` would break those links.
- `/` is mounted read-only only to call `statvfs` for the filesystem whose mount point is `/`.
- Running as UID/GID 65534 with all capabilities dropped and a read-only root filesystem is
  sufficient for these read-only files. If a host exposes a temperature input that is not readable
  by that user, temperature becomes unavailable while the other metrics continue; the feature does
  not escalate to root.

### Verification needed during implementation

- Confirm that the cluster's kubelet accepts a hostPath of `/proc/1/net` with type `Directory`.
- Confirm that a non-root container can read `/host/proc/1/net/fib_trie` and
  `/host/proc/1/net/route` from that mount. If not, the documented fallback is to mount host
  `/proc` read-only at `/host/proc` and read `/host/proc/1/net/*`; host networking and host PID
  sharing are still not used.
- Confirm that `/host/sys/class/hwmon` is readable as UID 65534.

## R3 — IPv4 discovery and interface mapping

### Decision

Read `/host/proc/1/net/fib_trie`, extract addresses followed by `/32 host LOCAL`, exclude loopback
(`127.0.0.0/8`), and map each address to an interface using the connected routes in
`/host/proc/1/net/route` (longest-prefix match, gateway `0.0.0.0`). If no route matches, label the
interface `unknown` but still expose the address. Identify the Tailscale address by
`interface="tailscale0"`. If route mapping fails but a `tailscale0` interface exists and the
address falls in `100.64.0.0/10`, assign it to `tailscale0`; do not label an address as Tailscale
solely by its range when the interface is absent. Do not fabricate an address.

### Rationale

- `/proc/net/fib_trie` is the only procfs source for IPv4 local addresses; `/proc/net/route` maps
  networks to interfaces.
- This works without host networking because the data comes from the host network namespace's
  procfs view.
- Values are collected on every scrape, so address changes and disappearing interfaces are
  reflected without restarting the exporter.
- Exposing every non-loopback address satisfies the "all active IPv4 or at minimum Tailscale"
  requirement. The JSON projection additionally provides a single `tailscale_ipv4` convenience
  field for Home Assistant.

### Alternatives considered

| Alternative | Why rejected |
| ----------- | ------------ |
| `hostNetwork: true` and Go `net.Interfaces()` | External exposure and explicitly forbidden. |
| `nsenter` into `/proc/1/ns/net` | Requires `CAP_SYS_ADMIN` or privileged mode; violates least privilege. |
| Kubernetes `status.hostIP` | Returns only the node's primary address (the observed InternalIP is a LAN address), not the Tailscale address and not all interfaces. |
| LAN-only or Tailscale-only hardcoding | Fails on address changes and does not satisfy "all active IPv4 or at minimum Tailscale" with interface labels. |

### Edge behavior

- Multiple addresses on one interface are all exposed with the same interface label.
- If the route table cannot map an address, the interface label is `unknown`; the address remains
  visible.
- If `/host/proc/1/net` is unreadable, IP metrics are absent, `tailscale_ipv4` is null, and the
  exporter remains Ready if memory and storage collection succeed. The condition is logged and
  documented.

## R4 — Temperature discovery

### Decision

Enumerate `/host/sys/class/hwmon/hwmon*` first. For each `temp*_input`, read millidegrees and divide
by 1000. Use `temp*_label` when present for the sensor label, otherwise the input file name. Include
`name` as the chip label. If no hwmon temperature is usable, fall back to
`/host/sys/class/thermal/thermal_zone*/temp` with `type` as the sensor label. Expose every usable
reading in `/metrics` with source/chip/sensor/path labels. For `/ha`, select a preferred reading:

1. hwmon names commonly associated with CPU packages (`coretemp`, `k10temp`, `zenpower`,
   `cpu_thermal`, `soc_thermal`);
2. labels containing `Package`, `Tctl`, `Tdie`, `CPU`, or `Core`;
3. the first usable reading.

If no reading is usable, `/metrics` omits the temperature family and sets
`host_metrics_temperature_available 0`; `/ha` sets `temperature_c: null`. A missing sensor is not an
error and does not block readiness.

### Rationale

- hwmon is the modern, labeled source and is preferred over thermal zones.
- Thermal zones are a fallback for hosts without hwmon, satisfying "hwmon or thermal zones".
- Exposing all sensors avoids guessing wrong when a host has multiple chips; the preferred reading
  gives Home Assistant one stable value.
- The availability template in Home Assistant turns a missing preferred reading into an unavailable
  entity rather than a fabricated zero.

## R5 — Memory and root filesystem usage semantics

### Decision

- Parse `MemTotal` and `MemAvailable` from `/host/proc/meminfo`; if `MemAvailable` is absent, derive
  it from `MemFree + Buffers + Cached + SReclaimable - Shmem`.
- `memory_used_bytes = memory_total_bytes - memory_available_bytes`.
- `memory_usage_percent = memory_used_bytes / memory_total_bytes * 100`, rounded to one decimal.
- Use `os.statvfs("/host/root")`: `total = f_blocks * f_frsize`, `available = f_bavail * f_frsize`.
- `storage_used_bytes = total - available`.
- `storage_usage_percent = used / total * 100`, rounded to one decimal.

### Rationale

- `MemAvailable` is the kernel's estimate of memory available for new allocations and matches user
  expectations better than `MemFree`.
- `f_bavail` is the space available to an unprivileged process; `total - f_bavail` is the intuitive
  "used" value for a household storage gauge. Reserved blocks are counted as used.
- These formulas are documented so Home Assistant values are reproducible and not tool-specific.

### Edge behavior

- If `MemAvailable` is missing, the fallback formula is used.
- If `/host/proc/meminfo` cannot be parsed, memory values are null and `/readyz` returns 503.
- If `statvfs` fails, storage values are null and `/readyz` returns 503.
- The exporter always returns partial data at `/metrics` and `/ha` if only one source is broken;
  readiness is stricter than scrape availability.

## R6 — Home Assistant integration

### Decision

Use Home Assistant's built-in **Scrape** integration, configured entirely through the UI. The
resource is `http://host-metrics.monitoring.svc.cluster.local:9100/ha`. Each sensor uses
`select: body`, a JSON `value_template`, an availability template for optional values, and the
documented unit/device class/state class. No Home Assistant YAML, HACS, or automation is added.

### Rationale

- The Scrape integration has a UI config flow and configuration subentries for multiple sensors.
- Its coordinator parses responses with BeautifulSoup and `lxml`. A JSON document is parsed as
  `<html><body>{...}</body></html>`, so `select: body` returns the raw JSON and `value_json` works.
  This behavior was verified locally with `beautifulsoup4` and `lxml`.
- The UI config flow exposes resource URL, method, headers, authentication, timeout, encoding,
  selector, index, value template, availability template, device class, state class, and unit.
- The UI does not expose `scan_interval`; the integration default is 10 minutes. Faster polling
  would require YAML or HACS, both out of scope. This is documented as a limitation.

### Alternatives considered

| Alternative | Why rejected |
| ----------- | ------------ |
| Scrape `/metrics` with CSS selectors | Prometheus text is not HTML; per-sensor extraction is fragile and the preferred temperature selection is harder. |
| RESTful sensor | YAML-only; violates the no-Home-Assistant-YAML constraint. |
| HACS Prometheus/OpenMetrics integration | HACS is explicitly out of scope. |
| Home Assistant Prometheus integration | It exports Home Assistant metrics; it does not scrape an external exporter. |
| Push to Home Assistant webhooks | Requires Home Assistant automations/scripts and is out of scope. |

## R7 — Exposure and security

### Decision

Expose the exporter through a ClusterIP Service only:

- Service type `ClusterIP`, port `9100`, target port `http`.
- No Ingress, Tailscale ingress, LoadBalancer, NodePort, hostPort, or hostNetwork.
- Pod: `runAsNonRoot`, UID/GID 65534, `allowPrivilegeEscalation: false`,
  `readOnlyRootFilesystem: true`, `capabilities.drop: ["ALL"]`, `seccompProfile: RuntimeDefault`,
  `automountServiceAccountToken: false`.
- No Secret, ConfigMap (other than the exporter script), or writable host mount.

### Rationale

- The specification requires cluster-internal access only.
- The cluster's NetworkPolicy support has known k3s/kube-router problems and is disabled; adding a
  policy would be unreliable. The Service is therefore reachable from any pod but not from outside
  the cluster. This is documented rather than hidden.
- The exporter has no API credentials and no write path, so a compromise limits the blast radius
  to read-only host data.

## R8 — Battery charging status

### Decision

Read `/host/sys/class/power_supply/*/type`; for every device whose type is `Battery`, read its
`status` file. Expose one `host_battery_status_info{device,status,path} 1` series per battery, a
`host_metrics_battery_available` 0/1 gauge, and `/ha` keys `battery_status`, `battery_device`,
`battery_path`, and `battery_statuses`. Preserve the raw kernel status string (`Charging`,
`Discharging`, `Full`, `Not charging`, `Unknown`). Select the preferred battery deterministically by
device name (lexicographic) and document the rule. If there is no battery, omit the series, set
`battery_status: null` and `host_metrics_battery_available 0`, and make the Home Assistant sensor
unavailable through its availability template.

### Rationale

- The user selected the host battery via Linux `power_supply` as the source.
- The existing read-only `/sys` mount already exposes `/sys/class/power_supply`; no new mount,
  service, device, privilege, or secret is required.
- Preserving the kernel string avoids mapping `Full` or `Not charging` into a misleading binary
  charging/discharging state. Home Assistant can display the actual state.
- A deterministic preferred battery keeps the single UI sensor stable on a multi-battery host while
  retaining all statuses in the machine-readable endpoint.

### Alternatives considered

| Alternative | Why rejected |
| ----------- | ------------ |
| NUT/`upsc` USB UPS | The user selected the host battery source; NUT adds a service, USB/device access, and likely privilege. |
| Binary `charging` gauge only | Loses `Full`, `Not charging`, and `Unknown`; the user asked for charging versus discharging status, not a lossy boolean. |
| Battery percentage/health/runtime | Out of scope; the request was status only. |
| Reading only `BAT0` | Fails on hosts with multiple batteries or different device names; enumerate by `type: Battery` instead. |

## R9 — Validation and recovery

### Decision

- Add unit tests for meminfo parsing, fib-trie extraction, route mapping, temperature selection,
  battery selection, usage calculations, Prometheus rendering, and JSON rendering.
- Extend `scripts/validate.sh` to run the unit tests with `python3 -m unittest`.
- Verify on the real cluster: Flux reconciliation, pod readiness on `dietpi`, endpoint reachability
  from `home-assistant`, metric presence, Home Assistant UI sensor creation, pod restart recovery,
  node reboot recovery, missing-temperature and missing-battery behavior, battery status changes,
  and no external exposure.
- Document recovery for exporter crash, pod restart, node reboot, missing host path, unreadable
  hwmon or `power_supply/*/status`, and missing temperature or battery.

### Rationale

- Parser logic is the most likely source of silent wrong values; unit tests with fixtures catch
  them without needing the host.
- The remaining acceptance criteria are inherently cluster-level: scheduling, hostPath behavior,
  Service DNS, Flux reconciliation, and Home Assistant UI.
- The exporter is stateless, so recovery is normal Kubernetes and Flux behavior rather than a
  bespoke restore procedure.

## Resolved unknowns

| Unknown | Resolution |
| ------- | ---------- |
| Node Exporter or custom exporter? | Custom Python stdlib exporter; Node Exporter lacks host IPv4 and cannot serve the JSON projection without extra moving parts. |
| How to read host IPs without host networking? | Read the host network namespace through a narrow read-only `/proc/1/net` mount and map addresses via `/proc/1/net/route`. |
| How to get exact root filesystem usage? | Read-only mount of host `/` and `statvfs("/host/root")`. |
| How to get temperature when hwmon is absent? | Fall back to thermal zones; if neither exists, omit temperature and mark it unavailable. |
| Where does charging status come from? | Host batteries under `/sys/class/power_supply` with `type: Battery`; preserve the raw kernel `status` string. No NUT/UPS service. |
| What if the host has no battery? | Omit the battery series, report `battery_status: null` and availability `0`, and keep the other metrics working. |
| What if there are multiple batteries? | Expose all statuses with device labels; choose the preferred battery lexicographically by device name and document the rule. |
| How can Home Assistant UI consume the data without YAML/HACS? | Built-in Scrape integration with `/ha` JSON, `select: body`, and `value_template`. |
| What is the Home Assistant update cadence? | The UI-only integration polls every 10 minutes; documented as a limitation. |
| How is external exposure prevented? | ClusterIP Service only; no ingress/load balancer/node port/host port/host network; offline exposure checks. |
| How is the exporter delivered without a custom image pipeline? | Git-tracked script in a Kustomize-generated ConfigMap; official Python image pinned by digest. |

## References

- Home Assistant Scrape integration documentation: <https://www.home-assistant.io/integrations/scrape/>
- Home Assistant Scrape config flow (UI fields): <https://github.com/home-assistant/core/blob/dev/homeassistant/components/scrape/config_flow.py>
- Home Assistant Scrape coordinator (BeautifulSoup/lxml parsing): <https://github.com/home-assistant/core/blob/dev/homeassistant/components/scrape/coordinator.py>
- Home Assistant Scrape sensor value extraction: <https://github.com/home-assistant/core/blob/dev/homeassistant/components/scrape/sensor.py>
- Node Exporter netdev collector (address info uses the process network namespace): <https://github.com/prometheus/node_exporter/blob/master/collector/netdev_common.go>
- Node Exporter host mount guidance: <https://github.com/prometheus/node_exporter>
- Kubernetes hostPath and Pod security standards: <https://kubernetes.io/docs/concepts/storage/volumes/> and <https://kubernetes.io/docs/concepts/security/pod-security-standards>
- Linux `/proc/net/fib_trie` local address extraction: <https://sleeplessbeastie.eu/2022/11/30/how-to-display-ipv4-addresses-without-network-utilities/>
