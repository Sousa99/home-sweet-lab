import json
import unittest
from types import SimpleNamespace

import mqtt_discovery as discovery
import mqtt_publisher

HAS_PAHO = mqtt_publisher.mqtt is not None


class DiscoveryTests(unittest.TestCase):
    def test_device_identity(self) -> None:
        device = discovery.device_info()
        self.assertEqual(device["identifiers"], ["home-sweet-lab-server"])
        self.assertEqual(device["name"], "home-sweet-lab-server")
        self.assertEqual(device["manufacturer"], "Home Sweet Lab")

    def test_discovery_messages_share_one_device(self) -> None:
        messages = discovery.discovery_messages()
        self.assertEqual(len(messages), 6)
        topics = {topic for topic, _ in messages}
        self.assertIn(
            "homeassistant/sensor/home_sweet_lab_server_cpu_temperature/config",
            topics,
        )
        for _, payload in messages:
            data = json.loads(payload)
            self.assertEqual(data["device"]["identifiers"], ["home-sweet-lab-server"])
            self.assertEqual(data["qos"], 1)
            self.assertEqual(data["availability_mode"], "all")
            self.assertEqual(data["state_topic"], "home-sweet-lab-server/state")

    def test_temperature_discovery(self) -> None:
        payload = discovery.discovery_payload(
            next(sensor for sensor in discovery.SENSORS if sensor["key"] == "cpu_temperature")
        )
        self.assertEqual(payload["default_entity_id"], "sensor.home_sweet_lab_server_cpu_temperature")
        self.assertEqual(payload["unique_id"], "home_sweet_lab_server_cpu_temperature")
        self.assertEqual(payload["unit_of_measurement"], "°C")
        self.assertEqual(payload["device_class"], "temperature")
        self.assertEqual(payload["state_class"], "measurement")
        self.assertEqual(
            payload["availability"],
            [
                {
                    "topic": "home-sweet-lab-server/availability",
                    "payload_available": "online",
                    "payload_not_available": "offline",
                },
                {
                    "topic": "home-sweet-lab-server/availability/temperature",
                    "payload_available": "online",
                    "payload_not_available": "offline",
                },
            ],
        )

    def test_availability_messages(self) -> None:
        messages = dict(
            discovery.availability_messages(
                ready=True,
                temperature_available=True,
                battery_available=False,
                ipv4_available=True,
            )
        )
        self.assertEqual(messages["home-sweet-lab-server/availability"], "online")
        self.assertEqual(messages["home-sweet-lab-server/availability/temperature"], "online")
        self.assertEqual(messages["home-sweet-lab-server/availability/battery"], "offline")
        self.assertEqual(messages["home-sweet-lab-server/availability/ipv4"], "online")

    def test_availability_when_unready(self) -> None:
        messages = dict(
            discovery.availability_messages(
                ready=False,
                temperature_available=True,
                battery_available=True,
                ipv4_available=True,
            )
        )
        self.assertTrue(all(value == "offline" for value in messages.values()))


class FakeMessageInfo:
    rc = 0


class FakeClient:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, int, bool]] = []
        self.subscriptions: list[tuple[str, int]] = []
        self.connected = True

    def publish(self, topic: str, payload: str, qos: int = 0, retain: bool = False) -> FakeMessageInfo:
        self.messages.append((topic, payload, qos, retain))
        return FakeMessageInfo()

    def subscribe(self, topic: str, qos: int = 0) -> None:
        self.subscriptions.append((topic, qos))

    def is_connected(self) -> bool:
        return self.connected


def snapshot(temperatures: tuple = (1,), batteries: tuple = (1,), ipv4: tuple = (1,)) -> SimpleNamespace:
    return SimpleNamespace(
        temperatures=temperatures,
        batteries=batteries,
        ipv4_addresses=ipv4,
    )


@unittest.skipUnless(HAS_PAHO, "paho-mqtt is not installed")
class PublisherTests(unittest.TestCase):
    def make_publisher(self, *, ready: bool = True, state: SimpleNamespace | None = None) -> tuple:
        settings = mqtt_publisher.MqttSettings(host="mqtt.example", username="exporter", password="secret")
        publisher = mqtt_publisher.MqttPublisher(
            settings,
            lambda: state or snapshot(),
            lambda value: '{"temperature_c": 50.0}',
            lambda value: (ready, "ready" if ready else "not ready"),
        )
        client = FakeClient()
        publisher.client = client
        return publisher, client

    def test_publish_discovery_and_state(self) -> None:
        publisher, client = self.make_publisher()
        publisher.publish_discovery()
        self.assertEqual(len(client.messages), 6)
        self.assertTrue(all(retain and qos == 1 for _, _, qos, retain in client.messages))
        publisher.publish_state()
        topics = {topic for topic, _, _, _ in client.messages}
        self.assertIn("home-sweet-lab-server/state", topics)
        self.assertIn("home-sweet-lab-server/availability", topics)
        self.assertIn("home-sweet-lab-server/availability/temperature", topics)
        self.assertIn("home-sweet-lab-server/availability/battery", topics)
        self.assertIn("home-sweet-lab-server/availability/ipv4", topics)

    def test_publish_state_marks_absent_sources_offline(self) -> None:
        publisher, client = self.make_publisher(state=snapshot(temperatures=(), batteries=(), ipv4=()))
        publisher.publish_state()
        messages = {topic: payload for topic, payload, _, _ in client.messages}
        self.assertEqual(messages["home-sweet-lab-server/availability"], "online")
        self.assertEqual(messages["home-sweet-lab-server/availability/temperature"], "offline")
        self.assertEqual(messages["home-sweet-lab-server/availability/battery"], "offline")
        self.assertEqual(messages["home-sweet-lab-server/availability/ipv4"], "offline")

    def test_publish_state_when_unready(self) -> None:
        publisher, client = self.make_publisher(ready=False)
        publisher.publish_state()
        messages = {topic: payload for topic, payload, _, _ in client.messages}
        self.assertEqual(messages["home-sweet-lab-server/availability"], "offline")
        self.assertEqual(messages["home-sweet-lab-server/availability/temperature"], "offline")

    def test_on_connect_subscribes_and_publishes(self) -> None:
        publisher, client = self.make_publisher()
        publisher._on_connect(client, None, None, SimpleNamespace(is_failure=False))
        self.assertEqual(client.subscriptions, [("homeassistant/status", 1)])
        topics = {topic for topic, _, _, _ in client.messages}
        self.assertIn("home-sweet-lab-server/state", topics)
        self.assertIn(
            "homeassistant/sensor/home_sweet_lab_server_cpu_temperature/config",
            topics,
        )

    def test_home_assistant_birth_republishes(self) -> None:
        publisher, client = self.make_publisher()
        publisher._on_message(
            client,
            None,
            SimpleNamespace(topic="homeassistant/status", payload=b"online"),
        )
        topics = {topic for topic, _, _, _ in client.messages}
        self.assertIn("home-sweet-lab-server/state", topics)
        self.assertIn(
            "homeassistant/sensor/home_sweet_lab_server_cpu_temperature/config",
            topics,
        )


if __name__ == "__main__":
    unittest.main()
