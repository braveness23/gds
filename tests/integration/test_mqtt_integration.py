"""Integration tests for MQTT output system."""

import json
import time

import pytest

from src.core.event_bus import DetectionEvent, Event, EventType
from src.output.mqtt_output import MQTTOutputNode


@pytest.fixture
def mqtt_node(event_bus, mock_paho_mqtt):
    """Create MQTT output node with mocked client."""
    node = MQTTOutputNode(
        broker="localhost",
        port=1883,
        topic="test/detections",
        node_id="test_node_001",
        qos=1,
        use_tls=False,
        event_bus=event_bus,
    )
    return node


class TestMQTTIntegration:
    """Test MQTT output integration with event bus."""

    def test_mqtt_connection_setup(self, mqtt_node, mock_paho_mqtt):
        """Test MQTT client is configured correctly."""
        mqtt_node.connect()

        # Wait for async connection to complete
        timeout = time.time() + 2.0
        while not mqtt_node.connected and time.time() < timeout:
            time.sleep(0.01)

        # Get the mock client instance
        client = mock_paho_mqtt._instances[-1]

        assert client.connected is True
        assert client._tls_set is False  # No TLS for localhost

    def test_detection_event_to_mqtt(self, event_bus, mqtt_node, mock_paho_mqtt):
        """Test detection event flows from event bus to MQTT."""
        mqtt_node.connect()

        # Wait for async connection to complete
        timeout = time.time() + 2.0
        while not mqtt_node.connected and time.time() < timeout:
            time.sleep(0.01)

        # Get the mock client
        client = mock_paho_mqtt._instances[-1]

        # Publish detection event to event bus
        detection = DetectionEvent(
            timestamp=123.456,
            source="aubio",
            confidence=0.85,
            detector_type="onset",
            buffer_index=42,
        )
        event_bus.publish(detection)

        # Wait for async processing
        time.sleep(0.2)

        # Verify MQTT publish was called
        messages = client.get_published_messages()
        assert len(messages) >= 1

        # Check published message contains detection data
        detection_msgs = [
            m for m in messages if b"detections" in m.topic.encode() or "detections" in m.topic
        ]
        assert len(detection_msgs) >= 1

        # Parse and verify content
        msg = json.loads(detection_msgs[0].payload.decode())
        assert msg["node_id"] == "test_node_001"
        # Detection data is nested under 'detection' key
        assert "detection" in msg or "confidence" in msg
        if "detection" in msg:
            assert msg["detection"]["confidence"] == 0.85
            assert msg["detection"]["detector_type"] == "onset"
        else:
            assert msg["confidence"] == 0.85
            assert msg["detector_type"] == "onset"

    def test_multiple_detections_published(self, event_bus, mqtt_node, mock_paho_mqtt):
        """Test multiple detections are all published."""
        mqtt_node.connect()

        # Wait for async connection to complete
        timeout = time.time() + 2.0
        while not mqtt_node.connected and time.time() < timeout:
            time.sleep(0.01)

        # Get the mock client
        client = mock_paho_mqtt._instances[-1]

        # Publish multiple detections
        for i in range(5):
            detection = DetectionEvent(
                timestamp=100.0 + i,
                source="test_detector",
                confidence=0.7 + i * 0.05,
                detector_type="onset",
                buffer_index=i,
            )
            event_bus.publish(detection)

        time.sleep(0.3)

        # Should have multiple publishes
        messages = client.get_published_messages()
        assert len(messages) >= 5

    def test_mqtt_disconnection_handling(self, mqtt_node, mock_paho_mqtt):
        """Test MQTT handles disconnection gracefully."""
        mqtt_node.connect()

        # Wait for async connection to complete
        timeout = time.time() + 2.0
        while not mqtt_node.connected and time.time() < timeout:
            time.sleep(0.01)

        # Get the mock client
        client = mock_paho_mqtt._instances[-1]

        assert mqtt_node.connected is True
        assert client.connected is True

        # Disconnect
        mqtt_node.disconnect()

        assert mqtt_node.connected is False
        assert client.connected is False

    def test_failed_messages_counted(self, event_bus, mqtt_node, mock_paho_mqtt):
        """Test failed messages are counted when publish fails."""
        # Connect first so subscriptions are set up
        mqtt_node.connect()

        # Wait for async connection to complete
        timeout = time.time() + 2.0
        while not mqtt_node.connected and time.time() < timeout:
            time.sleep(0.01)

        # Get client and make it fail on publish
        client = mock_paho_mqtt._instances[-1]
        client.fail_on_publish = True

        initial_failed = mqtt_node.messages_failed

        # Try to publish - should fail
        detection = DetectionEvent(
            timestamp=123.0,
            source="test",
            confidence=0.8,
            detector_type="onset",
            buffer_index=0,
        )
        event_bus.publish(detection)

        time.sleep(0.2)

        # Failed count should increase
        assert mqtt_node.messages_failed > initial_failed

    def test_health_event_published(self, event_bus, mqtt_node, mock_paho_mqtt):
        """Test health events are published to MQTT."""
        mqtt_node.connect()

        # Wait for async connection to complete
        timeout = time.time() + 2.0
        while not mqtt_node.connected and time.time() < timeout:
            time.sleep(0.01)

        # Get the mock client
        client = mock_paho_mqtt._instances[-1]

        # Publish health event
        health_event = Event(
            event_type=EventType.HEALTH,
            timestamp=200.0,
            source="system_monitor",
            data={"cpu_usage": 45.2, "memory_usage": 62.1},
        )
        event_bus.publish(health_event)

        time.sleep(0.2)

        # Verify health was published
        messages = client.get_published_messages()
        health_msgs = [m for m in messages if "health" in m.topic]

        assert len(health_msgs) >= 1, "Health event was not published"

    def test_message_format(self, event_bus, mqtt_node, mock_paho_mqtt):
        """Test published messages have correct format."""
        mqtt_node.connect()

        # Wait for async connection to complete
        timeout = time.time() + 2.0
        while not mqtt_node.connected and time.time() < timeout:
            time.sleep(0.01)

        # Get the mock client
        client = mock_paho_mqtt._instances[-1]

        # Publish detection
        detection = DetectionEvent(
            timestamp=123.456,
            source="aubio",
            confidence=0.92,
            detector_type="onset",
            buffer_index=10,
        )
        event_bus.publish(detection)

        time.sleep(0.2)

        # Get detection messages
        messages = client.get_published_messages(topic_filter="test/detections")
        assert len(messages) >= 1

        # Parse message
        msg_data = json.loads(messages[0].payload.decode())

        # Verify required fields
        assert "node_id" in msg_data
        assert "timestamp" in msg_data
        assert msg_data["node_id"] == "test_node_001"

        # Detection data may be nested under 'detection' key
        if "detection" in msg_data:
            assert msg_data["detection"]["confidence"] == 0.92
            assert msg_data["detection"]["detector_type"] == "onset"
        else:
            assert msg_data["confidence"] == 0.92
            assert msg_data["detector_type"] == "onset"
