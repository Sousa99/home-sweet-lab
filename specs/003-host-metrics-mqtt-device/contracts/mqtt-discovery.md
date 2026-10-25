# Contract: MQTT Discovery for Home Metrics

**Feature**: `specs/003-host-metrics-mqtt-device`
**Home Assistant**: 2026.10.4
**Stability**: Device name, entity IDs, topics, and discovery payload keys are the public contract.

## Broker

```text
mosquitto.monitoring.svc.cluster.local:1883
```

- ClusterIP only
- Plain MQTT inside the cluster
- Users: `exporter`, `homeassistant`
- Discovery prefix: `homeassistant`

## Home Assistant device

Every discovery payload uses the same device block:

```json
{
  "device": {
    "identifiers": ["home-sweet-lab-server"],
    "name": "home-sweet-lab-server",
    "manufacturer": "Home Sweet Lab",
    "model": "DietPi k3s node",
    "sw_version": "1"
  }
}
```

- `home-sweet-lab-server` is the Home Assistant device identity.
- DietPi remains the OS; `dietpi` remains the hostname and Linux user.
- The Kubernetes node remains `dietpi`.

## Topics

| Topic | Direction | Retained | Purpose |
| ----- | --------- | -------- | ------- |
| `homeassistant/status` | HA → broker | yes | HA birth/online message |
| `homeassistant/sensor/home_sweet_lab_server_<key>/config` | exporter → broker | yes | discovery |
| `home-sweet-lab-server/state` | exporter → broker | yes | flat JSON state |
| `home-sweet-lab-server/availability` | exporter → broker | yes | main availability / LWT |
| `home-sweet-lab-server/availability/temperature` | exporter → broker | yes | temperature source availability |
| `home-sweet-lab-server/availability/battery` | exporter → broker | yes | battery source availability |
| `home-sweet-lab-server/availability/ipv4` | exporter → broker | yes | IPv4 source availability |

The exporter publishes state every 30 seconds by default and on every connect/HA birth.

## Entities

| Key | Discovery topic | Entity ID | Name | Unit | Device class | State class | Value template | Availability |
| --- | --------------- | --------- | ---- | ---- | ------------ | ----------- | -------------- | ------------ |
| `cpu_temperature` | `homeassistant/sensor/home_sweet_lab_server_cpu_temperature/config` | `sensor.home_sweet_lab_server_cpu_temperature` | CPU temperature | °C | temperature | measurement | `{{ value_json.temperature_c }}` | main + temperature |
| `ram_usage` | `homeassistant/sensor/home_sweet_lab_server_ram_usage/config` | `sensor.home_sweet_lab_server_ram_usage` | RAM usage | % | none | measurement | `{{ value_json.memory_usage_percent }}` | main |
| `storage_usage` | `homeassistant/sensor/home_sweet_lab_server_storage_usage/config` | `sensor.home_sweet_lab_server_storage_usage` | Storage usage | % | none | measurement | `{{ value_json.storage_usage_percent }}` | main |
| `battery_status` | `homeassistant/sensor/home_sweet_lab_server_battery_status/config` | `sensor.home_sweet_lab_server_battery_status` | Battery status | none | none | none | `{{ value_json.battery_status }}` | main + battery |
| `tailscale_ipv4` | `homeassistant/sensor/home_sweet_lab_server_tailscale_ipv4/config` | `sensor.home_sweet_lab_server_tailscale_ipv4` | Tailscale IPv4 | none | none | none | `{{ value_json.tailscale_ipv4 }}` | main + ipv4 |
| `ipv4_addresses` | `homeassistant/sensor/home_sweet_lab_server_ipv4_addresses/config` | `sensor.home_sweet_lab_server_ipv4_addresses` | IPv4 addresses | none | none | none | `{{ value_json.ipv4_addresses \| map(attribute='address') \| join(', ') }}` | main + ipv4 |

Icons:

- temperature: `mdi:thermometer`
- RAM: `mdi:memory`
- storage: `mdi:harddisk`
- battery: `mdi:battery`
- Tailscale IPv4: `mdi:ip-network`
- all IPv4: `mdi:ip-network-outline`

Each entity also carries:

- `unique_id`: `home_sweet_lab_server_<key>`
- `default_entity_id`: `sensor.home_sweet_lab_server_<key>`
- `state_topic`: `home-sweet-lab-server/state`
- `qos`: `1`
- `availability_mode`: `all`
- `device`: the shared device block above
- `origin`: `{ "name": "home-sweet-lab-server", "sw_version": "1", "support_url": "https://github.com/Sousa99/home-sweet-lab" }`

### Temperature discovery example

```json
{
  "name": "CPU temperature",
  "unique_id": "home_sweet_lab_server_cpu_temperature",
  "default_entity_id": "sensor.home_sweet_lab_server_cpu_temperature",
  "state_topic": "home-sweet-lab-server/state",
  "value_template": "{{ value_json.temperature_c }}",
  "unit_of_measurement": "°C",
  "device_class": "temperature",
  "state_class": "measurement",
  "icon": "mdi:thermometer",
  "qos": 1,
  "availability_mode": "all",
  "availability": [
    {
      "topic": "home-sweet-lab-server/availability",
      "payload_available": "online",
      "payload_not_available": "offline"
    },
    {
      "topic": "home-sweet-lab-server/availability/temperature",
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

## State payload

The state payload is the same flat JSON as `/ha`:

```json
{
  "collected_at": "2026-10-25T21:00:00Z",
  "temperature_c": 50.0,
  "temperature_source": "hwmon/coretemp/Package id 0",
  "temperature_path": "/host/sys/class/hwmon/hwmon7/temp1_input",
  "memory_total_bytes": 16457240576,
  "memory_available_bytes": 13500000000,
  "memory_used_bytes": 2957240576,
  "memory_usage_percent": 18.0,
  "storage_total_bytes": 1007611232256,
  "storage_available_bytes": 947000000000,
  "storage_used_bytes": 60611232256,
  "storage_usage_percent": 6.0,
  "ipv4_addresses": [
    {"interface": "tailscale0", "address": "<tailscale-ipv4>", "tailscale": true, "netmask": 10}
  ],
  "tailscale_ipv4": "<tailscale-ipv4>",
  "battery_status": "Full",
  "battery_device": "BAT0",
  "battery_path": "/host/sys/class/power_supply/BAT0/status",
  "battery_statuses": [
    {"device": "BAT0", "status": "Full", "path": "/host/sys/class/power_supply/BAT0/status", "preferred": true}
  ]
}
```

Absent temperature, battery, or IPv4 values are `null` or empty arrays, and the corresponding
availability topic is `offline`.

## Availability behavior

- Main availability is `online` only when memory and root filesystem collection succeed.
- Temperature availability is `online` only when at least one usable temperature reading exists.
- Battery availability is `online` only when at least one readable battery exists.
- IPv4 availability is `online` only when at least one address is present.
- The exporter sets MQTT Last Will to `offline` on the main availability topic.
- On connect and on `homeassistant/status=online`, the exporter publishes discovery, all
  availability topics, and state.
- On each 30-second cycle, the exporter publishes availability and state.

## Authentication and ACLs

Manual Secret `mosquitto-auth` in `monitoring`:

| Key | Purpose |
| --- | ------- |
| `passwd` | Mosquitto password file with `exporter` and `homeassistant` |
| `exporter-username` | exporter MQTT username |
| `exporter-password` | exporter MQTT password |
| `homeassistant-username` | HA MQTT username |
| `homeassistant-password` | HA MQTT password |

ACL:

```text
user exporter
topic write homeassistant/sensor/home_sweet_lab_server_cpu_temperature/config
topic write homeassistant/sensor/home_sweet_lab_server_ram_usage/config
topic write homeassistant/sensor/home_sweet_lab_server_storage_usage/config
topic write homeassistant/sensor/home_sweet_lab_server_battery_status/config
topic write homeassistant/sensor/home_sweet_lab_server_tailscale_ipv4/config
topic write homeassistant/sensor/home_sweet_lab_server_ipv4_addresses/config
topic write home-sweet-lab-server/state
topic write home-sweet-lab-server/availability
topic write home-sweet-lab-server/availability/+
topic read homeassistant/status

user homeassistant
topic read homeassistant/sensor/home_sweet_lab_server_cpu_temperature/config
topic read homeassistant/sensor/home_sweet_lab_server_ram_usage/config
topic read homeassistant/sensor/home_sweet_lab_server_storage_usage/config
topic read homeassistant/sensor/home_sweet_lab_server_battery_status/config
topic read homeassistant/sensor/home_sweet_lab_server_tailscale_ipv4/config
topic read homeassistant/sensor/home_sweet_lab_server_ipv4_addresses/config
topic read home-sweet-lab-server/state
topic read home-sweet-lab-server/availability
topic read home-sweet-lab-server/availability/+
topic read homeassistant/status
topic write homeassistant/status

```

## Home Assistant UI

1. **Settings > Devices & services > Add Integration**
2. Search **MQTT**
3. Choose **Manually enter the MQTT broker connection details**
4. Broker: `mosquitto.monitoring.svc.cluster.local`
5. Port: `1883`
6. Username: `homeassistant`
7. Password: from the `mosquitto-auth` Secret
8. Leave TLS and protocol defaults
9. Submit

Expected: one device `home-sweet-lab-server` with the six entities above. No Scrape integration is
needed. Remove Scrape after MQTT is verified if it exists.

## Legacy Scrape

The HTTP `/ha` endpoint and the 10-minute Scrape UI flow remain documented as legacy in
`docs/11-host-metrics.md`. They are no longer the primary Home Assistant data path. MQTT updates
every 30 seconds and provides one device.

## Failure behavior

| Condition | Behavior |
| --------- | -------- |
| Broker down | Exporter retries; HA entities unavailable; state is republished on reconnect. |
| Wrong Secret/password | Broker rejects the client; exporter logs auth failure; HA MQTT integration shows an error. |
| ACL denies a topic | Publish/subscribe fails; verify the ACL file and broker logs. |
| Broker restart | Retained messages are lost; exporter reconnects and republishes discovery/state/availability. |
| HA restart | HA publishes `homeassistant/status=online`; exporter republishes discovery/state/availability. |
| Exporter restart | LWT marks entities offline; replacement publishes online and state. |
| Temperature/battery/IPv4 absent | Only the affected per-source availability topic is offline. |
| Memory/storage unreadable | Main availability offline; all entities unavailable until `/readyz` recovers. |
| Scrape sensors still exist | Remove Scrape after MQTT verification; delete orphaned entities if needed. |
| Image unavailable | Deployment stays in image pull failure until the GHCR package is public/pullable. |
