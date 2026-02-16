"""Mock MQTT client for testing without real broker."""

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class MockPublishResult:
    """Mock result from publish operation."""

    rc: int = 0  # 0 = success, 1+ = failure
    mid: int = 1  # message ID


@dataclass
class MockMessage:
    """Mock MQTT message."""

    topic: str
    payload: bytes
    qos: int
    retain: bool = False
    timestamp: float = field(default_factory=time.time)


class MockMQTTClient:
    """
    Mock MQTT client that simulates paho.mqtt.client.Client behavior.

    Features:
    - Simulates connect/disconnect
    - Records published messages
    - Supports callbacks
    - Can simulate failures
    - Thread-safe for async testing
    """

    # Class-level tracking for all instances
    _instances: List["MockMQTTClient"] = []
    _lock = threading.Lock()

    def __init__(
        self,
        client_id: str = "",
        clean_session: bool = True,
        fail_on_connect: bool = False,
        fail_on_publish: bool = False,
        connection_delay: float = 0.0,
    ):
        """
        Initialize mock client.

        Args:
            client_id: Client identifier
            clean_session: Clean session flag
            fail_on_connect: Simulate connection failure
            fail_on_publish: Simulate publish failure
            connection_delay: Delay before connection succeeds (simulates network latency)
        """
        self.client_id = client_id
        self.clean_session = clean_session
        self.fail_on_connect = fail_on_connect
        self.fail_on_publish = fail_on_publish
        self.connection_delay = connection_delay

        # State
        self.connected = False
        self.loop_running = False

        # Callbacks
        self.on_connect: Optional[Callable] = None
        self.on_disconnect: Optional[Callable] = None
        self.on_publish: Optional[Callable] = None
        self.on_message: Optional[Callable] = None

        # Configuration
        self._username: Optional[str] = None
        self._password: Optional[str] = None
        self._tls_set = False
        self._tls_insecure = False
        self._max_inflight = 20
        self._max_queued = 0

        # Message tracking
        self.published_messages: List[MockMessage] = []
        self.subscriptions: List[tuple] = []  # (topic, qos)

        # Thread for async callbacks
        self._thread: Optional[threading.Thread] = None

        # Register instance
        with MockMQTTClient._lock:
            MockMQTTClient._instances.append(self)

    def username_pw_set(self, username: str, password: Optional[str] = None):
        """Set username and password."""
        self._username = username
        self._password = password

    def tls_set(
        self,
        ca_certs=None,
        certfile=None,
        keyfile=None,
        cert_reqs=None,
        tls_version=None,
        ciphers=None,
    ):
        """Enable TLS."""
        self._tls_set = True

    def tls_insecure_set(self, value: bool):
        """Set TLS insecure mode."""
        self._tls_insecure = value

    def max_inflight_messages_set(self, inflight: int):
        """Set max inflight messages."""
        self._max_inflight = inflight

    def max_queued_messages_set(self, queue_size: int):
        """Set max queued messages."""
        self._max_queued = queue_size

    def connect(self, host: str, port: int = 1883, keepalive: int = 60):
        """Connect to broker (simulated)."""
        if self.fail_on_connect:
            raise ConnectionError(f"Mock connection failure to {host}:{port}")

        # Simulate connection delay
        if self.connection_delay > 0:
            time.sleep(self.connection_delay)

        self.connected = True

        # Trigger on_connect callback asynchronously (in real paho-mqtt,
        # this happens after connect returns). Delay slightly to simulate async.
        if self.on_connect:
            # Call the callback in a separate thread to avoid blocking
            import threading

            def call_callback():
                time.sleep(0.01)  # Small delay to simulate async
                try:
                    self.on_connect(self, None, None, 0)
                except Exception as e:
                    print(f"[MockMQTTClient] Exception in on_connect callback: {e}")
                    import traceback

                    traceback.print_exc()

            thread = threading.Thread(target=call_callback, daemon=True)
            thread.start()

    def reconnect(self):
        """Reconnect to broker."""
        return self.connect("mock_host", 1883)

    def disconnect(self):
        """Disconnect from broker."""
        was_connected = self.connected
        self.connected = False

        # Trigger on_disconnect callback
        if was_connected and self.on_disconnect:
            # rc=0 means clean disconnect
            self.on_disconnect(self, None, 0)

    def loop_start(self):
        """Start network loop in background thread."""
        self.loop_running = True
        # In real implementation, would start background thread
        # For mock, we just track the state

    def loop_stop(self):
        """Stop network loop."""
        self.loop_running = False

    def publish(self, topic: str, payload=None, qos: int = 0, retain: bool = False):
        """
        Publish message (simulated).

        Returns MockPublishResult with rc=0 for success, rc=1 for failure.
        """
        if self.fail_on_publish:
            return MockPublishResult(rc=1)

        if not self.connected:
            return MockPublishResult(rc=1)

        # Record message
        message = MockMessage(
            topic=topic,
            payload=payload if isinstance(payload, bytes) else str(payload).encode(),
            qos=qos,
            retain=retain,
        )
        self.published_messages.append(message)

        # Trigger on_publish callback
        if self.on_publish:
            mid = len(self.published_messages)
            self.on_publish(self, None, mid)

        return MockPublishResult(rc=0, mid=len(self.published_messages))

    def subscribe(self, topic: str, qos: int = 0):
        """Subscribe to topic."""
        self.subscriptions.append((topic, qos))
        # Return (result, mid)
        return (0, len(self.subscriptions))

    def get_published_messages(self, topic_filter: Optional[str] = None) -> List[MockMessage]:
        """
        Get published messages, optionally filtered by topic.

        Args:
            topic_filter: Topic to filter by (supports wildcards)
        """
        if topic_filter is None:
            return self.published_messages.copy()

        # Simple wildcard matching
        filtered = []
        for msg in self.published_messages:
            if self._topic_matches(msg.topic, topic_filter):
                filtered.append(msg)
        return filtered

    def _topic_matches(self, topic: str, pattern: str) -> bool:
        """Simple topic matching with + and # wildcards."""
        if pattern == topic:
            return True

        topic_parts = topic.split("/")
        pattern_parts = pattern.split("/")

        if len(pattern_parts) > len(topic_parts):
            return False

        for i, pattern_part in enumerate(pattern_parts):
            if pattern_part == "#":
                return True
            if pattern_part == "+":
                continue
            if i >= len(topic_parts) or pattern_part != topic_parts[i]:
                return False

        return len(pattern_parts) == len(topic_parts)

    def reset(self):
        """Reset mock state."""
        self.published_messages.clear()
        self.subscriptions.clear()
        self.connected = False
        self.loop_running = False

    @classmethod
    def reset_all(cls):
        """Reset all mock instances."""
        with cls._lock:
            for instance in cls._instances:
                instance.reset()
            cls._instances.clear()
