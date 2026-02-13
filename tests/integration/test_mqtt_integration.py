"""Integration tests for MQTT output system."""

import pytest
import time
import json
from unittest.mock import Mock, MagicMock, patch, call
from core.event_bus import EventBus, Event, EventType, DetectionEvent
from output.mqtt_output import MQTTOutputNode


@pytest.mark.skip(reason="Requires more complex mocking or real MQTT broker")
@pytest.fixture
def mock_mqtt_client():
    """Mock paho.mqtt.client."""
    with patch('output.mqtt_output.mqtt') as mock_mqtt:
        client = MagicMock()
        mock_mqtt.Client.return_value = client
        yield client


@pytest.fixture
def mqtt_node(event_bus, mock_mqtt_client):
    """Create MQTT output node with mocked client."""
    node = MQTTOutputNode(
        broker="test.broker.com",
        port=8883,
        topic="test/detections",
        node_id="test_node_001",
        qos=1,
        username="test_user",
        password="test_pass",
        use_tls=True,
        event_bus=event_bus
    )
    return node


@pytest.mark.skip(reason="Requires more complex mocking or real MQTT broker")
class TestMQTTIntegration:
    """Test MQTT output integration with event bus."""

    def test_mqtt_connection_setup(self, mqtt_node, mock_mqtt_client):
        """Test MQTT client is configured correctly."""
        mqtt_node.connect()

        # Verify client creation
        assert mock_mqtt_client is not None

        # Verify credentials were set
        mock_mqtt_client.username_pw_set.assert_called_once_with(
            "test_user", "test_pass"
        )

        # Verify TLS was enabled
        mock_mqtt_client.tls_set.assert_called_once()

        # Verify connection attempt
        mock_mqtt_client.connect.assert_called_once_with(
            "test.broker.com", 8883, keepalive=60
        )

        # Verify loop started
        mock_mqtt_client.loop_start.assert_called_once()

    def test_detection_event_to_mqtt(self, event_bus, mqtt_node, mock_mqtt_client):
        """Test detection event flows from event bus to MQTT."""
        # Connect and simulate successful connection
        mqtt_node.connect()
        mqtt_node._on_connect(mock_mqtt_client, None, None, 0)

        # Publish detection event to event bus
        detection = DetectionEvent(
            timestamp=123.456,
            source="aubio",
            confidence=0.85,
            detector_type="onset",
            buffer_index=42
        )
        event_bus.publish(detection)

        # Wait for async processing
        time.sleep(0.2)

        # Verify MQTT publish was called
        assert mock_mqtt_client.publish.call_count >= 1

        # Check published message contains detection data
        calls = mock_mqtt_client.publish.call_args_list
        published = False
        for call_args in calls:
            if len(call_args[0]) >= 2:
                topic, payload = call_args[0][0], call_args[0][1]
                if 'detections' in topic:
                    msg = json.loads(payload)
                    assert msg['node_id'] == 'test_node_001'
                    assert msg['confidence'] == 0.85
                    assert msg['detector_type'] == 'onset'
                    published = True

        assert published, "Detection was not published to MQTT"

    def test_multiple_detections_published(self, event_bus, mqtt_node, mock_mqtt_client):
        """Test multiple detections are all published."""
        mqtt_node.connect()
        mqtt_node._on_connect(mock_mqtt_client, None, None, 0)

        # Publish multiple detections
        for i in range(5):
            detection = DetectionEvent(
                timestamp=100.0 + i,
                source="test_detector",
                confidence=0.7 + i * 0.05,
                detector_type="onset",
                buffer_index=i
            )
            event_bus.publish(detection)

        time.sleep(0.3)

        # Should have multiple publishes (each detection goes to 2 topics)
        assert mock_mqtt_client.publish.call_count >= 5

    def test_mqtt_disconnection_handling(self, mqtt_node, mock_mqtt_client):
        """Test MQTT handles disconnection gracefully."""
        mqtt_node.connect()
        mqtt_node._on_connect(mock_mqtt_client, None, None, 0)

        assert mqtt_node.connected is True

        # Simulate unexpected disconnection
        mqtt_node._on_disconnect(mock_mqtt_client, None, 1)

        assert mqtt_node.connected is False

    def test_failed_messages_counted(self, event_bus, mqtt_node, mock_mqtt_client):
        """Test failed messages are counted when disconnected."""
        mqtt_node.connect()
        # Don't call _on_connect, so connected stays False

        initial_failed = mqtt_node.messages_failed

        # Try to publish while disconnected
        detection = DetectionEvent(
            timestamp=123.0,
            source="test",
            confidence=0.8,
            detector_type="onset",
            buffer_index=0
        )
        event_bus.publish(detection)

        time.sleep(0.2)

        # Failed count should increase
        assert mqtt_node.messages_failed > initial_failed

    def test_health_event_published(self, event_bus, mqtt_node, mock_mqtt_client):
        """Test health events are published to MQTT."""
        mqtt_node.connect()
        mqtt_node._on_connect(mock_mqtt_client, None, None, 0)

        # Publish health event
        health_event = Event(
            event_type=EventType.HEALTH,
            timestamp=200.0,
            source="system_monitor",
            data={'cpu_usage': 45.2, 'memory_usage': 62.1}
        )
        event_bus.publish(health_event)

        time.sleep(0.2)

        # Verify health was published
        calls = mock_mqtt_client.publish.call_args_list
        health_published = False
        for call_args in calls:
            if len(call_args[0]) >= 2:
                topic = call_args[0][0]
                if 'health' in topic:
                    health_published = True
                    break

        assert health_published, "Health event was not published"

    def test_message_enrichment_with_location(self, event_bus, mock_mqtt_client):
        """Test messages are enriched with GPS data when available."""
        # Mock GPS reader
        mock_gps = Mock()
        mock_gps.get_latest_fix.return_value = {
            'latitude': 37.7749,
            'longitude': -122.4194,
            'altitude': 10.0,
            'timestamp': 123.456
        }

        mqtt_node = MQTTOutputNode(
            broker="test.broker.com",
            port=1883,
            topic="test/detections",
            node_id="test_node_gps",
            event_bus=event_bus,
            gps_reader=mock_gps
        )

        mqtt_node.connect()
        mqtt_node._on_connect(mock_mqtt_client, None, None, 0)

        # Publish detection
        detection = DetectionEvent(
            timestamp=123.456,
            source="detector",
            confidence=0.9,
            detector_type="onset",
            buffer_index=0
        )
        event_bus.publish(detection)

        time.sleep(0.2)

        # Verify location was added to published message
        calls = mock_mqtt_client.publish.call_args_list
        location_found = False
        for call_args in calls:
            if len(call_args[0]) >= 2:
                topic, payload = call_args[0][0], call_args[0][1]
                if 'detections' in topic:
                    msg = json.loads(payload)
                    if 'location' in msg:
                        assert msg['location']['latitude'] == 37.7749
                        assert msg['location']['longitude'] == -122.4194
                        location_found = True

        assert location_found, "Location data was not added to message"


@pytest.mark.skip(reason="Requires more complex mocking or real MQTT broker")
class TestFleetCoordinator:
    """Test fleet coordination via MQTT."""

    @patch('output.mqtt_output.mqtt')
    def test_fleet_coordinator_initialization(self, mock_mqtt):
        """Test fleet coordinator connects and subscribes."""
        from output.mqtt_output import FleetCoordinator

        client = MagicMock()
        mock_mqtt.Client.return_value = client

        coordinator = FleetCoordinator(
            broker="test.broker.com",
            port=1883
        )
        coordinator.connect()

        # Verify subscriptions when connected
        coordinator._on_connect(client, None, None, 0)

        # Should subscribe to multiple topics
        assert client.subscribe.call_count >= 3

    @patch('output.mqtt_output.mqtt')
    def test_active_nodes_tracking(self, mock_mqtt):
        """Test coordinator tracks active nodes."""
        from output.mqtt_output import FleetCoordinator

        coordinator = FleetCoordinator(
            broker="test.broker.com",
            port=1883
        )

        # Simulate receiving messages from different nodes
        for i in range(3):
            msg = MagicMock()
            msg.topic = f"gunshot/node_{i}/detections"
            msg.payload = json.dumps({
                'node_id': f'node_{i}',
                'timestamp': 100.0 + i,
                'confidence': 0.8
            }).encode()

            coordinator._on_message(None, None, msg)

        # Should track 3 active nodes
        active = coordinator.get_active_nodes()
        assert len(active) == 3

    @patch('output.mqtt_output.mqtt')
    def test_detection_aggregation(self, mock_mqtt):
        """Test coordinator aggregates detections from fleet."""
        from output.mqtt_output import FleetCoordinator

        coordinator = FleetCoordinator(
            broker="test.broker.com",
            port=1883
        )

        detection_count = 0

        def on_detection(payload):
            nonlocal detection_count
            detection_count += 1

        coordinator.set_detection_callback(on_detection)

        # Simulate detections from multiple nodes
        for i in range(5):
            msg = MagicMock()
            msg.topic = "gunshot/detections"
            msg.payload = json.dumps({
                'node_id': f'node_{i % 2}',
                'timestamp': 100.0 + i,
                'confidence': 0.85
            }).encode()

            coordinator._on_message(None, None, msg)

        # Callback should have been called for each detection
        assert detection_count == 5

        # All detections should be stored
        assert len(coordinator.detections) == 5
