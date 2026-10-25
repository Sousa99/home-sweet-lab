# Contract: Host Metrics Exporter HTTP API

**Feature**: `specs/002-host-metrics-exporter`
**Version**: 1
**Stability**: The metric names, JSON keys, endpoint paths, and units in this document are the
public contract. Renaming or removing them is a breaking change and requires updating the Home
Assistant UI steps and this contract together.

## Endpoints

The exporter listens on port `9100` inside the `monitoring` namespace and is published by a
ClusterIP Service named `host-metrics`.

| Method | Path | Purpose | Content type |
| ------ | ---- | ------- | ------------ |
| GET | `/metrics` | Prometheus text exposition | `text/plain; version=0.0.4; charset=utf-8` |
| GET | `/ha` | Flat JSON projection for the Home Assistant Scrape UI | `application/json; charset=utf-8` |
| GET | `/healthz` | Liveness | `text/plain; charset=utf-8` |
| GET | `/readyz` | Readiness | `text/plain; charset=utf-8` |

Documented URLs from the `home-assistant` namespace:

```text
http://host-metrics.monitoring.svc.cluster.local:9100/metrics
http://host-metrics.monitoring.svc.cluster.local:9100/ha
http://host-metrics.monitoring.svc.cluster.local:9100/healthz
http://host-metrics.monitoring.svc.cluster.local:9100/readyz
```

The Service is `ClusterIP` only. There is no Ingress, Tailscale ingress, load balancer, node port,
host port, or host networking. The endpoint is not reachable from outside the cluster.

## Common behavior

- Responses are `Cache-Control: no-store`.
- No authentication, no cookies, no secrets, no request body.
- Methods other than GET return `405` with `Allow: GET`.
- Unknown paths return `404`.
- Collection is performed per request; there is no background cache and no persistent state.
- `/metrics` and `/ha` return `200` with partial data when one optional source is unavailable, as
  described below.
- An unexpected unhandled collection error returns `500` and is logged. Home Assistant treats a
  failed poll as an unavailable sensor.
- The exporter never writes to a host mount.

## `GET /metrics`

Prometheus text format. Every sample is a gauge unless marked as an info metric. Metric names use
the `host_` prefix and units are part of the name (`_bytes`, `_celsius`, `_percent`).

### Metric families

#### `host_system_temperature_celsius`

Current CPU/system temperature.

| Property | Value |
| -------- | ----- |
| Type | gauge |
| Unit | degrees Celsius |
| Labels | `source`, `chip`, `sensor`, `path` |
| Presence | One series per usable reading. Omitted entirely when no usable hwmon or thermal-zone reading exists. |

Labels:

- `source`: `hwmon` or `thermal_zone`.
- `chip`: hwmon `name` (for example `coretemp`, `k10temp`, `nct6775`), or `thermal` for a thermal
  zone.
- `sensor`: hwmon `temp*_label` when present, otherwise the input file name; thermal-zone `type`.
- `path`: the container-visible source path, for example
  `/host/sys/class/hwmon/hwmon0/temp1_input`.

Example:

```text
# HELP host_system_temperature_celsius Host CPU/system temperature in degrees Celsius.
# TYPE host_system_temperature_celsius gauge
host_system_temperature_celsius{source="hwmon",chip="coretemp",sensor="Package id 0",path="/host/sys/class/hwmon/hwmon0/temp1_input"} 45.0
```

#### `host_metrics_temperature_available`

Whether at least one usable temperature reading exists.

| Property | Value |
| -------- | ----- |
| Type | gauge |
| Unit | 0 or 1 |
| Labels | none |
| Presence | Always |

Example:

```text
# HELP host_metrics_temperature_available Whether a usable temperature source was found.
# TYPE host_metrics_temperature_available gauge
host_metrics_temperature_available 1
```

#### `host_memory_total_bytes`

Total usable host memory.

| Property | Value |
| -------- | ----- |
| Type | gauge |
| Unit | bytes |
| Labels | none |
| Presence | Present when `/host/proc/meminfo` is readable and parseable. |

#### `host_memory_available_bytes`

Memory available for new allocations (`MemAvailable`, with the documented fallback).

| Property | Value |
| -------- | ----- |
| Type | gauge |
| Unit | bytes |
| Labels | none |
| Presence | Present when memory is readable. |

#### `host_memory_used_bytes`

`host_memory_total_bytes - host_memory_available_bytes`.

| Property | Value |
| -------- | ----- |
| Type | gauge |
| Unit | bytes |
| Labels | none |
| Presence | Present when memory is readable. |

#### `host_memory_usage_percent`

`host_memory_used_bytes / host_memory_total_bytes * 100`.

| Property | Value |
| -------- | ----- |
| Type | gauge |
| Unit | percent, 0–100 |
| Labels | none |
| Presence | Present when memory is readable. |

Example:

```text
# HELP host_memory_total_bytes Total usable host memory in bytes.
# TYPE host_memory_total_bytes gauge
host_memory_total_bytes 16106127360
# HELP host_memory_available_bytes Host memory available for new allocations in bytes.
# TYPE host_memory_available_bytes gauge
host_memory_available_bytes 12345678900
# HELP host_memory_used_bytes Host memory used in bytes (total minus available).
# TYPE host_memory_used_bytes gauge
host_memory_used_bytes 3760447460
# HELP host_memory_usage_percent Host memory usage percentage (0-100).
# TYPE host_memory_usage_percent gauge
host_memory_usage_percent 23.4
```

#### `host_filesystem_size_bytes`

Capacity of the filesystem mounted at `/`.

| Property | Value |
| -------- | ----- |
| Type | gauge |
| Unit | bytes |
| Labels | `mountpoint` (always `/`) |
| Presence | Present when `statvfs("/host/root")` succeeds. |

#### `host_filesystem_available_bytes`

Space available to an unprivileged process on `/` (`f_bavail * f_frsize`).

| Property | Value |
| -------- | ----- |
| Type | gauge |
| Unit | bytes |
| Labels | `mountpoint` (always `/`) |
| Presence | Present when storage is readable. |

#### `host_filesystem_used_bytes`

`host_filesystem_size_bytes - host_filesystem_available_bytes`.

| Property | Value |
| -------- | ----- |
| Type | gauge |
| Unit | bytes |
| Labels | `mountpoint` (always `/`) |
| Presence | Present when storage is readable. |

#### `host_filesystem_usage_percent`

`host_filesystem_used_bytes / host_filesystem_size_bytes * 100`.

| Property | Value |
| -------- | ----- |
| Type | gauge |
| Unit | percent, 0–100 |
| Labels | `mountpoint` (always `/`) |
| Presence | Present when storage is readable. |

Example:

```text
# HELP host_filesystem_size_bytes Root filesystem capacity in bytes.
# TYPE host_filesystem_size_bytes gauge
host_filesystem_size_bytes{mountpoint="/"} 1000000000000
# HELP host_filesystem_available_bytes Root filesystem space available in bytes.
# TYPE host_filesystem_available_bytes gauge
host_filesystem_available_bytes{mountpoint="/"} 900000000000
# HELP host_filesystem_used_bytes Root filesystem space used in bytes (size minus available).
# TYPE host_filesystem_used_bytes gauge
host_filesystem_used_bytes{mountpoint="/"} 100000000000
# HELP host_filesystem_usage_percent Root filesystem usage percentage (0-100).
# TYPE host_filesystem_usage_percent gauge
host_filesystem_usage_percent{mountpoint="/"} 10.0
```

#### `host_network_ipv4_info`

Info metric for every active non-loopback IPv4 address.

| Property | Value |
| -------- | ----- |
| Type | gauge |
| Unit | 1 (info metric; the address is in a label) |
| Labels | `interface`, `address`, `tailscale` |
| Presence | One series per active address. Omitted when the host network source is unreadable. |

Labels:

- `interface`: route-derived interface name, or `unknown`.
- `address`: dotted-quad IPv4 address.
- `tailscale`: `true` only when `interface="tailscale0"`, otherwise `false`.

Example:

```text
# HELP host_network_ipv4_info Active non-loopback IPv4 address by interface.
# TYPE host_network_ipv4_info gauge
host_network_ipv4_info{interface="tailscale0",address="<tailscale-ipv4>",tailscale="true"} 1
host_network_ipv4_info{interface="<lan-interface>",address="<lan-ipv4>",tailscale="false"} 1
```

#### `host_battery_status_info`

Info metric for each host battery's raw charging/discharging status.

| Property | Value |
| -------- | ----- |
| Type | gauge |
| Unit | 1 (info metric; the status is in a label) |
| Labels | `device`, `status`, `path` |
| Presence | One series per readable battery whose `type` is `Battery`. Omitted when the host has no battery. |

Labels:

- `device`: directory name under `/sys/class/power_supply/`, for example `BAT0`.
- `status`: trimmed raw kernel status, for example `Charging`, `Discharging`, `Full`,
  `Not charging`, or `Unknown`.
- `path`: container-visible source path, for example
  `/host/sys/class/power_supply/BAT0/status`.

The raw kernel string is preserved. `Full` and `Not charging` are not mapped to `Charging` or
`Discharging`. If multiple batteries exist, one series is emitted per battery.

Example:

```text
# HELP host_battery_status_info Host battery charging/discharging status.
# TYPE host_battery_status_info gauge
host_battery_status_info{device="BAT0",status="Discharging",path="/host/sys/class/power_supply/BAT0/status"} 1
```

#### `host_metrics_battery_available`

Whether at least one readable battery status exists.

| Property | Value |
| -------- | ----- |
| Type | gauge |
| Unit | 0 or 1 |
| Labels | none |
| Presence | Always |

Example:

```text
# HELP host_metrics_battery_available Whether a readable host battery status exists.
# TYPE host_metrics_battery_available gauge
host_metrics_battery_available 1
```

#### `host_metrics_info`

Exporter identity.

| Property | Value |
| -------- | ----- |
| Type | gauge |
| Unit | 1 (info metric) |
| Labels | `version` |
| Presence | Always |

Example:

```text
# HELP host_metrics_info Host metrics exporter information.
# TYPE host_metrics_info gauge
host_metrics_info{version="1"} 1
```

### Absence semantics

| Condition | `/metrics` behavior |
| --------- | ------------------- |
| No usable temperature sensor | No `host_system_temperature_celsius` series; `host_metrics_temperature_available 0`. |
| One of several hwmon inputs unreadable | That reading is skipped; other readings remain. |
| Memory source unreadable | Memory families are omitted; `/readyz` returns 503. |
| Root filesystem source unreadable | Filesystem families are omitted; `/readyz` returns 503. |
| Host network source unreadable | IP family is omitted; other families remain; `/readyz` may still be 200. |
| No battery or no readable `power_supply` status | Battery family is omitted; `host_metrics_battery_available 0`; other families remain; `/readyz` remains 200. |
| One of several batteries unreadable | That battery is skipped; other battery series remain. |
| Process down | Connection failure; no HTTP response. |

## `GET /ha`

Flat JSON projection for the Home Assistant Scrape UI. Keys intended for sensors are top-level.
Missing values are `null` rather than omitted, so a template can test them without raising an
undefined-key error. `collected_at`, `ipv4_addresses`, and `battery_statuses` are always present.

### Response schema

```json
{
  "collected_at": "2026-10-25T12:34:56Z",
  "temperature_c": 45.0,
  "temperature_source": "hwmon/coretemp/Package id 0",
  "temperature_path": "/host/sys/class/hwmon/hwmon0/temp1_input",
  "memory_total_bytes": 16106127360,
  "memory_available_bytes": 12345678900,
  "memory_used_bytes": 3760447460,
  "memory_usage_percent": 23.4,
  "storage_total_bytes": 1000000000000,
  "storage_available_bytes": 900000000000,
  "storage_used_bytes": 100000000000,
  "storage_usage_percent": 10.0,
  "ipv4_addresses": [
    {
      "interface": "tailscale0",
      "address": "<tailscale-ipv4>",
      "tailscale": true,
      "netmask": 32
    },
    {
      "interface": "<lan-interface>",
      "address": "<lan-ipv4>",
      "tailscale": false,
      "netmask": 24
    }
  ],
  "tailscale_ipv4": "<tailscale-ipv4>",
  "battery_status": "Discharging",
  "battery_device": "BAT0",
  "battery_path": "/host/sys/class/power_supply/BAT0/status",
  "battery_statuses": [
    {
      "device": "BAT0",
      "status": "Discharging",
      "path": "/host/sys/class/power_supply/BAT0/status",
      "preferred": true
    }
  ]
}
```

### Field rules

| Key | Type | Null behavior |
| --- | ---- | ------------- |
| `collected_at` | ISO 8601 UTC string | Never null. |
| `temperature_c` | number | Null when no usable temperature sensor. |
| `temperature_source` | string | Null when no usable temperature sensor; format `source/chip/sensor`. |
| `temperature_path` | string | Null when no usable temperature sensor. |
| `memory_total_bytes` | integer | Null when memory is unreadable. |
| `memory_available_bytes` | integer | Null when memory is unreadable. |
| `memory_used_bytes` | integer | Null when memory is unreadable. |
| `memory_usage_percent` | number | Null when memory is unreadable. |
| `storage_total_bytes` | integer | Null when storage is unreadable. |
| `storage_available_bytes` | integer | Null when storage is unreadable. |
| `storage_used_bytes` | integer | Null when storage is unreadable. |
| `storage_usage_percent` | number | Null when storage is unreadable. |
| `ipv4_addresses` | array | Empty array when the network source is unreadable or no address is active. |
| `tailscale_ipv4` | string | Null when no `tailscale0` address exists. |
| `battery_status` | string | Null when no readable battery exists. Raw kernel status otherwise. |
| `battery_device` | string | Null when no readable battery exists; otherwise the preferred device name. |
| `battery_path` | string | Null when no readable battery exists; otherwise the preferred status path. |
| `battery_statuses` | array of `{device, status, path, preferred}` | Empty array when no readable battery exists. One entry per battery, sorted by device name; exactly one `preferred: true` when non-empty. |

### Absence example (no temperature sensor or battery)

```json
{
  "collected_at": "2026-10-25T12:34:56Z",
  "temperature_c": null,
  "temperature_source": null,
  "temperature_path": null,
  "memory_total_bytes": 16106127360,
  "memory_available_bytes": 12345678900,
  "memory_used_bytes": 3760447460,
  "memory_usage_percent": 23.4,
  "storage_total_bytes": 1000000000000,
  "storage_available_bytes": 900000000000,
  "storage_used_bytes": 100000000000,
  "storage_usage_percent": 10.0,
  "ipv4_addresses": [],
  "tailscale_ipv4": null,
  "battery_status": null,
  "battery_device": null,
  "battery_path": null,
  "battery_statuses": []
}
```

## `GET /healthz`

Liveness endpoint. Returns `200` with a short text body while the HTTP server is running,
regardless of collection failures. A broken host path should make the pod unready, not restart-loop.

```text
ok
```

## `GET /readyz`

Readiness endpoint. Returns `200` when memory and root filesystem collection both succeed; returns
`503` when either source is unavailable. Temperature and IP failures do not make the exporter
unready, because both are optional or may legitimately be absent.

Success body:

```text
ready
```

Failure example:

```text
not ready: memory unavailable; storage unavailable
```

The exact failure text is diagnostic and not part of the sensor contract.

## Collection and error handling

| Failure | Behavior |
| ------- | -------- |
| `/host/proc/meminfo` missing or unreadable | Memory keys are null; memory families omitted; `/readyz` 503; error logged. |
| `/host/proc/meminfo` has no `MemAvailable` | Fallback formula is used; no error if the fallback is computable. |
| `/host/proc/1/net` missing or unreadable | IP list is empty; `tailscale_ipv4` is null; `/readyz` remains 200; warning logged. |
| `/host/sys/class/hwmon` missing or empty | Thermal-zone fallback is attempted. |
| `/host/sys/class/thermal` missing or empty | Temperature is absent; `temperature_c` null; `/readyz` remains 200. |
| One hwmon input unreadable | That reading is skipped; other readings are served. |
| No `power_supply` device with `type: Battery` | Battery family is omitted; `host_metrics_battery_available 0`; `battery_status` null; `/readyz` remains 200. |
| A battery's `status` file is unreadable | That battery is skipped; other batteries and metrics remain. |
| A battery is removed at runtime | Its series disappears on the next collection; `battery_status` becomes null if no battery remains; Home Assistant sensor becomes unavailable. |
| `statvfs("/host/root")` fails | Storage keys are null; filesystem families omitted; `/readyz` 503. |
| Unexpected exception in collection | `500` for that request; error logged; Home Assistant marks the poll failed. |

## Security contract

- No authentication is required because the Service is cluster-internal only.
- No secrets, tokens, or credentials are read or exposed.
- No host write occurs.
- The response does not include environment variables, process lists, command lines, or file
  contents beyond the documented metric values.
- Real deployment values (IP addresses) are runtime data and must never be copied into Git or
  documentation examples; examples use placeholders.
