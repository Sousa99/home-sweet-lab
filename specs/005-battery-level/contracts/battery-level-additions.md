# Contract: Battery Level Additions

**Feature**: `specs/005-battery-level`
**Date**: 2026-11-06
**Stability**: Additive to the public contracts in
[`../../002-host-metrics-exporter/contracts/exporter-api.md`](../../002-host-metrics-exporter/contracts/exporter-api.md)
and
[`../../003-host-metrics-mqtt-device/contracts/mqtt-discovery.md`](../../003-host-metrics-mqtt-device/contracts/mqtt-discovery.md).
Existing names, keys, entities, and behavior remain stable.

## Source

Each `BatteryReading` is read from
`/host/sys/class/power_supply/<device>/capacity`. The value is an integer percentage constrained to
`0..100`. Missing, unreadable, or non-numeric contents mean "level unavailable", not zero.

The existing `/host/sys` read-only mount covers this source. No new mount, command execution,
package, or privilege is required.

## `GET /metrics` addition

```text
# HELP host_battery_level_percent Host battery charge level percentage (0-100).
# TYPE host_battery_level_percent gauge
host_battery_level_percent{device="BAT0",path="/host/sys/class/power_supply/BAT0/capacity"} 87
```

| Property | Value |
| -------- | ----- |
| Metric | `host_battery_level_percent` |
| Type | gauge |
| Unit | percent (0–100) |
| Labels | `device`, `path` |
| Presence | One series per battery with a readable level. Omitted for a battery whose level is unavailable. |
| Availability metric | Existing `host_metrics_battery_available` is unchanged and remains based on readable battery status. |

Example with a status-only battery:

```text
# HELP host_battery_status_info Host battery charging/discharging status.
# TYPE host_battery_status_info gauge
host_battery_status_info{device="BAT0",status="Full",path="/host/sys/class/power_supply/BAT0/status"} 1
# HELP host_metrics_battery_available Whether a readable host battery status exists.
# TYPE host_metrics_battery_available gauge
host_metrics_battery_available 1
```

No `host_battery_level_percent` series is emitted in that case.

## `GET /ha` addition

Existing keys are unchanged. The payload adds:

| Key | Type | Presence | Meaning |
| --- | ---- | -------- | ------- |
| `battery_level_percent` | integer or null | Always | Preferred battery level. |
| `battery_statuses[].level_percent` | integer or null | In every entry | Level for that battery. |

Example:

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

Absent battery:

```json
{
  "battery_status": null,
  "battery_level_percent": null,
  "battery_device": null,
  "battery_path": null,
  "battery_statuses": []
}
```

## MQTT state addition

`home-sweet-lab-server/state` uses the same flat JSON as `/ha`, so it gains the same
`battery_level_percent` and per-battery `level_percent` keys. No new state topic is introduced.

## MQTT discovery addition

| Property | Value |
| -------- | ----- |
| Key | `battery_level` |
| Discovery topic | `homeassistant/sensor/home_sweet_lab_server_battery_level/config` |
| Entity ID | `sensor.home_sweet_lab_server_battery_level` |
| Name | Battery level |
| Unit | `%` |
| Device class | `battery` |
| State class | `measurement` |
| Icon | `mdi:battery` |
| Value template | `{{ value_json.battery_level_percent }}` |
| State topic | `home-sweet-lab-server/state` |
| QoS | `1` |
| Availability mode | `all` |
| Availability | main + `home-sweet-lab-server/availability/battery` |

Expected discovery payload:

```json
{
  "name": "Battery level",
  "unique_id": "home_sweet_lab_server_battery_level",
  "default_entity_id": "sensor.home_sweet_lab_server_battery_level",
  "state_topic": "home-sweet-lab-server/state",
  "value_template": "{{ value_json.battery_level_percent }}",
  "unit_of_measurement": "%",
  "device_class": "battery",
  "state_class": "measurement",
  "icon": "mdi:battery",
  "qos": 1,
  "availability_mode": "all",
  "availability": [
    {
      "topic": "home-sweet-lab-server/availability",
      "payload_available": "online",
      "payload_not_available": "offline"
    },
    {
      "topic": "home-sweet-lab-server/availability/battery",
      "payload_available": "online",
      "payload_not_available": "offline"
    }
  ],
  "device": {
    "identifiers": ["home-sweet-lab-server"],
    "name": "home-sweet-lab-server",
    "manufacturer": "Home Sweet Lab",
    "model": "DietPi k3s node",
    "sw_version": "1"
  },
  "origin": {
    "name": "home-sweet-lab-server",
    "sw_version": "1",
    "support_url": "https://github.com/Sousa99/home-sweet-lab"
  }
}
```

The device, origin, and existing six discovery messages are unchanged. After this feature the
device has seven entities.

## Broker ACL addition

Add to the `exporter` user:

```text
topic write homeassistant/sensor/home_sweet_lab_server_battery_level/config
```

Add to the `homeassistant` user:

```text
topic read homeassistant/sensor/home_sweet_lab_server_battery_level/config
```

All other ACL entries remain unchanged.

## Availability behavior

| Condition | Battery status entity | Battery level entity |
| --------- | --------------------- | -------------------- |
| Battery status and level readable | Available with status text | Available with percentage |
| Battery status readable, level unreadable | Available with status text | Unavailable / no valid value |
| No readable battery | Unavailable | Unavailable |
| Exporter, broker, or HA down | Unavailable per existing behavior | Unavailable per existing behavior |
| Memory or storage unreadable | Unavailable (main availability offline) | Unavailable (main availability offline) |

`/readyz` and the main availability topic are not affected by a missing battery level.

## Verification

```bash
python -m unittest discover -s apps/host-metrics -p 'test_*.py'
kubectl kustomize apps/host-metrics
kubeconform -strict -summary apps/host-metrics
```

Cluster checks are in [quickstart.md](../quickstart.md).
