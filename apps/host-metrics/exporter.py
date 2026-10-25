from __future__ import annotations

import dataclasses
import ipaddress
import json
import logging
import os
import re
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from mqtt_publisher import MqttPublisher, MqttSettings

HOST_PROC = Path(os.environ.get("HOST_PROC", "/host/proc"))
HOST_NET = Path(os.environ.get("HOST_NET", "/host/proc/1/net"))
HOST_SYS = Path(os.environ.get("HOST_SYS", "/host/sys"))
HOST_ROOT = Path(os.environ.get("HOST_ROOT", "/host/root"))
LISTEN_ADDRESS = os.environ.get("LISTEN_ADDRESS", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "9100"))
VERSION = "1"

LOGGER = logging.getLogger("host-metrics")

TAILSCALE_CGNAT = ipaddress.IPv4Network("100.64.0.0/10")
PREFERRED_CHIPS = ("coretemp", "k10temp", "zenpower", "cpu_thermal", "soc_thermal")
PREFERRED_LABELS = ("package", "tctl", "tdie", "cpu", "core")
LOCAL_IPV4_RE = re.compile(r"\|\-\- (\d{1,3}(?:\.\d{1,3}){3})\s*\n\s*/32 host LOCAL")


@dataclass(frozen=True)
class TemperatureReading:
    celsius: float
    source: str
    chip: str
    sensor: str
    path: str
    preferred: bool = False


@dataclass(frozen=True)
class MemoryReading:
    total_bytes: int
    available_bytes: int
    used_bytes: int
    usage_percent: float


@dataclass(frozen=True)
class StorageReading:
    mountpoint: str
    total_bytes: int
    available_bytes: int
    used_bytes: int
    usage_percent: float


@dataclass(frozen=True)
class IPv4Address:
    interface: str
    address: str
    tailscale: bool
    netmask: int | None = None


@dataclass(frozen=True)
class BatteryReading:
    device: str
    status: str
    path: str
    preferred: bool = False


@dataclass(frozen=True)
class HostSnapshot:
    collected_at: str
    temperatures: tuple[TemperatureReading, ...]
    memory: MemoryReading | None
    storage: StorageReading | None
    ipv4_addresses: tuple[IPv4Address, ...]
    batteries: tuple[BatteryReading, ...]

    @property
    def preferred_temperature(self) -> TemperatureReading | None:
        return next((reading for reading in self.temperatures if reading.preferred), None)

    @property
    def preferred_battery(self) -> BatteryReading | None:
        return next((reading for reading in self.batteries if reading.preferred), None)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _read_int(path: Path) -> int | None:
    text = _read_text(path)
    if text is None:
        return None
    try:
        return int(text.strip())
    except ValueError:
        return None


def _percent(used: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(max(0.0, min(100.0, used / total * 100.0)), 1)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_meminfo(text: str) -> MemoryReading | None:
    values: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        fields = rest.split()
        if not fields:
            continue
        try:
            values[key] = int(fields[0])
        except ValueError:
            continue

    total_kb = values.get("MemTotal")
    if total_kb is None or total_kb <= 0:
        return None

    available_kb = values.get("MemAvailable")
    if available_kb is None:
        available_kb = (
            values.get("MemFree", 0)
            + values.get("Buffers", 0)
            + values.get("Cached", 0)
            + values.get("SReclaimable", 0)
            - values.get("Shmem", 0)
        )

    total_bytes = total_kb * 1024
    available_bytes = max(0, min(available_kb * 1024, total_bytes))
    used_bytes = total_bytes - available_bytes
    return MemoryReading(total_bytes, available_bytes, used_bytes, _percent(used_bytes, total_bytes))


def collect_memory(proc_path: Path | str = HOST_PROC) -> MemoryReading | None:
    text = _read_text(Path(proc_path) / "meminfo")
    if text is None:
        return None
    return parse_meminfo(text)


def collect_storage(root_path: Path | str = HOST_ROOT) -> StorageReading | None:
    try:
        stats = os.statvfs(Path(root_path))
    except OSError:
        return None
    total_bytes = stats.f_blocks * stats.f_frsize
    if total_bytes <= 0:
        return None
    available_bytes = max(0, min(stats.f_bavail * stats.f_frsize, total_bytes))
    used_bytes = total_bytes - available_bytes
    return StorageReading("/", total_bytes, available_bytes, used_bytes, _percent(used_bytes, total_bytes))


def _collect_hwmon(sys_path: Path) -> list[TemperatureReading]:
    readings: list[TemperatureReading] = []
    hwmon_root = sys_path / "class" / "hwmon"
    if not hwmon_root.is_dir():
        return readings
    for device in sorted(hwmon_root.iterdir(), key=lambda path: path.name):
        if not device.is_dir():
            continue
        chip = (_read_text(device / "name") or "unknown").strip() or "unknown"
        for input_path in sorted(device.glob("temp*_input"), key=lambda path: path.name):
            raw = _read_int(input_path)
            if raw is None:
                continue
            label_path = input_path.with_name(input_path.name.replace("_input", "_label"))
            label = (_read_text(label_path) or "").strip() or input_path.name
            readings.append(TemperatureReading(raw / 1000.0, "hwmon", chip, label, str(input_path)))
    return readings


def _collect_thermal(sys_path: Path) -> list[TemperatureReading]:
    readings: list[TemperatureReading] = []
    thermal_root = sys_path / "class" / "thermal"
    if not thermal_root.is_dir():
        return readings
    for zone in sorted(thermal_root.glob("thermal_zone*"), key=lambda path: path.name):
        raw = _read_int(zone / "temp")
        if raw is None:
            continue
        sensor = (_read_text(zone / "type") or "").strip() or zone.name
        readings.append(TemperatureReading(raw / 1000.0, "thermal_zone", "thermal", sensor, str(zone / "temp")))
    return readings


def _preferred_temperature_index(readings: list[TemperatureReading]) -> int | None:
    if not readings:
        return None
    hwmon = [index for index, reading in enumerate(readings) if reading.source == "hwmon"]
    pool = hwmon or list(range(len(readings)))
    for chip in PREFERRED_CHIPS:
        for index in pool:
            if readings[index].chip.lower() == chip:
                return index
    for label in PREFERRED_LABELS:
        for index in pool:
            if label in readings[index].sensor.lower():
                return index
    return pool[0]


def collect_temperatures(sys_path: Path | str = HOST_SYS) -> tuple[TemperatureReading, ...]:
    base = Path(sys_path)
    readings = _collect_hwmon(base)
    if not readings:
        readings = _collect_thermal(base)
    readings = sorted(readings, key=lambda reading: (reading.source != "hwmon", reading.path))
    preferred = _preferred_temperature_index(readings)
    if preferred is None:
        return ()
    return tuple(
        dataclasses.replace(reading, preferred=(index == preferred))
        for index, reading in enumerate(readings)
    )


def parse_fib_trie(text: str) -> list[ipaddress.IPv4Address]:
    addresses: set[ipaddress.IPv4Address] = set()
    for match in LOCAL_IPV4_RE.finditer(text):
        try:
            address = ipaddress.IPv4Address(match.group(1))
        except ValueError:
            continue
        if address.is_loopback:
            continue
        addresses.add(address)
    return sorted(addresses)


def _route_hex_to_ipv4(value: str) -> ipaddress.IPv4Address:
    return ipaddress.IPv4Address(struct.pack("<I", int(value, 16)))


def parse_routes(text: str) -> list[tuple[str, ipaddress.IPv4Network]]:
    routes: list[tuple[str, ipaddress.IPv4Network]] = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 8 or fields[0].lower() == "iface":
            continue
        interface, destination_hex, gateway_hex, flags_hex, _, _, _, mask_hex = fields[:8]
        try:
            flags = int(flags_hex, 16)
        except ValueError:
            continue
        if not flags & 0x1 or gateway_hex.lower() != "00000000" or mask_hex.lower() == "00000000":
            continue
        try:
            destination = _route_hex_to_ipv4(destination_hex)
            mask = _route_hex_to_ipv4(mask_hex)
            network = ipaddress.IPv4Network(f"{destination}/{mask}", strict=False)
        except (ValueError, ipaddress.NetmaskValueError):
            continue
        routes.append((interface, network))
    return routes


def _map_ipv4(
    address: ipaddress.IPv4Address,
    routes: list[tuple[str, ipaddress.IPv4Network]],
    tailscale_present: bool,
) -> tuple[str, int | None]:
    matches = [
        (network.prefixlen, interface)
        for interface, network in routes
        if address in network
    ]
    if matches:
        prefix_length, interface = max(matches, key=lambda item: (item[0], item[1]))
        return interface, prefix_length
    if tailscale_present and address in TAILSCALE_CGNAT:
        return "tailscale0", 10
    return "unknown", None


def collect_ipv4(net_path: Path | str = HOST_NET, sys_path: Path | str = HOST_SYS) -> tuple[IPv4Address, ...]:
    net = Path(net_path)
    fib_trie = _read_text(net / "fib_trie")
    if fib_trie is None:
        return ()
    routes = parse_routes(_read_text(net / "route") or "")
    tailscale_present = (Path(sys_path) / "class" / "net" / "tailscale0").exists() or any(
        interface == "tailscale0" for interface, _ in routes
    )
    seen: set[tuple[str, str]] = set()
    readings: list[IPv4Address] = []
    for address in parse_fib_trie(fib_trie):
        interface, netmask = _map_ipv4(address, routes, tailscale_present)
        key = (interface, str(address))
        if key in seen:
            continue
        seen.add(key)
        readings.append(IPv4Address(interface, str(address), interface == "tailscale0", netmask))
    readings.sort(key=lambda reading: (not reading.tailscale, reading.interface, ipaddress.IPv4Address(reading.address)))
    return tuple(readings)


def collect_batteries(sys_path: Path | str = HOST_SYS) -> tuple[BatteryReading, ...]:
    root = Path(sys_path) / "class" / "power_supply"
    if not root.is_dir():
        return ()
    readings: list[BatteryReading] = []
    for device in sorted(root.iterdir(), key=lambda path: path.name):
        if not device.is_dir():
            continue
        device_type = (_read_text(device / "type") or "").strip().lower()
        if device_type != "battery":
            continue
        status = (_read_text(device / "status") or "").strip()
        if not status:
            continue
        readings.append(BatteryReading(device.name, status, str(device / "status")))
    if not readings:
        return ()
    readings.sort(key=lambda reading: reading.device)
    return tuple(
        dataclasses.replace(reading, preferred=(index == 0))
        for index, reading in enumerate(readings)
    )


def collect_snapshot(
    *,
    proc_path: Path | str = HOST_PROC,
    net_path: Path | str = HOST_NET,
    sys_path: Path | str = HOST_SYS,
    root_path: Path | str = HOST_ROOT,
) -> HostSnapshot:
    memory = collect_memory(proc_path)
    storage = collect_storage(root_path)
    temperatures = collect_temperatures(sys_path)
    ipv4_addresses = collect_ipv4(net_path, sys_path)
    batteries = collect_batteries(sys_path)

    if memory is None:
        LOGGER.warning("memory source unavailable at %s", Path(proc_path) / "meminfo")
    if storage is None:
        LOGGER.warning("root filesystem source unavailable at %s", Path(root_path))
    if not temperatures:
        LOGGER.debug("no usable temperature source under %s", Path(sys_path) / "class")
    if not ipv4_addresses:
        LOGGER.debug("no IPv4 addresses read from %s", Path(net_path))
    if not batteries:
        LOGGER.debug("no readable battery under %s", Path(sys_path) / "class" / "power_supply")

    return HostSnapshot(
        _utc_now(),
        temperatures,
        memory,
        storage,
        ipv4_addresses,
        batteries,
    )


def _escape_label(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(pairs: list[tuple[str, object]]) -> str:
    if not pairs:
        return ""
    return "{" + ",".join(f'{name}="{_escape_label(value)}"' for name, value in pairs) + "}"


def _format_value(value: float | int) -> str:
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _sample(name: str, labels: list[tuple[str, object]], value: float | int) -> str:
    return f"{name}{_labels(labels)} {_format_value(value)}"


def _family(
    lines: list[str],
    name: str,
    help_text: str,
    samples: list[str],
    metric_type: str = "gauge",
) -> None:
    if not samples:
        return
    lines.append(f"# HELP {name} {help_text}")
    lines.append(f"# TYPE {name} {metric_type}")
    lines.extend(samples)


def render_metrics(snapshot: HostSnapshot) -> str:
    lines: list[str] = []

    temperature_samples = [
        _sample(
            "host_system_temperature_celsius",
            [("source", reading.source), ("chip", reading.chip), ("sensor", reading.sensor), ("path", reading.path)],
            reading.celsius,
        )
        for reading in snapshot.temperatures
    ]
    _family(
        lines,
        "host_system_temperature_celsius",
        "Host CPU/system temperature in degrees Celsius.",
        temperature_samples,
    )
    _family(
        lines,
        "host_metrics_temperature_available",
        "Whether a usable temperature source was found.",
        [_sample("host_metrics_temperature_available", [], 1 if snapshot.temperatures else 0)],
    )

    if snapshot.memory is not None:
        memory = snapshot.memory
        _family(lines, "host_memory_total_bytes", "Total usable host memory in bytes.", [_sample("host_memory_total_bytes", [], memory.total_bytes)])
        _family(lines, "host_memory_available_bytes", "Host memory available for new allocations in bytes.", [_sample("host_memory_available_bytes", [], memory.available_bytes)])
        _family(lines, "host_memory_used_bytes", "Host memory used in bytes (total minus available).", [_sample("host_memory_used_bytes", [], memory.used_bytes)])
        _family(lines, "host_memory_usage_percent", "Host memory usage percentage (0-100).", [_sample("host_memory_usage_percent", [], memory.usage_percent)])

    if snapshot.storage is not None:
        storage = snapshot.storage
        mount = [("mountpoint", storage.mountpoint)]
        _family(lines, "host_filesystem_size_bytes", "Root filesystem capacity in bytes.", [_sample("host_filesystem_size_bytes", mount, storage.total_bytes)])
        _family(lines, "host_filesystem_available_bytes", "Root filesystem space available in bytes.", [_sample("host_filesystem_available_bytes", mount, storage.available_bytes)])
        _family(lines, "host_filesystem_used_bytes", "Root filesystem space used in bytes (size minus available).", [_sample("host_filesystem_used_bytes", mount, storage.used_bytes)])
        _family(lines, "host_filesystem_usage_percent", "Root filesystem usage percentage (0-100).", [_sample("host_filesystem_usage_percent", mount, storage.usage_percent)])

    address_samples = [
        _sample(
            "host_network_ipv4_info",
            [("interface", address.interface), ("address", address.address), ("tailscale", "true" if address.tailscale else "false")],
            1,
        )
        for address in snapshot.ipv4_addresses
    ]
    _family(lines, "host_network_ipv4_info", "Active non-loopback IPv4 address by interface.", address_samples)

    battery_samples = [
        _sample(
            "host_battery_status_info",
            [("device", battery.device), ("status", battery.status), ("path", battery.path)],
            1,
        )
        for battery in snapshot.batteries
    ]
    _family(lines, "host_battery_status_info", "Host battery charging/discharging status.", battery_samples)
    _family(
        lines,
        "host_metrics_battery_available",
        "Whether a readable host battery status exists.",
        [_sample("host_metrics_battery_available", [], 1 if snapshot.batteries else 0)],
    )

    _family(
        lines,
        "host_metrics_info",
        "Host metrics exporter information.",
        [_sample("host_metrics_info", [("version", VERSION)], 1)],
    )
    return "\n".join(lines) + "\n"


def render_ha(snapshot: HostSnapshot) -> str:
    temperature = snapshot.preferred_temperature
    battery = snapshot.preferred_battery
    memory = snapshot.memory
    storage = snapshot.storage
    tailscale_ipv4 = next(
        (address.address for address in snapshot.ipv4_addresses if address.tailscale),
        None,
    )
    addresses: list[dict[str, object]] = []
    for address in snapshot.ipv4_addresses:
        item: dict[str, object] = {
            "interface": address.interface,
            "address": address.address,
            "tailscale": address.tailscale,
        }
        if address.netmask is not None:
            item["netmask"] = address.netmask
        addresses.append(item)

    payload = {
        "collected_at": snapshot.collected_at,
        "temperature_c": round(temperature.celsius, 1) if temperature is not None else None,
        "temperature_source": f"{temperature.source}/{temperature.chip}/{temperature.sensor}" if temperature is not None else None,
        "temperature_path": temperature.path if temperature is not None else None,
        "memory_total_bytes": memory.total_bytes if memory is not None else None,
        "memory_available_bytes": memory.available_bytes if memory is not None else None,
        "memory_used_bytes": memory.used_bytes if memory is not None else None,
        "memory_usage_percent": memory.usage_percent if memory is not None else None,
        "storage_total_bytes": storage.total_bytes if storage is not None else None,
        "storage_available_bytes": storage.available_bytes if storage is not None else None,
        "storage_used_bytes": storage.used_bytes if storage is not None else None,
        "storage_usage_percent": storage.usage_percent if storage is not None else None,
        "ipv4_addresses": addresses,
        "tailscale_ipv4": tailscale_ipv4,
        "battery_status": battery.status if battery is not None else None,
        "battery_device": battery.device if battery is not None else None,
        "battery_path": battery.path if battery is not None else None,
        "battery_statuses": [
            {
                "device": reading.device,
                "status": reading.status,
                "path": reading.path,
                "preferred": reading.preferred,
            }
            for reading in snapshot.batteries
        ],
    }
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def readiness(snapshot: HostSnapshot) -> tuple[bool, str]:
    missing = []
    if snapshot.memory is None:
        missing.append("memory")
    if snapshot.storage is None:
        missing.append("storage")
    if not missing:
        return True, "ready"
    return False, "not ready: " + "; ".join(f"{name} unavailable" for name in missing)


class MetricsHandler(BaseHTTPRequestHandler):
    server_version = "HostMetrics/1"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        LOGGER.info("%s - %s", self.address_string(), format % args)

    def _send(self, status: HTTPStatus, body: str, content_type: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        if status == HTTPStatus.METHOD_NOT_ALLOWED:
            self.send_header("Allow", "GET")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _method_not_allowed(self) -> None:
        self._send(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed\n", "text/plain; charset=utf-8")

    def do_HEAD(self) -> None:
        self._method_not_allowed()

    def do_POST(self) -> None:
        self._method_not_allowed()

    def do_PUT(self) -> None:
        self._method_not_allowed()

    def do_PATCH(self) -> None:
        self._method_not_allowed()

    def do_DELETE(self) -> None:
        self._method_not_allowed()

    def do_OPTIONS(self) -> None:
        self._method_not_allowed()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/healthz":
            self._send(HTTPStatus.OK, "ok\n", "text/plain; charset=utf-8")
            return
        if path == "/readyz":
            try:
                snapshot = collect_snapshot()
            except Exception:
                LOGGER.exception("readiness collection failed")
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, "collection failed\n", "text/plain; charset=utf-8")
                return
            ready, message = readiness(snapshot)
            status = HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE
            self._send(status, message + "\n", "text/plain; charset=utf-8")
            return
        if path not in ("/metrics", "/ha"):
            self._send(HTTPStatus.NOT_FOUND, "not found\n", "text/plain; charset=utf-8")
            return
        try:
            snapshot = collect_snapshot()
            if path == "/metrics":
                body = render_metrics(snapshot)
                self._send(HTTPStatus.OK, body, "text/plain; version=0.0.4; charset=utf-8")
            else:
                body = render_ha(snapshot)
                self._send(HTTPStatus.OK, body, "application/json; charset=utf-8")
        except Exception:
            LOGGER.exception("collection failed")
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, "collection failed\n", "text/plain; charset=utf-8")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    mqtt_host = os.environ.get("MQTT_HOST", "").strip()
    publisher: MqttPublisher | None = None
    if mqtt_host:
        settings = MqttSettings(
            host=mqtt_host,
            port=_env_int("MQTT_PORT", 1883),
            username=os.environ.get("MQTT_USERNAME") or None,
            password=os.environ.get("MQTT_PASSWORD") or None,
            client_id=os.environ.get("MQTT_CLIENT_ID", "home-sweet-lab-server"),
            publish_interval=max(5, _env_int("MQTT_PUBLISH_INTERVAL", 30)),
        )
        publisher = MqttPublisher(settings, collect_snapshot, render_ha, readiness)
        publisher.start()
    server = ThreadingHTTPServer((LISTEN_ADDRESS, LISTEN_PORT), MetricsHandler)
    server.daemon_threads = True
    LOGGER.info("listening on %s:%s", LISTEN_ADDRESS, LISTEN_PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if publisher is not None:
            publisher.stop()
        server.server_close()


if __name__ == "__main__":
    main()
