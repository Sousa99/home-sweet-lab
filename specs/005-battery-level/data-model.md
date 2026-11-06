# Phase 1 Data Model: Battery Level Percentage

**Feature**: `specs/005-battery-level`
**Date**: 2026-11-06

This feature extends the stateless runtime model from `specs/002-host-metrics-exporter`. No
database, PVC, cache, or history is added. Each scrape builds a fresh snapshot; Home Assistant keeps
whatever history its recorder policy provides.

## Entity Overview

```text
HostSnapshot
└── batteries[] : BatteryReading
        ├── device: str
        ├── status: str
        ├── level_percent: int | None   # new, optional
        ├── path: str                   # status path, unchanged
        ├── level_path: str | None      # new, optional capacity path
        └── preferred: bool
```

The Mosquitto ACL entry and the Home Assistant discovery sensor are declared configuration, not
runtime data.

## BatteryReading

| Field | Type | Required | Validation |
| ----- | ---- | -------- | ---------- |
| `device` | string | Yes | Directory name under `/host/sys/class/power_supply/`, for example `BAT0`. Unchanged. |
| `status` | string | Yes | Trimmed raw kernel `status` value. A battery is included only when this file is readable. Unchanged. |
| `level_percent` | integer or null | No | `0..100` inclusive when readable; null when `capacity` is missing, unreadable, or non-numeric. |
| `path` | string | Yes | Status source path, for example `/host/sys/class/power_supply/BAT0/status`. Unchanged. |
| `level_path` | string or null | No | Capacity source path, for example `/host/sys/class/power_supply/BAT0/capacity`; null when no level was read or the path is not applicable. |
| `preferred` | boolean | Yes | Exactly one reading is preferred when at least one battery exists; first by device name. Unchanged. |

### Collection rules

1. Enumerate directories under `/host/sys/class/power_supply/` whose `type` contains `battery`
   (case-insensitive), exactly as today.
2. Require a readable, non-empty `status`; otherwise skip the device. This preserves existing
   status behavior.
3. Read `capacity`. Parse the trimmed contents as a base-10 integer.
4. If parsed, constrain the value to `0..100` inclusive.
5. If missing, unreadable, or not an integer, set `level_percent` and `level_path` to null.
6. Sort by device name and mark the first as preferred, exactly as today.

### Value rules

| Source | Result |
| ------ | ------ |
| `capacity` contains `87` | `level_percent = 87` |
| `capacity` contains `0` | `level_percent = 0` (valid, not absent) |
| `capacity` contains `100` | `level_percent = 100` |
| `capacity` contains `123` | `level_percent = 100` (numeric value constrained) |
| `capacity` contains `-5` | `level_percent = 0` (numeric value constrained) |
| `capacity` missing | `level_percent = null` |
| `capacity` unreadable | `level_percent = null` |
| `capacity` contains `unknown` | `level_percent = null` |
| `status` unreadable | Battery omitted entirely (existing behavior) |

## HostSnapshot

`HostSnapshot` is unchanged except that each `BatteryReading` may carry a level. Collection order,
`collected_at`, and the other readings are unchanged.

### Snapshot states

| State | Battery status | Battery level | Battery metric family | `/ha` battery keys | `/readyz` |
| ----- | -------------- | ------------- | --------------------- | ------------------ | --------- |
| Healthy | Present | Present | Status and level series | Preferred + all levels populated | 200 |
| Status only | Present | Absent | Status series only; no level series for that device | Preferred level null; per-battery level null | 200 |
| No battery | Absent | Absent | Both families omitted; `host_metrics_battery_available 0` | All battery keys null/empty | 200 |

`/readyz` continues to depend only on memory and root filesystem. Battery availability never gates
readiness.

## HTTP Projections

### `/metrics` addition

| Metric | Type | Labels | Unit | Presence |
| ------ | ---- | ------ | ---- | -------- |
| `host_battery_level_percent` | gauge | `device`, `path` | percent (0–100) | One series per battery with a readable level; omitted for that device otherwise. |

Example:

```text
# HELP host_battery_level_percent Host battery charge level percentage (0-100).
# TYPE host_battery_level_percent gauge
host_battery_level_percent{device="BAT0",path="/host/sys/class/power_supply/BAT0/capacity"} 87
```

The existing `host_battery_status_info` and `host_metrics_battery_available` families are
unchanged.

### `/ha` and MQTT state additions

The flat JSON gains:

| Key | Type | Presence | Notes |
| --- | ---- | -------- | ----- |
| `battery_level_percent` | integer or null | Always | Preferred battery level. |
| `battery_statuses[].level_percent` | integer or null | Always in each entry | Per-battery level. |

Existing keys keep their names, types, and meaning. Example addition:

```json
{
  "battery_status": "Discharging",
  "battery_level_percent": 87,
  "battery_device": "BAT0",
  "battery_path": "/host/sys/class/power_supply/BAT0/status",
  "battery_statuses": [
    {
      "device": "BAT0",
      "status": "Discharging",
      "level_percent": 87,
      "path": "/host/sys/class/power_supply/BAT0/status",
      "preferred": true
    }
  ]
}
```

## Home Assistant Entity

| Property | Value |
| -------- | ----- |
| Key | `battery_level` |
| Entity ID | `sensor.home_sweet_lab_server_battery_level` |
| Name | Battery level |
| Unique ID | `home_sweet_lab_server_battery_level` |
| Unit | `%` |
| Device class | `battery` |
| State class | `measurement` |
| Icon | `mdi:battery` |
| Value template | `{{ value_json.battery_level_percent }}` |
| State topic | `home-sweet-lab-server/state` |
| Availability | main + `home-sweet-lab-server/availability/battery` |

The existing `sensor.home_sweet_lab_server_battery_status` entity is unchanged.

## Availability and Recovery

- Battery source availability is `online` when at least one battery is included in the snapshot,
  independent of whether any level was readable.
- A missing level does not change battery source availability; the level entity has no valid value
  while status remains usable.
- A missing battery makes both battery entities unavailable.
- Exporter, broker, and Home Assistant restarts recover through the existing discovery/state
  republish path; no new state needs to be retained.
