import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import exporter


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_snapshot(**overrides: object) -> exporter.HostSnapshot:
    values = {
        "collected_at": "2026-10-25T12:00:00Z",
        "temperatures": (
            exporter.TemperatureReading(
                45.0,
                "hwmon",
                "coretemp",
                "Package id 0",
                "/host/sys/class/hwmon/hwmon0/temp1_input",
                True,
            ),
        ),
        "memory": exporter.MemoryReading(1000, 400, 600, 60.0),
        "storage": exporter.StorageReading("/", 2000, 1500, 500, 25.0),
        "ipv4_addresses": (
            exporter.IPv4Address("tailscale0", "100.100.100.100", True, 10),
            exporter.IPv4Address("enp1s0", "192.168.1.10", False, 24),
        ),
        "batteries": (
            exporter.BatteryReading(
                "BAT0",
                "Discharging",
                "/host/sys/class/power_supply/BAT0/status",
                True,
            ),
        ),
    }
    values.update(overrides)
    return exporter.HostSnapshot(**values)


class ParserTests(unittest.TestCase):
    def test_parse_meminfo_available(self) -> None:
        reading = exporter.parse_meminfo("MemTotal: 16384000 kB\nMemAvailable: 8192000 kB\n")
        self.assertIsNotNone(reading)
        assert reading is not None
        self.assertEqual(reading.total_bytes, 16777216000)
        self.assertEqual(reading.available_bytes, 8388608000)
        self.assertEqual(reading.used_bytes, 8388608000)
        self.assertEqual(reading.usage_percent, 50.0)

    def test_parse_meminfo_fallback(self) -> None:
        text = (
            "MemTotal: 1000 kB\n"
            "MemFree: 100 kB\n"
            "Buffers: 50 kB\n"
            "Cached: 200 kB\n"
            "SReclaimable: 30 kB\n"
            "Shmem: 10 kB\n"
        )
        reading = exporter.parse_meminfo(text)
        self.assertIsNotNone(reading)
        assert reading is not None
        self.assertEqual(reading.total_bytes, 1024000)
        self.assertEqual(reading.available_bytes, 378880)
        self.assertEqual(reading.used_bytes, 645120)
        self.assertEqual(reading.usage_percent, 63.0)

    def test_parse_meminfo_missing_total(self) -> None:
        self.assertIsNone(exporter.parse_meminfo("MemAvailable: 100 kB\n"))

    def test_collect_storage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            reading = exporter.collect_storage(directory)
            self.assertIsNotNone(reading)
            assert reading is not None
            self.assertEqual(reading.mountpoint, "/")
            self.assertGreater(reading.total_bytes, 0)
            self.assertGreaterEqual(reading.available_bytes, 0)
            self.assertGreaterEqual(reading.used_bytes, 0)
            self.assertGreaterEqual(reading.usage_percent, 0.0)
            self.assertLessEqual(reading.usage_percent, 100.0)

    def test_temperature_hwmon_preferred(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sys_path = Path(directory)
            hwmon = sys_path / "class" / "hwmon" / "hwmon0"
            write(hwmon / "name", "coretemp\n")
            write(hwmon / "temp1_input", "45000\n")
            write(hwmon / "temp1_label", "Package id 0\n")
            write(hwmon / "temp2_input", "40000\n")

            readings = exporter.collect_temperatures(sys_path)
            self.assertEqual(len(readings), 2)
            self.assertEqual(sum(1 for reading in readings if reading.preferred), 1)
            preferred = next(reading for reading in readings if reading.preferred)
            self.assertEqual(preferred.sensor, "Package id 0")
            self.assertEqual(preferred.celsius, 45.0)
            self.assertEqual(preferred.chip, "coretemp")
            self.assertEqual(preferred.source, "hwmon")

    def test_temperature_thermal_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sys_path = Path(directory)
            zone = sys_path / "class" / "thermal" / "thermal_zone0"
            write(zone / "type", "x86_pkg_temp\n")
            write(zone / "temp", "50000\n")

            readings = exporter.collect_temperatures(sys_path)
            self.assertEqual(len(readings), 1)
            self.assertEqual(readings[0].source, "thermal_zone")
            self.assertEqual(readings[0].chip, "thermal")
            self.assertEqual(readings[0].sensor, "x86_pkg_temp")
            self.assertEqual(readings[0].celsius, 50.0)
            self.assertTrue(readings[0].preferred)

    def test_temperature_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(exporter.collect_temperatures(directory), ())

    def test_ipv4_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            net_path = Path(directory) / "net"
            sys_path = Path(directory) / "sys"
            write(
                net_path / "fib_trie",
                "Local:\n"
                "  |-- 192.168.1.10\n"
                "     /32 host LOCAL\n"
                "  |-- 100.100.100.100\n"
                "     /32 host LOCAL\n"
                "  |-- 127.0.0.1\n"
                "     /32 host LOCAL\n",
            )
            write(
                net_path / "route",
                "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\tMTU\tWindow\tIRTT\n"
                "enp1s0\t0001A8C0\t00000000\t0001\t0\t0\t0\t00FFFFFF\t0\t0\t0\n"
                "tailscale0\t00004064\t00000000\t0001\t0\t0\t0\t0000C0FF\t0\t0\t0\n",
            )
            (sys_path / "class" / "net" / "tailscale0").mkdir(parents=True)

            readings = exporter.collect_ipv4(net_path, sys_path)
            self.assertEqual(len(readings), 2)
            self.assertTrue(readings[0].tailscale)
            self.assertEqual(readings[0].interface, "tailscale0")
            self.assertEqual(readings[0].address, "100.100.100.100")
            self.assertEqual(readings[0].netmask, 10)
            self.assertEqual(readings[1].interface, "enp1s0")
            self.assertEqual(readings[1].address, "192.168.1.10")
            self.assertEqual(readings[1].netmask, 24)
            self.assertFalse(any(reading.address == "127.0.0.1" for reading in readings))

    def test_ipv4_unknown_interface(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            net_path = Path(directory) / "net"
            sys_path = Path(directory) / "sys"
            write(
                net_path / "fib_trie",
                "Local:\n"
                "  |-- 100.100.100.100\n"
                "     /32 host LOCAL\n",
            )
            write(net_path / "route", "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\tMTU\tWindow\tIRTT\n")

            readings = exporter.collect_ipv4(net_path, sys_path)
            self.assertEqual(len(readings), 1)
            self.assertEqual(readings[0].interface, "unknown")
            self.assertFalse(readings[0].tailscale)

    def test_batteries_sorted_and_preferred(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sys_path = Path(directory)
            root = sys_path / "class" / "power_supply"
            write(root / "BAT1" / "type", "Battery\n")
            write(root / "BAT1" / "status", "Discharging\n")
            write(root / "BAT0" / "type", "Battery\n")
            write(root / "BAT0" / "status", "Charging\n")
            write(root / "AC" / "type", "Mains\n")
            write(root / "AC" / "status", "Unknown\n")
            write(root / "BAT2" / "type", "Battery\n")

            readings = exporter.collect_batteries(sys_path)
            self.assertEqual([reading.device for reading in readings], ["BAT0", "BAT1"])
            self.assertEqual(readings[0].status, "Charging")
            self.assertTrue(readings[0].preferred)
            self.assertEqual(readings[1].status, "Discharging")
            self.assertFalse(readings[1].preferred)

    def test_battery_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(exporter.collect_batteries(directory), ())

    def test_battery_status_unreadable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sys_path = Path(directory)
            status_path = sys_path / "class" / "power_supply" / "BAT0" / "status"
            write(sys_path / "class" / "power_supply" / "BAT0" / "type", "Battery\n")
            write(status_path, "Charging\n")
            os.chmod(status_path, 0)
            self.assertEqual(exporter.collect_batteries(sys_path), ())

    def test_snapshot_missing_memory_and_storage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            proc_path = base / "proc"
            net_path = base / "net"
            sys_path = base / "sys"
            root_path = base / "root"
            root_path.mkdir()
            with self.assertLogs(exporter.LOGGER, level="WARNING"):
                snapshot = exporter.collect_snapshot(
                    proc_path=proc_path,
                    net_path=net_path,
                    sys_path=sys_path,
                    root_path=root_path,
                )
            self.assertIsNone(snapshot.memory)
            self.assertIsNotNone(snapshot.storage)
            self.assertEqual(snapshot.temperatures, ())
            self.assertEqual(snapshot.batteries, ())
            self.assertEqual(
                exporter.readiness(snapshot),
                (False, "not ready: memory unavailable"),
            )
            with self.assertLogs(exporter.LOGGER, level="WARNING"):
                missing_storage = exporter.collect_snapshot(
                    proc_path=proc_path,
                    net_path=net_path,
                    sys_path=sys_path,
                    root_path=base / "missing-root",
                )
            self.assertEqual(
                exporter.readiness(missing_storage),
                (False, "not ready: memory unavailable; storage unavailable"),
            )


class RenderTests(unittest.TestCase):
    def test_metrics_contract(self) -> None:
        metrics = exporter.render_metrics(make_snapshot())
        self.assertIn(
            'host_system_temperature_celsius{source="hwmon",chip="coretemp",sensor="Package id 0",path="/host/sys/class/hwmon/hwmon0/temp1_input"} 45.0',
            metrics,
        )
        self.assertIn("host_metrics_temperature_available 1", metrics)
        self.assertIn("host_memory_total_bytes 1000", metrics)
        self.assertIn("host_memory_available_bytes 400", metrics)
        self.assertIn("host_memory_used_bytes 600", metrics)
        self.assertIn("host_memory_usage_percent 60.0", metrics)
        self.assertIn('host_filesystem_size_bytes{mountpoint="/"} 2000', metrics)
        self.assertIn('host_filesystem_available_bytes{mountpoint="/"} 1500', metrics)
        self.assertIn('host_filesystem_used_bytes{mountpoint="/"} 500', metrics)
        self.assertIn('host_filesystem_usage_percent{mountpoint="/"} 25.0', metrics)
        self.assertIn(
            'host_network_ipv4_info{interface="tailscale0",address="100.100.100.100",tailscale="true"} 1',
            metrics,
        )
        self.assertIn(
            'host_network_ipv4_info{interface="enp1s0",address="192.168.1.10",tailscale="false"} 1',
            metrics,
        )
        self.assertIn(
            'host_battery_status_info{device="BAT0",status="Discharging",path="/host/sys/class/power_supply/BAT0/status"} 1',
            metrics,
        )
        self.assertIn("host_metrics_battery_available 1", metrics)
        self.assertIn('host_metrics_info{version="1"} 1', metrics)

    def test_metrics_absent_optional_sources(self) -> None:
        snapshot = make_snapshot(
            temperatures=(),
            memory=None,
            storage=None,
            ipv4_addresses=(),
            batteries=(),
        )
        metrics = exporter.render_metrics(snapshot)
        self.assertIn("host_metrics_temperature_available 0", metrics)
        self.assertIn("host_metrics_battery_available 0", metrics)
        self.assertIn("host_metrics_info", metrics)
        for name in (
            "host_system_temperature_celsius",
            "host_memory_total_bytes",
            "host_filesystem_size_bytes",
            "host_network_ipv4_info",
            "host_battery_status_info",
        ):
            self.assertNotIn(f"# TYPE {name}", metrics)

    def test_ha_contract(self) -> None:
        payload = json.loads(exporter.render_ha(make_snapshot()))
        self.assertEqual(payload["collected_at"], "2026-10-25T12:00:00Z")
        self.assertEqual(payload["temperature_c"], 45.0)
        self.assertEqual(payload["temperature_source"], "hwmon/coretemp/Package id 0")
        self.assertEqual(payload["temperature_path"], "/host/sys/class/hwmon/hwmon0/temp1_input")
        self.assertEqual(payload["memory_total_bytes"], 1000)
        self.assertEqual(payload["memory_available_bytes"], 400)
        self.assertEqual(payload["memory_used_bytes"], 600)
        self.assertEqual(payload["memory_usage_percent"], 60.0)
        self.assertEqual(payload["storage_total_bytes"], 2000)
        self.assertEqual(payload["storage_available_bytes"], 1500)
        self.assertEqual(payload["storage_used_bytes"], 500)
        self.assertEqual(payload["storage_usage_percent"], 25.0)
        self.assertEqual(payload["tailscale_ipv4"], "100.100.100.100")
        self.assertEqual(
            payload["ipv4_addresses"],
            [
                {"interface": "tailscale0", "address": "100.100.100.100", "tailscale": True, "netmask": 10},
                {"interface": "enp1s0", "address": "192.168.1.10", "tailscale": False, "netmask": 24},
            ],
        )
        self.assertEqual(payload["battery_status"], "Discharging")
        self.assertEqual(payload["battery_device"], "BAT0")
        self.assertEqual(payload["battery_path"], "/host/sys/class/power_supply/BAT0/status")
        self.assertEqual(
            payload["battery_statuses"],
            [
                {
                    "device": "BAT0",
                    "status": "Discharging",
                    "path": "/host/sys/class/power_supply/BAT0/status",
                    "preferred": True,
                }
            ],
        )

    def test_ha_absent_optional_sources(self) -> None:
        payload = json.loads(
            exporter.render_ha(
                make_snapshot(
                    temperatures=(),
                    memory=None,
                    storage=None,
                    ipv4_addresses=(),
                    batteries=(),
                )
            )
        )
        self.assertIsNone(payload["temperature_c"])
        self.assertIsNone(payload["temperature_source"])
        self.assertIsNone(payload["temperature_path"])
        self.assertIsNone(payload["memory_total_bytes"])
        self.assertIsNone(payload["storage_total_bytes"])
        self.assertIsNone(payload["tailscale_ipv4"])
        self.assertEqual(payload["ipv4_addresses"], [])
        self.assertIsNone(payload["battery_status"])
        self.assertIsNone(payload["battery_device"])
        self.assertIsNone(payload["battery_path"])
        self.assertEqual(payload["battery_statuses"], [])

    def test_readiness(self) -> None:
        self.assertEqual(exporter.readiness(make_snapshot()), (True, "ready"))
        self.assertEqual(
            exporter.readiness(make_snapshot(memory=None)),
            (False, "not ready: memory unavailable"),
        )
        self.assertEqual(
            exporter.readiness(make_snapshot(storage=None)),
            (False, "not ready: storage unavailable"),
        )
        self.assertEqual(
            exporter.readiness(make_snapshot(memory=None, storage=None)),
            (False, "not ready: memory unavailable; storage unavailable"),
        )


class HttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = exporter.ThreadingHTTPServer(("127.0.0.1", 0), exporter.MetricsHandler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_health_and_contract_endpoints(self) -> None:
        with mock.patch.object(exporter, "collect_snapshot", return_value=make_snapshot()):
            with urllib.request.urlopen(self.base + "/healthz", timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read().decode(), "ok\n")
            with urllib.request.urlopen(self.base + "/metrics", timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertIn("host_metrics_info", response.read().decode())
            with urllib.request.urlopen(self.base + "/ha", timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertIn("battery_status", json.loads(response.read().decode()))
            with urllib.request.urlopen(self.base + "/readyz", timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read().decode(), "ready\n")

    def test_unready_and_unknown_path(self) -> None:
        with mock.patch.object(
            exporter,
            "collect_snapshot",
            return_value=make_snapshot(memory=None),
        ):
            with self.assertRaises(urllib.error.HTTPError) as context:
                urllib.request.urlopen(self.base + "/readyz", timeout=5)
            self.assertEqual(context.exception.code, 503)
            context.exception.close()
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(self.base + "/missing", timeout=5)
        self.assertEqual(context.exception.code, 404)
        context.exception.close()

    def test_post_is_not_allowed(self) -> None:
        request = urllib.request.Request(self.base + "/metrics", data=b"", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(context.exception.code, 405)
        self.assertEqual(context.exception.headers.get("Allow"), "GET")
        context.exception.close()


if __name__ == "__main__":
    unittest.main()
