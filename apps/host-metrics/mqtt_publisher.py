from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

import mqtt_discovery as discovery

LOGGER = logging.getLogger("host-metrics.mqtt")


@dataclass(frozen=True)
class MqttSettings:
    host: str
    port: int = 1883
    username: str | None = None
    password: str | None = None
    client_id: str = "home-sweet-lab-server"
    publish_interval: int = 30


class MqttPublisher:
    def __init__(
        self,
        settings: MqttSettings,
        snapshot_provider: Callable[[], Any],
        state_renderer: Callable[[Any], str],
        readiness: Callable[[Any], tuple[bool, str]],
    ) -> None:
        self.settings = settings
        self.snapshot_provider = snapshot_provider
        self.state_renderer = state_renderer
        self.readiness = readiness
        self.client: Any | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def available(self) -> bool:
        return mqtt is not None

    def start(self) -> bool:
        if mqtt is None:
            LOGGER.error("paho-mqtt is not installed; MQTT publishing is disabled")
            return False
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.settings.client_id)
        if self.settings.username:
            client.username_pw_set(self.settings.username, self.settings.password)
        client.will_set(discovery.AVAILABILITY_TOPIC, "offline", qos=1, retain=True)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client = client
        client.connect_async(self.settings.host, self.settings.port, keepalive=60)
        client.loop_start()
        self._thread = threading.Thread(target=self._state_loop, name="mqtt-state-publisher", daemon=True)
        self._thread.start()
        LOGGER.info(
            "MQTT publisher started for %s:%s as %s",
            self.settings.host,
            self.settings.port,
            self.settings.client_id,
        )
        return True

    def stop(self) -> None:
        self._stop.set()
        if self.client is not None:
            try:
                self.client.disconnect()
            except Exception:
                LOGGER.debug("MQTT disconnect failed", exc_info=True)
            self.client.loop_stop()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _on_connect(
        self,
        client: Any,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        if getattr(reason_code, "is_failure", False) or (
            isinstance(reason_code, int) and reason_code != 0
        ):
            LOGGER.error("MQTT connection failed: %s", reason_code)
            return
        LOGGER.info("MQTT connected to %s:%s", self.settings.host, self.settings.port)
        client.subscribe("homeassistant/status", qos=1)
        self.publish_discovery(client)
        self.publish_state(client)

    def _on_disconnect(
        self,
        client: Any,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        LOGGER.warning("MQTT disconnected: %s", reason_code)

    def _on_message(self, client: Any, userdata: Any, message: Any) -> None:
        if message.topic == "homeassistant/status" and message.payload == b"online":
            LOGGER.info("Home Assistant birth received; republishing discovery and state")
            self.publish_discovery(client)
            self.publish_state(client)

    def _publish(self, client: Any, topic: str, payload: str, retain: bool = True) -> None:
        result = client.publish(topic, payload, qos=1, retain=retain)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            LOGGER.warning("MQTT publish failed for %s: %s", topic, result.rc)

    def publish_discovery(self, client: Any | None = None) -> None:
        target = client or self.client
        if target is None or not target.is_connected():
            return
        for topic, payload in discovery.discovery_messages():
            self._publish(target, topic, payload, retain=True)

    def publish_state(self, client: Any | None = None) -> None:
        target = client or self.client
        if target is None or not target.is_connected():
            return
        snapshot = self.snapshot_provider()
        ready, _ = self.readiness(snapshot)
        for topic, payload in discovery.availability_messages(
            ready=ready,
            temperature_available=bool(getattr(snapshot, "temperatures", ())),
            battery_available=bool(getattr(snapshot, "batteries", ())),
            ipv4_available=bool(getattr(snapshot, "ipv4_addresses", ())),
        ):
            self._publish(target, topic, payload, retain=True)
        self._publish(target, discovery.STATE_TOPIC, self.state_renderer(snapshot), retain=True)

    def _state_loop(self) -> None:
        while not self._stop.wait(self.settings.publish_interval):
            try:
                self.publish_state()
            except Exception:
                LOGGER.exception("MQTT state publish failed")
