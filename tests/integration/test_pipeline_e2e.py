"""End-to-end pipeline integration tests.

Tests the full audio → detection → EventBus → MQTT pipeline using in-process
mocks.  No external services required.

Architecture under test:
    AudioBuffer (injected)
        → ThresholdDetectorNode.receive()
        → EventBus (publishes DETECTION event)
        → MQTTOutputNode._on_detection_event()
        → MockMQTTBroker (routes via broker_paho fixture)
"""

import json
import time

import numpy as np
import pytest

from src.audio.audio_nodes import AudioBuffer
from src.core.event_bus import EventBus
from src.detection.detection_nodes import ThresholdDetectorNode
from src.output.mqtt_output import MQTTOutputNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_buffer(samples, sample_rate=48000, timestamp=None, buf_idx=0):
    return AudioBuffer(
        samples=samples,
        timestamp=timestamp or time.time(),
        sample_rate=sample_rate,
        channels=1,
        buffer_index=buf_idx,
    )


def _loud(n=1024, amplitude=0.9):
    return np.full(n, amplitude, dtype=np.float32)


def _silent(n=1024):
    return np.zeros(n, dtype=np.float32)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bus():
    eb = EventBus()
    eb.start()
    yield eb
    eb.stop()


@pytest.fixture
def detector(bus):
    return ThresholdDetectorNode(
        threshold_db=-20.0,  # amplitude ≈ 0.1 → our 0.9 samples trigger it
        min_duration_ms=0.0,
        publish_min_interval_ms=0.0,  # disable rate limiting for tests
        event_bus=bus,
    )


@pytest.fixture
def mqtt_out(bus, broker_paho):
    """MQTTOutputNode wired through the mock broker."""
    node = MQTTOutputNode(
        broker="localhost",
        port=1883,
        topic="gunshot/detections",
        node_id="pipeline_test_node",
        qos=1,
        event_bus=bus,
    )
    node.connect()
    time.sleep(0.05)  # let async on_connect fire
    yield node
    node.running = False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDetectionToMQTT:
    def test_loud_audio_publishes_detection(self, detector, mqtt_out, broker_paho):
        """Audio above threshold produces a detection message on MQTT."""
        assert mqtt_out.connected

        detector.receive(_make_buffer(_loud()))
        time.sleep(0.1)
        broker_paho.drain()

        msgs = broker_paho.get_messages("gunshot/detections")
        assert len(msgs) >= 1

        payload = json.loads(msgs[0].payload)
        assert payload["node_id"] == "pipeline_test_node"
        assert "timestamp" in payload

    def test_silent_audio_no_detection(self, detector, mqtt_out, broker_paho):
        """Silent audio produces no detection events."""
        # Capture only baseline messages (e.g. online status)
        initial = len(broker_paho.get_messages("gunshot/detections"))

        detector.receive(_make_buffer(_silent()))
        time.sleep(0.1)
        broker_paho.drain()

        assert len(broker_paho.get_messages("gunshot/detections")) == initial

    def test_node_specific_topic_published(self, detector, mqtt_out, broker_paho):
        """Detection is also published to the node-specific topic."""
        detector.receive(_make_buffer(_loud()))
        time.sleep(0.1)
        broker_paho.drain()

        node_msgs = broker_paho.get_messages("gunshot/pipeline_test_node/detections")
        assert len(node_msgs) >= 1

    def test_detection_increments_counter(self, detector, mqtt_out, broker_paho):
        """Each detection increments messages_published."""
        before = mqtt_out.messages_published

        for i in range(3):
            detector.receive(_make_buffer(_loud(), buf_idx=i))
            time.sleep(0.05)  # small gap so each buffer is treated as new event

        time.sleep(0.15)
        broker_paho.drain()

        assert mqtt_out.messages_published > before

    def test_detection_payload_structure(self, detector, mqtt_out, broker_paho):
        """Detection payload has expected top-level fields."""
        detector.receive(_make_buffer(_loud()))
        time.sleep(0.1)
        broker_paho.drain()

        msgs = broker_paho.get_messages("gunshot/detections")
        assert msgs, "Expected at least one detection message"

        payload = json.loads(msgs[0].payload)
        assert {"node_id", "timestamp", "detection"}.issubset(payload.keys())
        detection = payload["detection"]
        assert {"confidence", "detector_type"}.issubset(detection.keys())

    def test_below_threshold_no_detection(self, detector, mqtt_out, broker_paho):
        """Audio just below threshold (-20 dB ≈ 0.1) is not detected."""
        initial = len(broker_paho.get_messages("gunshot/detections"))

        # 0.05 amplitude ≈ -26 dB, below the -20 dB threshold
        quiet = np.full(1024, 0.05, dtype=np.float32)
        detector.receive(_make_buffer(quiet))
        time.sleep(0.1)
        broker_paho.drain()

        assert len(broker_paho.get_messages("gunshot/detections")) == initial
