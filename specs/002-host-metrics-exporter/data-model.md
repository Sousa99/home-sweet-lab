# Phase 1 Data Model: Host Metrics Exporter and Home Assistant Integration

**Feature**: `specs/002-host-metrics-exporter`
**Date**: 2026-10-25

This is a stateless runtime data model. No database, persistent volume, or metric history is
introduced. Each scrape builds a fresh snapshot from host files; Home Assistant keeps whatever
history its own recorder policy provides.

## Entity Overview

```text
HostSnapshot
├── collected_at
├── temperatures[] : TemperatureReading
├── memory?        : MemoryReading
├── storage?       : StorageReading
├── ipv4_addresses[] : IPv4Address
└── batteries[]    : BatteryReading

Deployment/Service/ConfigMap are declared Kubernetes entities, not runtime data.
HomeAssistantSensor maps a HostSnapshot field to a UI-created entity.
```

## HostSnapshot

The complete result of one collection pass.

| Field | Type | Required | Validation |
| ----- | ---- | -------- | ---------- |
| `collected_at` | ISO 8601 UTC timestamp | Yes | Generated at collection time; never in the future beyond clock skew. |
| `temperatures` | list of `TemperatureReading` | Yes | May be empty when no usable hwmon or thermal-zone source exists; one reading is preferred when non-empty. |
| `memory` | `MemoryReading` or null | No | Null only when meminfo cannot be read or parsed. |
| `storage` | `StorageReading` or null | No | Null only when root filesystem `statvfs` fails. |
| `ipv4_addresses` | list of `IPv4Address` | Yes | May be empty; no fabricated entries; loopback excluded. |
| `batteries` | list of `BatteryReading` | Yes | May be empty; no fabricated entries; deterministic order by device name. |

### Snapshot states

| State | Temperature | Battery | Memory | Storage | IPv4 | `/metrics` | `/ha` | `/readyz` |
| ----- | ----------- | ------- | ------ | ------- | ---- | ---------- | ----- | --------- |
| Healthy | Present | Present | Present | Present | Present or empty | 200, all available families | 200, no nulls except an empty IP list | 200 |
| Degraded (no temperature) | Null | Any | Present | Present | Present or empty | 200, temperature family omitted; `host_metrics_temperature_available 0` | 200, `temperature_c: null` | 200 |
| Degraded (no battery) | Any | Empty | Present | Present | Present or empty | 200, battery family omitted; `host_metrics_battery_available 0` | 200, `battery_status: null` | 200 |
| Degraded (no IP source) | Any | Any | Present | Present | Empty | 200, IP family omitted | 200, `tailscale_ipv4: null`, empty array | 200 |
| Unready (memory or storage failure) | Any | Any | Null or present | Null or present | Any | 200, partial families | 200, nulls for failed fields | 503 |
| Process down | — | — | — | — | — | Connection failure | Connection failure | Connection failure |

`/healthz` is 200 while the HTTP server is alive, independent of collection success. It is used as a
liveness probe so a broken host path does not cause a useless restart loop. `/readyz` is stricter
and gates Service endpoints.

## TemperatureReading

| Field | Type | Required | Validation |
| ----- | ---- | -------- | ---------- |
| `celsius` | float | Yes | Finite; millidegrees divided by 1000; no rounding beyond one decimal in output. |
| `source` | string | Yes | `hwmon` or `thermal_zone`. |
| `chip` | string | Yes | hwmon `name`, or `thermal` for thermal zones. |
| `sensor` | string | Yes | hwmon `temp*_label` if present, else input file name; thermal-zone `type`. |
| `path` | string | Yes | Host path read, expressed as a container-visible path under `/host/sys`. |
| `preferred` | boolean | Yes | Exactly one reading is preferred when at least one is usable. |

### Temperature selection rules

1. Prefer hwmon over thermal zones.
2. Among hwmon, prefer names associated with CPU/system packages: `coretemp`, `k10temp`,
   `zenpower`, `cpu_thermal`, `soc_thermal`.
3. Among remaining candidates, prefer labels containing `Package`, `Tctl`, `Tdie`, `CPU`, or
   `Core`, case-insensitive.
4. Otherwise use the first usable reading in deterministic path order.
5. No usable reading: no `TemperatureReading`, no temperature metric, `host_metrics_temperature_available 0`,
   `temperature_c: null`.

## MemoryReading

| Field | Type | Required | Validation |
| ----- | ---- | -------- | ---------- |
| `total_bytes` | integer | Yes | `MemTotal` from `/host/proc/meminfo` × 1024; > 0. |
| `available_bytes` | integer | Yes | `MemAvailable` × 1024; if missing, `MemFree + Buffers + Cached + SReclaimable - Shmem` × 1024; >= 0; <= total. |
| `used_bytes` | integer | Yes | `total_bytes - available_bytes`; >= 0. |
| `usage_percent` | float | Yes | `used_bytes / total_bytes * 100`; 0–100; one decimal in output. |

## StorageReading

| Field | Type | Required | Validation |
| ----- | ---- | -------- | ---------- |
| `mountpoint` | string | Yes | Exactly `/`. |
| `total_bytes` | integer | Yes | `f_blocks * f_frsize` from `statvfs("/host/root")`; > 0. |
| `available_bytes` | integer | Yes | `f_bavail * f_frsize`; >= 0; <= total. |
| `used_bytes` | integer | Yes | `total_bytes - available_bytes`; >= 0. |
| `usage_percent` | float | Yes | `used_bytes / total_bytes * 100`; 0–100; one decimal in output. |

`f_bavail` is used deliberately: it represents space available to an unprivileged process, and
`total - available` is the intuitive household "used" value. Reserved filesystem blocks are counted
as used. This is documented in the operator guide.

## IPv4Address

| Field | Type | Required | Validation |
| ----- | ---- | -------- | ---------- |
| `interface` | string | Yes | Route-derived interface name, or `unknown` when no connected route matches. |
| `address` | string | Yes | Valid dotted-quad IPv4 address, not in `127.0.0.0/8`. |
| `tailscale` | boolean | Yes | True only when the interface is `tailscale0`; used to select `tailscale_ipv4`. |
| `netmask` | integer | No | Prefix length from the connected route, when known. |

### Address rules

- Source: `/host/proc/1/net/fib_trie`, entries followed by `/32 host LOCAL`.
- Exclude loopback.
- Do not fabricate an address when the source is unreadable; return an empty list.
- Deduplicate identical `(interface, address)` pairs.
- Sort deterministically: Tailscale first, then interface name, then address.
- `tailscale_ipv4` is the address of `tailscale0` if present; otherwise null. A CGNAT address is not
  labeled Tailscale unless the interface itself is `tailscale0`.

## BatteryReading

| Field | Type | Required | Validation |
| ----- | ---- | -------- | ---------- |
| `device` | string | Yes | Directory name under `/host/sys/class/power_supply/`, for example `BAT0`. |
| `status` | string | Yes | Trimmed raw kernel `status` value, for example `Charging`, `Discharging`, `Full`, `Not charging`, or `Unknown`. No normalization. |
| `path` | string | Yes | Source path, for example `/host/sys/class/power_supply/BAT0/status`. |
| `preferred` | boolean | Yes | Exactly one reading is preferred when at least one battery exists. |

### Battery rules

- Enumerate directories under `/host/sys/class/power_supply/` whose `type` file contains `Battery`.
- Read each matching device's `status` file; skip a device if either file is unreadable.
- Sort by device name lexicographically; the first is the preferred battery for the single Home
  Assistant sensor.
- Expose every reading in `/metrics`; expose the preferred as flat `battery_status` and all as
  `battery_statuses` in `/ha`.
- If no battery exists or no status is readable, return an empty list, `host_metrics_battery_available 0`,
  `battery_status: null`, and an empty `battery_statuses` array.
- Do not map `Full`, `Not charging`, or `Unknown` to `Charging` or `Discharging`.

## HTTP projections

### `/metrics` (Prometheus text)

| Metric | Type | Labels | Unit | Presence |
| ------ | ---- | ------ | ---- | -------- |
| `host_system_temperature_celsius` | gauge | `source`, `chip`, `sensor`, `path` | degrees Celsius | One series per usable reading; omitted when none. |
| `host_metrics_temperature_available` | gauge | none | 0 or 1 | Always. |
| `host_memory_total_bytes` | gauge | none | bytes | When memory is readable. |
| `host_memory_available_bytes` | gauge | none | bytes | When memory is readable. |
| `host_memory_used_bytes` | gauge | none | bytes | When memory is readable. |
| `host_memory_usage_percent` | gauge | none | percent (0–100) | When memory is readable. |
| `host_filesystem_size_bytes` | gauge | `mountpoint="/"` | bytes | When storage is readable. |
| `host_filesystem_available_bytes` | gauge | `mountpoint="/"` | bytes | When storage is readable. |
| `host_filesystem_used_bytes` | gauge | `mountpoint="/"` | bytes | When storage is readable. |
| `host_filesystem_usage_percent` | gauge | `mountpoint="/"` | percent (0–100) | When storage is readable. |
| `host_network_ipv4_info` | gauge | `interface`, `address`, `tailscale` | 1 (info metric) | One series per active address; omitted when source unreadable. |
| `host_battery_status_info` | gauge | `device`, `status`, `path` | 1 (info metric) | One series per readable battery; omitted when no battery exists. |
| `host_metrics_battery_available` | gauge | none | 0 or 1 | Always. |
| `host_metrics_info` | gauge | `version` | 1 (info metric) | Always. |

The exact exposition format is fixed in `contracts/exporter-api.md`.

### `/ha` (Home Assistant JSON)

| Key | Type | Null behavior |
| --- | ---- | ------------- |
| `collected_at` | ISO 8601 UTC string | Never null. |
| `temperature_c` | number | Null when no usable sensor. |
| `temperature_source` | string | Null when no usable sensor; e.g. `hwmon/coretemp/Package id 0`. |
| `temperature_path` | string | Null when no usable sensor. |
| `memory_total_bytes` | integer | Null when memory is unreadable. |
| `memory_available_bytes` | integer | Null when memory is unreadable. |
| `memory_used_bytes` | integer | Null when memory is unreadable. |
| `memory_usage_percent` | number | Null when memory is unreadable. |
| `storage_total_bytes` | integer | Null when storage is unreadable. |
| `storage_available_bytes` | integer | Null when storage is unreadable. |
| `storage_used_bytes` | integer | Null when storage is unreadable. |
| `storage_usage_percent` | number | Null when storage is unreadable. |
| `ipv4_addresses` | array of `{interface, address, tailscale, netmask?}` | Empty array when unavailable. |
| `tailscale_ipv4` | string | Null when no `tailscale0` address exists. |
| `battery_status` | string | Null when no battery exists or its status is unreadable. |
| `battery_device` | string | Null when no battery exists; otherwise the preferred device name. |
| `battery_path` | string | Null when no battery exists; otherwise the preferred status path. |
| `battery_statuses` | array of `{device, status, path, preferred}` | Empty array when no battery exists. |

The exact schema is fixed in `contracts/exporter-api.md`.

## Home Assistant sensor mapping

These are UI-created entities, not files in this repository. The exact UI fields are in
`contracts/home-assistant-ui.md`.

| Sensor | JSON key | Template | Unit | Device class | State class |
| ------ | -------- | -------- | ---- | ------------ | ----------- |
| DietPi CPU temperature | `temperature_c` | `{{ value_json.temperature_c }}` | °C | Temperature | Measurement |
| DietPi RAM usage | `memory_usage_percent` | `{{ value_json.memory_usage_percent }}` | % | None | Measurement |
| DietPi storage usage | `storage_usage_percent` | `{{ value_json.storage_usage_percent }}` | % | None | Measurement |
| DietPi Tailscale IPv4 | `tailscale_ipv4` | `{{ value_json.tailscale_ipv4 }}` | None | None | None |
| DietPi IPv4 addresses (optional) | `ipv4_addresses` | `{{ value_json.ipv4_addresses \| map(attribute='address') \| join(', ') }}` | None | None | None |
| DietPi battery status | `battery_status` | `{{ value_json.battery_status }}` | None | None | None |

Availability templates:

- Temperature: `{{ value_json.temperature_c is not none }}`
- RAM: `{{ value_json.memory_usage_percent is not none }}`
- Storage: `{{ value_json.storage_usage_percent is not none }}`
- Tailscale IPv4: `{{ value_json.tailscale_ipv4 is not none }}`
- All IPv4: `{{ value_json.ipv4_addresses | length > 0 }}`
- Battery: `{{ value_json.battery_status is not none }}`

## Kubernetes entities

| Entity | Namespace | Validation |
| ------ | --------- | ---------- |
| `Namespace/monitoring` | cluster-scoped | Name exactly `monitoring`; Flux-managed. |
| `ConfigMap/host-metrics-script-<hash>` | `monitoring` | Generated from `exporter.py`; not edited by hand. |
| `Deployment/host-metrics` | `monitoring` | 1 replica; `nodeSelector` `kubernetes.io/hostname: dietpi`; no host network/PID/port; non-root; no privileged; probes; resources. |
| `Service/host-metrics` | `monitoring` | `type: ClusterIP`; port 9100; target port `http`. |
| Flux `Kustomization/apps` | `flux-system` | Includes `apps/host-metrics`; reconciles from `main`. |

## Validation rules summary

- No snapshot field is fabricated when its source is unavailable.
- Memory and storage usage never exceed 100% and are never negative.
- Temperature is in degrees Celsius, never millidegrees.
- Filesystem series always carries `mountpoint="/"`.
- IPv4 values are valid dotted-quad and never loopback.
- At most one temperature reading is marked `preferred`.
- At most one battery reading is marked `preferred`; the preferred battery is the lexicographically first device.
- Battery status is the raw kernel string and is never mapped from `Full`, `Not charging`, or `Unknown` into `Charging` or `Discharging`.
- The exporter never writes to a host mount.
- No entity contains a secret, token, kubeconfig, or real tailnet identifier.
