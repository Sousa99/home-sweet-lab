# Contract: Home Assistant UI Integration

**Feature**: `specs/002-host-metrics-exporter`
**Audience**: The household operator performing the manual Home Assistant UI steps.
**Constraint**: Use only the Home Assistant UI. Do not edit Home Assistant YAML, do not add HACS
integrations, do not add automations, and do not modify the `home-sweet-home-home-assistant`
repository.

## Prerequisites

- The `host-metrics` exporter pod is Ready in the `monitoring` namespace.
- From the `home-assistant` namespace, this returns HTTP 200 and JSON:

  ```text
  http://host-metrics.monitoring.svc.cluster.local:9100/ha
  ```

- You are signed in to Home Assistant as an administrator.
- You are at `https://home-assistant.<tailnet>.ts.net/`.

If the URL does not return 200 from a pod in the `home-assistant` namespace, stop and follow
`docs/11-host-metrics.md` before adding sensors.

## Integration setup

1. In Home Assistant, open **Settings > Devices & services**.
2. Select **Add Integration**.
3. Search for **Scrape** and select it.
4. Fill the resource form:
   - **Resource URL**: `http://host-metrics.monitoring.svc.cluster.local:9100/ha`
   - **Method**: `GET`
   - **Authentication**: none (leave username and password empty)
   - Leave headers empty.
   - **Verify SSL**: off is irrelevant because the URL is HTTP; leave the default.
   - **Timeout**: `10` seconds is sufficient.
   - **Encoding**: `UTF-8` (default).
5. Submit. Home Assistant validates the resource and then opens the first sensor subentry.
6. For each sensor below, enter the listed fields under the **Additional** section, then submit.
7. To add another sensor later, open the Scrape integration card and choose **Add entry** (the label
   may be **Add sensor** depending on the Home Assistant version) to create another sensor subentry.

The Scrape UI does not expose a scan interval. Home Assistant polls the resource every 10 minutes.
To force an immediate refresh after creating or editing a sensor, open the Scrape integration's
three-dot menu and choose **Reload**. Otherwise wait one poll interval.

## Sensor definitions

The `select` value is always `body`. This is required because the Scrape integration parses the
response through its HTML parser, and the JSON document is exposed as the body text. The
`value_template` then parses it as JSON.

### 1. DietPi CPU temperature

| UI field | Value |
| -------- | ----- |
| Name | `DietPi CPU temperature` |
| Select | `body` |
| Index | `0` |
| Attribute | leave empty |
| Value template | `{{ value_json.temperature_c }}` |
| Availability template | `{{ value_json.temperature_c is not none }}` |
| Device class | `Temperature` |
| State class | `Measurement` |
| Unit of measurement | `°C` |

If the host has no usable temperature sensor, the exporter returns `temperature_c: null`. The
availability template makes this entity **unavailable** instead of showing `0` or `unknown`.

### 2. DietPi RAM usage

| UI field | Value |
| -------- | ----- |
| Name | `DietPi RAM usage` |
| Select | `body` |
| Index | `0` |
| Attribute | leave empty |
| Value template | `{{ value_json.memory_usage_percent }}` |
| Availability template | `{{ value_json.memory_usage_percent is not none }}` |
| Device class | leave empty |
| State class | `Measurement` |
| Unit of measurement | `%` |

The percentage is `(memory_total_bytes - memory_available_bytes) / memory_total_bytes * 100`. If
you prefer a used-bytes sensor, use `{{ value_json.memory_used_bytes }}` with unit `B` and device
class `Data size` instead.

### 3. DietPi storage usage

| UI field | Value |
| -------- | ----- |
| Name | `DietPi storage usage` |
| Select | `body` |
| Index | `0` |
| Attribute | leave empty |
| Value template | `{{ value_json.storage_usage_percent }}` |
| Availability template | `{{ value_json.storage_usage_percent is not none }}` |
| Device class | leave empty |
| State class | `Measurement` |
| Unit of measurement | `%` |

The percentage is `(storage_total_bytes - storage_available_bytes) / storage_total_bytes * 100` for
the filesystem mounted at `/`. If you prefer a used-bytes sensor, use
`{{ value_json.storage_used_bytes }}` with unit `B` and device class `Data size`.

### 4. DietPi battery status

| UI field | Value |
| -------- | ----- |
| Name | `DietPi battery status` |
| Select | `body` |
| Index | `0` |
| Attribute | leave empty |
| Value template | `{{ value_json.battery_status }}` |
| Availability template | `{{ value_json.battery_status is not none }}` |
| Device class | leave empty |
| State class | leave empty |
| Unit of measurement | leave empty |

The state is the raw Linux `power_supply` status, usually `Charging` or `Discharging`, and possibly
`Full`, `Not charging`, or `Unknown`. The exporter does not map those other states to a binary
charging/discharging value. If the host has no battery, the entity is unavailable. If the host has
multiple batteries, this entity shows the preferred battery (the lexicographically first device);
the machine-readable endpoint also carries `battery_statuses` for all batteries.

### 5. DietPi Tailscale IPv4

| UI field | Value |
| -------- | ----- |
| Name | `DietPi Tailscale IPv4` |
| Select | `body` |
| Index | `0` |
| Attribute | leave empty |
| Value template | `{{ value_json.tailscale_ipv4 }}` |
| Availability template | `{{ value_json.tailscale_ipv4 is not none }}` |
| Device class | leave empty |
| State class | leave empty |
| Unit of measurement | leave empty |

This is the stable address to display. If Tailscale is down or the `tailscale0` interface is absent,
the entity becomes unavailable. It recovers at the next successful poll; it does not need to be
recreated.

### 6. DietPi IPv4 addresses (optional)

| UI field | Value |
| -------- | ----- |
| Name | `DietPi IPv4 addresses` |
| Select | `body` |
| Index | `0` |
| Attribute | leave empty |
| Value template | `{{ value_json.ipv4_addresses \| map(attribute='address') \| join(', ') }}` |
| Availability template | `{{ value_json.ipv4_addresses \| length > 0 }}` |
| Device class | leave empty |
| State class | leave empty |
| Unit of measurement | leave empty |

This sensor lists all active non-loopback IPv4 addresses, for example a Tailscale address and a LAN
address. Addresses disappear when their interface goes down and appear when a new one comes up.

## Verification

1. Open **Developer Tools > States**.
2. Filter for `dietpi` or the sensor names you chose.
3. Confirm each sensor has a value and the expected unit.
4. Confirm the temperature sensor is numeric on a host with a usable sensor, or unavailable on a
   host without one.
5. Confirm the RAM and storage percentages are between 0 and 100.
6. Confirm the battery status sensor shows a raw power state such as `Charging`, `Discharging`,
   `Full`, `Not charging`, or `Unknown`, or is unavailable on a host without a battery.
7. Confirm the Tailscale IPv4 sensor contains a dotted-quad address.
8. Wait for one 10-minute poll, or choose **Reload** on the Scrape integration, and confirm the
   values refresh.
9. If the battery state changes (for example, unplug or plug in AC power), confirm the battery
   status sensor reflects the new state at the next poll.
10. Restart the exporter and confirm the sensors become unavailable during the outage and recover
    after the next successful poll, without reconfiguration.

## Troubleshooting

| Symptom | Checks |
| ------- | ------ |
| Integration setup fails with a resource error | Verify the exporter pod is Ready; verify the URL from the `home-assistant` namespace; verify port 9100 and the Service name. |
| All sensors are unavailable | Check whether the exporter is Ready and `/readyz` returns 200. Home Assistant marks the poll failed when the endpoint is unreachable. |
| Temperature sensor is unavailable | The host may have no usable hwmon or thermal-zone sensor, or the sensor file may not be readable by UID 65534. Check `/metrics` for `host_metrics_temperature_available 0`. |
| RAM or storage sensor is unavailable | Check `/metrics` for the memory/filesystem families and `/readyz`. A failed host mount makes the exporter unready. |
| Battery status sensor is unavailable | The host may have no battery, no `power_supply` device with `type: Battery`, or an unreadable status file. Check `/metrics` for `host_metrics_battery_available 0` and the exporter logs. |
| Battery status is not what you expect | The sensor shows the raw kernel state. `Full` and `Not charging` are valid and are not mapped to `Charging` or `Discharging`. Check the host's `/sys/class/power_supply/<device>/status`. |
| Tailscale IPv4 sensor is unavailable | Check `/metrics` for `host_network_ipv4_info` and whether `interface="tailscale0"` is present. The host may be offline from Tailscale. |
| Values do not update within 10 minutes | Use **Reload** on the Scrape integration; check the Home Assistant logs for the Scrape coordinator. |
| Addresses look unexpected | The all-IPv4 sensor includes every active non-loopback interface. Use the Tailscale IPv4 sensor for the stable household address. |
| You need a different polling cadence | The UI does not expose one. The default is 10 minutes; faster polling requires Home Assistant YAML or HACS, which are out of scope. |

## What not to do

- Do not add `scrape:`, `rest:`, `sensor:`, `template:`, or `command_line:` blocks to
  `configuration.yaml`.
- Do not install HACS or a custom Prometheus/OpenMetrics integration.
- Do not add an automation, script, scene, or dashboard YAML file for this feature.
- Do not copy runtime IPv4 addresses into this repository or its documentation.
- Do not create a Home Assistant backup/state bundle just for these sensors; they are UI
  configuration only.

If the UI is later restored from a backup, the Scrape integration and sensors are restored with the
Home Assistant configuration entry and entity registry, not from this repository. If the exporter
URL or metric keys change, update the sensors through the UI and update this contract in the same
change.
