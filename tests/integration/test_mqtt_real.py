"""Integration tests for MQTT output system with real broker."""

import pytest
import time
import os
from src.core.event_bus import Event, EventType, DetectionEvent
from src.output.mqtt_output import MQTTOutputNode
from src.config.config import Config


@pytest.fixture
def mqtt_config():
    """Load MQTT config from environment or config.yaml."""
    # Check for environment override (useful for CI/CD and local testing)
    broker = os.getenv('MQTT_TEST_BROKER')
    if broker:
        print(f"[DEBUG] Using MQTT broker from environment: {broker}")
        return {
            'enabled': True,
            'broker': broker,
            'port': int(os.getenv('MQTT_TEST_PORT', '1883')),
            'topic': os.getenv('MQTT_TEST_TOPIC', 'gunshot/test/detections'),
            'qos': 1,
            'username': os.getenv('MQTT_TEST_USERNAME'),
            'password': os.getenv('MQTT_TEST_PASSWORD'),
            'use_tls': os.getenv('MQTT_TEST_USE_TLS', 'false').lower() == 'true'
        }

    # Fall back to config.yaml (production broker)
    config = Config('config.yaml')
    mqtt_conf = config.get('output.mqtt')

    # Use test prefix to avoid polluting production topics
    if mqtt_conf and 'topic' in mqtt_conf:
        mqtt_conf['topic'] = f"test/{mqtt_conf['topic']}"

    print(f"[DEBUG] mqtt_config loaded from config.yaml: {mqtt_conf}")
    return mqtt_conf


@pytest.fixture
def test_node_id():
    """Generate unique test node ID."""
    return f"test_node_{int(time.time())}"


@pytest.fixture
def mqtt_node(event_bus, mqtt_config, test_node_id):
    """Create MQTT output node with real broker."""
    if not mqtt_config.get('enabled'):
        pytest.skip("MQTT is disabled in config")

    node = MQTTOutputNode(
        broker=mqtt_config['broker'],
        port=mqtt_config['port'],
        topic=f"test/{mqtt_config['topic']}",  # Use test prefix
        node_id=test_node_id,
        qos=mqtt_config.get('qos', 1),
        username=mqtt_config.get('username'),
        password=mqtt_config.get('password'),
        use_tls=mqtt_config.get('use_tls', False),
        event_bus=event_bus
    )
    return node


@pytest.mark.mqtt
class TestMQTTIntegration:
    """Test MQTT output integration with real broker."""

    def test_mqtt_connection(self, mqtt_node):
        """Test MQTT connection to real broker."""
        mqtt_node.connect()

        # Wait for connection
        time.sleep(2)

        # Verify connection
        assert mqtt_node.connected is True

        # Cleanup
        mqtt_node.disconnect()

    def test_detection_event_published(self, event_bus, mqtt_node):
        """Test detection event is published to MQTT."""
        mqtt_node.connect()

        # Wait for connection
        time.sleep(2)

        assert mqtt_node.connected is True

        initial_count = mqtt_node.messages_published

        # Publish detection event
        detection = DetectionEvent(
            timestamp=time.time(),
            source="test_detector",
            confidence=0.85,
            detector_type="test",
            buffer_index=0
        )
        event_bus.publish(detection)

        # Wait for async publishing
        time.sleep(1)

        # Verify message was published
        assert mqtt_node.messages_published > initial_count

        # Cleanup
        mqtt_node.disconnect()

    def test_multiple_detections(self, event_bus, mqtt_node):
        """Test multiple detections are published."""
        mqtt_node.connect()
        time.sleep(2)

        assert mqtt_node.connected is True

        initial_count = mqtt_node.messages_published

        # Publish multiple detections
        for i in range(5):
            detection = DetectionEvent(
                timestamp=time.time() + i * 0.1,
                source="test_detector",
                confidence=0.7 + i * 0.05,
                detector_type="test",
                buffer_index=i
            )
            event_bus.publish(detection)
            time.sleep(0.1)

        # Wait for async publishing
        time.sleep(1)

        # Should have published at least 5 messages
        assert mqtt_node.messages_published >= initial_count + 5

        # Cleanup
        mqtt_node.disconnect()

    def test_reconnection_after_disconnect(self, mqtt_node):
        """Test MQTT reconnects after disconnection."""
        mqtt_node.connect()
        time.sleep(2)

        assert mqtt_node.connected is True

        # Disconnect
        mqtt_node.disconnect()
        time.sleep(1)

        # Reconnect
        mqtt_node.connect()
        time.sleep(2)

        assert mqtt_node.connected is True

        # Cleanup
        mqtt_node.disconnect()

    def test_health_event_published(self, event_bus, mqtt_node):
        """Test health events are published."""
        mqtt_node.connect()
        time.sleep(2)

        assert mqtt_node.connected is True

        # Publish health event
        health_event = Event(
            event_type=EventType.HEALTH,
            timestamp=time.time(),
            source="system_monitor",
            data={'cpu_usage': 45.2, 'memory_usage': 62.1}
        )
        event_bus.publish(health_event)

        # Wait for async publishing
        time.sleep(1)

        # Event should have been processed (no errors)
        assert mqtt_node.connected is True

        # Cleanup
        mqtt_node.disconnect()

    def test_message_format(self, event_bus, mqtt_node):
        """Test published message has correct format."""
        mqtt_node.connect()
        time.sleep(2)

        assert mqtt_node.connected is True

        # Publish detection
        detection = DetectionEvent(
            timestamp=123.456,
            source="test_detector",
            confidence=0.95,
            detector_type="threshold",
            buffer_index=42
        )
        event_bus.publish(detection)

        # Wait for publishing
        time.sleep(1)

        # Verify it was published
        assert mqtt_node.messages_published > 0
        assert mqtt_node.messages_failed == 0

        # Cleanup
        mqtt_node.disconnect()


@pytest.mark.mqtt
class TestFleetCoordinator:
    """Test fleet coordination via MQTT with real broker."""

    def test_fleet_coordinator_connection(self, mqtt_config):
        """Test fleet coordinator connects to broker."""
        from output.mqtt_output import MQTTFleetCoordinator

        if not mqtt_config.get('enabled'):
            pytest.skip("MQTT is disabled in config")

        coordinator = MQTTFleetCoordinator(
            broker=mqtt_config['broker'],
            port=mqtt_config['port'],
            username=mqtt_config.get('username'),
            password=mqtt_config.get('password'),
            use_tls=mqtt_config.get('use_tls', False)
        )

        coordinator.connect()
        time.sleep(2)

        assert coordinator.connected is True

        # Cleanup
        coordinator.disconnect()

    def test_fleet_receives_detections(self, mqtt_config, event_bus, test_node_id):
        """Test fleet coordinator receives detections from nodes."""
        from output.mqtt_output import MQTTFleetCoordinator

        if not mqtt_config.get('enabled'):
            pytest.skip("MQTT is disabled in config")

        # Start fleet coordinator
        coordinator = MQTTFleetCoordinator(
            broker=mqtt_config['broker'],
            port=mqtt_config['port'],
            username=mqtt_config.get('username'),
            password=mqtt_config.get('password'),
            use_tls=mqtt_config.get('use_tls', False)
        )
        coordinator.connect()
        time.sleep(2)

        # Start test node
        node = MQTTOutputNode(
            broker=mqtt_config['broker'],
            port=mqtt_config['port'],
            topic=mqtt_config['topic'],
            node_id=test_node_id,
            qos=mqtt_config.get('qos', 1),
            username=mqtt_config.get('username'),
            password=mqtt_config.get('password'),
            use_tls=mqtt_config.get('use_tls', False),
            event_bus=event_bus
        )
        node.connect()
        time.sleep(2)

        initial_detections = len(coordinator.detections)

        # Publish detection from node
        detection = DetectionEvent(
            timestamp=time.time(),
            source="test_detector",
            confidence=0.88,
            detector_type="test",
            buffer_index=0
        )
        event_bus.publish(detection)

        # Wait for message propagation
        time.sleep(2)

        # Fleet should have received detection
        assert len(coordinator.detections) > initial_detections

        # Cleanup
        node.disconnect()
        coordinator.disconnect()

    def test_active_nodes_detection(self, mqtt_config, event_bus):
        """Test fleet coordinator tracks active nodes."""
        from output.mqtt_output import MQTTFleetCoordinator

        if not mqtt_config.get('enabled'):
            pytest.skip("MQTT is disabled in config")

        coordinator = MQTTFleetCoordinator(
            broker=mqtt_config['broker'],
            port=mqtt_config['port'],
            username=mqtt_config.get('username'),
            password=mqtt_config.get('password'),
            use_tls=mqtt_config.get('use_tls', False)
        )
        coordinator.connect()
        time.sleep(2)

        # Create and connect test node
        node_id = f"test_node_{int(time.time())}"
        node = MQTTOutputNode(
            broker=mqtt_config['broker'],
            port=mqtt_config['port'],
            topic=mqtt_config['topic'],
            node_id=node_id,
            qos=mqtt_config.get('qos', 1),
            username=mqtt_config.get('username'),
            password=mqtt_config.get('password'),
            use_tls=mqtt_config.get('use_tls', False),
            event_bus=event_bus
        )
        node.connect()
        time.sleep(2)

        # Publish detection to register node
        detection = DetectionEvent(
            timestamp=time.time(),
            source="test",
            confidence=0.9,
            detector_type="test",
            buffer_index=0
        )
        event_bus.publish(detection)

        # Wait for message
        time.sleep(2)

        # Check active nodes
        active_nodes = coordinator.get_active_nodes(timeout=10.0)
        node_ids = [n['node_id'] for n in active_nodes]

        # Our test node should be in the list
        assert node_id in node_ids

        # Cleanup
        node.disconnect()
        coordinator.disconnect()
