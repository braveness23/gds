"""Multi-node distributed integration tests.

Tests scenarios specific to operating multiple nodes in a distributed system:
- Broadcast: server targets all known nodes simultaneously
- Node isolation: each node only applies commands addressed to it
- Concurrent detections: multiple nodes independently publish to MQTT
- Fleet coordination: each node gets a unique topic namespace
"""

import json
import time

import numpy as np
import pytest
import yaml

from src.audio.audio_nodes import AudioBuffer
from src.config.config import Config
from src.core.event_bus import EventBus
from src.detection.detection_nodes import ThresholdDetectorNode
from src.output.mqtt_output import MQTTOutputNode
from src.remote_config.client import RemoteConfigClient
from src.remote_config.server import RemoteConfigServer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_node_config(tmp_path, node_id: str, log_level: str = "INFO"):
    cfg_path = tmp_path / f"{node_id}.yaml"
    with open(cfg_path, "w") as f:
        yaml.dump(
            {
                "system": {"node_id": node_id, "log_level": log_level},
                "output": {"mqtt": {"broker": "localhost", "port": 1883}},
                "remote_config": {
                    "enabled": True,
                    "mqtt": {"broker": "localhost", "port": 1883},
                },
                "detection": {"aubio": {"threshold": 0.3}},
            },
            f,
        )
    return Config(str(cfg_path))


def _make_audio_buffer(amplitude=0.9, n=1024):
    samples = np.full(n, amplitude, dtype=np.float32)
    return AudioBuffer(
        samples=samples,
        timestamp=time.time(),
        sample_rate=48000,
        channels=1,
        buffer_index=0,
    )


def _drain(broker_paho, extra=0.2):
    broker_paho.drain()
    time.sleep(extra)
    broker_paho.drain()


# ---------------------------------------------------------------------------
# Multi-node remote config tests
# ---------------------------------------------------------------------------


class TestMultiNodeRemoteConfig:
    def test_broadcast_reaches_all_nodes(self, broker_paho, tmp_path):
        """Broadcast config change is applied on all registered nodes."""
        node_ids = ["alpha", "beta", "gamma"]

        server = RemoteConfigServer(broker="localhost", port=1883, response_timeout=2.0)
        server.start()
        time.sleep(0.05)

        clients = []
        configs = []
        try:
            for nid in node_ids:
                cfg = _make_node_config(tmp_path, nid)
                configs.append(cfg)
                rc = RemoteConfigClient(config=cfg, node_id=nid)
                rc.start()
                clients.append(rc)
                server.known_nodes[nid] = {"last_seen": time.time()}

            time.sleep(0.1)

            server.broadcast_config({"detection.aubio.threshold": 0.8})
            _drain(broker_paho, extra=0.4)

            for cfg in configs:
                assert cfg.get("detection.aubio.threshold") == pytest.approx(0.8), (
                    f"Node {cfg.get('system.node_id')} did not apply broadcast"
                )
        finally:
            for rc in clients:
                rc.stop()
            server.stop()

    def test_targeted_change_does_not_affect_others(self, broker_paho, tmp_path):
        """Change addressed to one node is not applied to other nodes."""
        server = RemoteConfigServer(broker="localhost", port=1883, response_timeout=2.0)
        server.start()
        time.sleep(0.05)

        cfg_a = _make_node_config(tmp_path, "node_a")
        cfg_b = _make_node_config(tmp_path, "node_b")

        node_a = RemoteConfigClient(config=cfg_a, node_id="node_a")
        node_b = RemoteConfigClient(config=cfg_b, node_id="node_b")
        node_a.start()
        node_b.start()
        time.sleep(0.1)

        server.known_nodes["node_a"] = {"last_seen": time.time()}
        server.known_nodes["node_b"] = {"last_seen": time.time()}

        try:
            # Only target node_a
            server.set_node_config("node_a", {"system.log_level": "DEBUG"})
            _drain(broker_paho)

            assert cfg_a.get("system.log_level") == "DEBUG"
            assert cfg_b.get("system.log_level") == "INFO"  # unchanged
        finally:
            node_a.stop()
            node_b.stop()
            server.stop()

    def test_each_node_responds_independently(self, broker_paho, tmp_path):
        """Each node publishes its own response to its own response topic."""
        server = RemoteConfigServer(broker="localhost", port=1883, response_timeout=2.0)
        server.start()
        time.sleep(0.05)

        node_ids = ["resp_a", "resp_b"]
        clients = []
        try:
            for nid in node_ids:
                cfg = _make_node_config(tmp_path, nid)
                rc = RemoteConfigClient(config=cfg, node_id=nid)
                rc.start()
                clients.append(rc)
                server.known_nodes[nid] = {"last_seen": time.time()}

            time.sleep(0.1)

            server.broadcast_config({"system.log_level": "WARNING"})
            _drain(broker_paho, extra=0.4)

            for nid in node_ids:
                responses = broker_paho.get_messages(f"gunshot/config/{nid}/response")
                set_responses = [
                    json.loads(m.payload)
                    for m in responses
                    if json.loads(m.payload).get("command") == "set_config_response"
                ]
                assert len(set_responses) >= 1, f"No response from {nid}"
        finally:
            for rc in clients:
                rc.stop()
            server.stop()


# ---------------------------------------------------------------------------
# Multi-node detection tests
# ---------------------------------------------------------------------------


class TestMultiNodeDetection:
    def test_each_node_publishes_to_unique_topic(self, broker_paho):
        """Multiple detection nodes each publish to their own node-specific topic."""
        buses = []
        nodes = []
        try:
            for i in range(3):
                bus = EventBus()
                bus.start()
                buses.append(bus)

                detector = ThresholdDetectorNode(
                    threshold_db=-20.0,
                    min_duration_ms=0.0,
                    publish_min_interval_ms=0.0,
                    event_bus=bus,
                )

                mqtt_node = MQTTOutputNode(
                    broker="localhost",
                    port=1883,
                    topic="gunshot/detections",
                    node_id=f"node_{i}",
                    qos=0,
                    event_bus=bus,
                )
                mqtt_node.connect()
                nodes.append((detector, mqtt_node))

            time.sleep(0.08)  # let all on_connect callbacks fire

            # Trigger detection on each node
            buf = _make_audio_buffer()
            for detector, _ in nodes:
                detector.receive(buf)

            time.sleep(0.15)
            broker_paho.drain()

            # Each node publishes to its own specific topic
            for i in range(3):
                msgs = broker_paho.get_messages(f"gunshot/node_{i}/detections")
                assert len(msgs) >= 1, f"node_{i} did not publish detection"

        finally:
            for bus in buses:
                bus.stop()
            for _, mqtt_node in nodes:
                mqtt_node.running = False

    def test_shared_detection_topic_gets_all_nodes(self, broker_paho):
        """The common 'gunshot/detections' topic receives events from all nodes."""
        buses = []
        nodes = []
        n_nodes = 3

        try:
            for i in range(n_nodes):
                bus = EventBus()
                bus.start()
                buses.append(bus)

                detector = ThresholdDetectorNode(
                    threshold_db=-20.0,
                    min_duration_ms=0.0,
                    publish_min_interval_ms=0.0,
                    event_bus=bus,
                )

                mqtt_node = MQTTOutputNode(
                    broker="localhost",
                    port=1883,
                    topic="gunshot/detections",
                    node_id=f"fleet_node_{i}",
                    qos=0,
                    event_bus=bus,
                )
                mqtt_node.connect()
                nodes.append((detector, mqtt_node))

            time.sleep(0.08)

            buf = _make_audio_buffer()
            for detector, _ in nodes:
                detector.receive(buf)

            time.sleep(0.15)
            broker_paho.drain()

            # All detections land on the shared topic
            all_msgs = broker_paho.get_messages("gunshot/detections")
            node_ids_seen = {json.loads(m.payload)["node_id"] for m in all_msgs}
            expected = {f"fleet_node_{i}" for i in range(n_nodes)}
            assert expected == node_ids_seen

        finally:
            for bus in buses:
                bus.stop()
            for _, mqtt_node in nodes:
                mqtt_node.running = False
