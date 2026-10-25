from __future__ import annotations

import json

DEVICE_ID = "home-sweet-lab-server"
DEVICE_NAME = "home-sweet-lab-server"
DISCOVERY_PREFIX = "homeassistant"
STATE_TOPIC = "home-sweet-lab-server/state"
AVAILABILITY_TOPIC = "home-sweet-lab-server/availability"
SOURCE_AVAILABILITY = {
    "temperature": "home-sweet-lab-server/availability/temperature",
    "battery": "home-sweet-lab-server/availability/battery",
    "ipv4": "home-sweet-lab-server/availability/ipv4",
}
VERSION = "1"
SUPPORT_URL = "https://github.com/Sousa99/home-sweet-lab"

SENSORS = (
    {
        "key": "cpu_temperature",
        "name": "CPU temperature",
        "unit": "°C",
        "device_class": "temperature",
        "state_class": "measurement",
        "icon": "mdi:thermometer",
        "value_template": "{{ value_json.temperature_c }}",
        "availability_keys": ("temperature",),
    },
    {
        "key": "ram_usage",
        "name": "RAM usage",
        "unit": "%",
        "state_class": "measurement",
        "icon": "mdi:memory",
        "value_template": "{{ value_json.memory_usage_percent }}",
        "availability_keys": (),
    },
    {
        "key": "storage_usage",
        "name": "Storage usage",
        "unit": "%",
        "state_class": "measurement",
        "icon": "mdi:harddisk",
        "value_template": "{{ value_json.storage_usage_percent }}",
        "availability_keys": (),
    },
    {
        "key": "battery_status",
        "name": "Battery status",
        "icon": "mdi:battery",
        "value_template": "{{ value_json.battery_status }}",
        "availability_keys": ("battery",),
    },
    {
        "key": "tailscale_ipv4",
        "name": "Tailscale IPv4",
        "icon": "mdi:ip-network",
        "value_template": "{{ value_json.tailscale_ipv4 }}",
        "availability_keys": ("ipv4",),
    },
    {
        "key": "ipv4_addresses",
        "name": "IPv4 addresses",
        "icon": "mdi:ip-network-outline",
        "value_template": "{{ value_json.ipv4_addresses | map(attribute='address') | join(', ') }}",
        "availability_keys": ("ipv4",),
    },
)


def device_info() -> dict[str, object]:
    return {
        "identifiers": [DEVICE_ID],
        "name": DEVICE_NAME,
        "manufacturer": "Home Sweet Lab",
        "model": "DietPi k3s node",
        "sw_version": VERSION,
    }


def origin_info() -> dict[str, object]:
    return {
        "name": DEVICE_NAME,
        "sw_version": VERSION,
        "support_url": SUPPORT_URL,
    }


def entity_id(key: str) -> str:
    return f"sensor.home_sweet_lab_server_{key}"


def unique_id(key: str) -> str:
    return f"home_sweet_lab_server_{key}"


def discovery_topic(key: str) -> str:
    return f"{DISCOVERY_PREFIX}/sensor/home_sweet_lab_server_{key}/config"


def availability_item(topic: str) -> dict[str, str]:
    return {
        "topic": topic,
        "payload_available": "online",
        "payload_not_available": "offline",
    }


def availability_topics(sensor: dict[str, object]) -> list[dict[str, str]]:
    topics = [availability_item(AVAILABILITY_TOPIC)]
    for key in sensor["availability_keys"]:
        topics.append(availability_item(SOURCE_AVAILABILITY[key]))
    return topics


def discovery_payload(sensor: dict[str, object]) -> dict[str, object]:
    key = str(sensor["key"])
    payload: dict[str, object] = {
        "name": sensor["name"],
        "unique_id": unique_id(key),
        "default_entity_id": entity_id(key),
        "state_topic": STATE_TOPIC,
        "value_template": sensor["value_template"],
        "qos": 1,
        "availability_mode": "all",
        "availability": availability_topics(sensor),
        "device": device_info(),
        "origin": origin_info(),
    }
    for field in ("unit_of_measurement", "device_class", "state_class", "icon"):
        source_field = {
            "unit_of_measurement": "unit",
            "device_class": "device_class",
            "state_class": "state_class",
            "icon": "icon",
        }[field]
        if source_field in sensor:
            payload[field] = sensor[source_field]
    return payload


def discovery_messages() -> list[tuple[str, str]]:
    messages: list[tuple[str, str]] = []
    for sensor in SENSORS:
        key = str(sensor["key"])
        payload = json.dumps(discovery_payload(sensor), separators=(",", ":"), ensure_ascii=False)
        messages.append((discovery_topic(key), payload))
    return messages


def availability_messages(
    *,
    ready: bool,
    temperature_available: bool,
    battery_available: bool,
    ipv4_available: bool,
) -> list[tuple[str, str]]:
    main = "online" if ready else "offline"
    messages = [(AVAILABILITY_TOPIC, main)]
    messages.append(
        (
            SOURCE_AVAILABILITY["temperature"],
            "online" if ready and temperature_available else "offline",
        )
    )
    messages.append(
        (
            SOURCE_AVAILABILITY["battery"],
            "online" if ready and battery_available else "offline",
        )
    )
    messages.append(
        (
            SOURCE_AVAILABILITY["ipv4"],
            "online" if ready and ipv4_available else "offline",
        )
    )
    return messages
