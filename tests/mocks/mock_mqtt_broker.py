"""In-process MQTT broker for routing integration tests.

Routes published messages to all matching subscribers, enabling real
client-server communication tests without a running MQTT broker.
"""

import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple


def _topic_matches(topic: str, pattern: str) -> bool:
    """MQTT topic matching with + and # wildcards."""
    if pattern == topic:
        return True
    topic_parts = topic.split("/")
    pattern_parts = pattern.split("/")
    if len(pattern_parts) > len(topic_parts) and "#" not in pattern_parts:
        return False
    for i, part in enumerate(pattern_parts):
        if part == "#":
            return True
        if part == "+":
            if i >= len(topic_parts):
                return False
            continue
        if i >= len(topic_parts) or part != topic_parts[i]:
            return False
    return len(pattern_parts) == len(topic_parts)


class MockMQTTBroker:
    """
    Shared in-process MQTT broker.

    All MockMQTTClient instances created with ``client._broker = this`` will
    route published messages to matching subscribers, enabling real end-to-end
    pub/sub testing without an external broker.

    Usage::

        broker = MockMQTTBroker()

        publisher = MockMQTTClient()
        publisher._broker = broker

        subscriber = MockMQTTClient()
        subscriber._broker = broker
        subscriber.on_message = my_handler
        subscriber.subscribe("gunshot/+/detections")

        publisher.connect("localhost")
        subscriber.connect("localhost")

        publisher.publish("gunshot/node1/detections", b"hello")
        broker.drain()
        # my_handler was called with the message
    """

    def __init__(self):
        self._lock = threading.Lock()
        # pattern → list of (client, on_message_callback_at_subscribe_time)
        # We snapshot the callback at subscribe time; if on_message changes
        # later we read it fresh from the client.
        self._subscriptions: Dict[str, List[Tuple[Any, Callable]]] = {}
        self._retained: Dict[str, Any] = {}  # topic → MockMessage (last retained)
        self.all_messages: List[Any] = []

        # In-flight delivery tracking for drain()
        self._pending = 0
        self._pending_lock = threading.Lock()
        self._idle = threading.Event()
        self._idle.set()

    # ------------------------------------------------------------------
    # Internal API (called by MockMQTTClient)
    # ------------------------------------------------------------------

    def _register_subscription(self, client: Any, topic: str) -> None:
        """Register a subscription on behalf of a client."""
        with self._lock:
            if topic not in self._subscriptions:
                self._subscriptions[topic] = []
            # Store (client_ref, topic) so we can look up on_message at delivery time
            self._subscriptions[topic].append(client)

        # Deliver any retained message for this topic immediately
        retained = {}
        with self._lock:
            for ret_topic, msg in self._retained.items():
                if _topic_matches(ret_topic, topic):
                    retained[ret_topic] = msg
        for msg in retained.values():
            self._deliver_to(client, msg)

    def _route(self, message: Any) -> None:
        """Route a published message to all matching subscribers."""
        with self._lock:
            self.all_messages.append(message)
            if message.retain:
                self._retained[message.topic] = message
            recipients = []
            for pattern, clients in self._subscriptions.items():
                if _topic_matches(message.topic, pattern):
                    recipients.extend(clients)

        for client in recipients:
            self._deliver_to(client, message)

    def _deliver_to(self, client: Any, message: Any) -> None:
        """Deliver a message to one client asynchronously."""
        callback = client.on_message
        if callback is None:
            return

        with self._pending_lock:
            self._pending += 1
            self._idle.clear()

        def _run(cb=callback, c=client, msg=message):
            try:
                cb(c, None, msg)
            finally:
                with self._pending_lock:
                    self._pending -= 1
                    if self._pending == 0:
                        self._idle.set()

        threading.Thread(target=_run, daemon=True).start()

    # ------------------------------------------------------------------
    # Public API (for test assertions and control)
    # ------------------------------------------------------------------

    def drain(self, timeout: float = 1.0) -> bool:
        """
        Wait until all in-flight message deliveries complete.

        Returns True if drained within timeout, False if timed out.
        """
        return self._idle.wait(timeout=timeout)

    def get_messages(self, topic_filter: Optional[str] = None) -> List[Any]:
        """Return all published messages, optionally filtered by topic pattern."""
        with self._lock:
            messages = list(self.all_messages)
        if topic_filter is None:
            return messages
        return [m for m in messages if _topic_matches(m.topic, topic_filter)]

    def get_message_payloads(self, topic_filter: Optional[str] = None) -> List[bytes]:
        """Convenience: return raw payloads for matching messages."""
        return [m.payload for m in self.get_messages(topic_filter)]

    def reset(self) -> None:
        """Clear all broker state. Call between tests."""
        with self._lock:
            self._subscriptions.clear()
            self._retained.clear()
            self.all_messages.clear()
        with self._pending_lock:
            self._pending = 0
            self._idle.set()
