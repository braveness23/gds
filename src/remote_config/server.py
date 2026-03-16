"""Remote configuration server for strix central management.

Manages configuration of multiple nodes via MQTT.
Provides command interface for config operations.
"""

import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

import paho.mqtt.client as mqtt


class ChangeState(Enum):
    """State of a configuration change operation."""

    PENDING = "pending"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    TIMEOUT = "timeout"


@dataclass
class ConfigChange:
    """Represents a configuration change operation."""

    change_id: str
    node_id: str
    changes: Dict[str, Any]
    state: ChangeState = ChangeState.PENDING
    created_at: float = field(default_factory=time.time)
    sent_at: Optional[float] = None
    acknowledged_at: Optional[float] = None
    confirmed_at: Optional[float] = None
    response_data: Optional[Dict] = None
    error_message: Optional[str] = None


class RemoteConfigServer:
    """
    Server for managing remote configuration of GDS nodes.

    Topic Structure:
    - gunshot/config/{node_id}/set      → Send configuration changes
    - gunshot/config/{node_id}/get      → Request config dump
    - gunshot/config/{node_id}/status   ← Receive status updates
    - gunshot/config/{node_id}/response ← Receive command responses

    Broadcast:
    - gunshot/config/all/set            → Send to all nodes
    """

    def __init__(
        self,
        broker: str,
        port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_tls: bool = False,
        tls_ca_cert: Optional[str] = None,
        response_timeout: float = 30.0,
    ):
        """
        Initialize remote config server.

        Args:
            broker: MQTT broker hostname
            port: MQTT broker port
            username: MQTT username (optional)
            password: MQTT password (optional)
            use_tls: Enable TLS
            tls_ca_cert: Path to CA certificate
            response_timeout: Seconds to wait for response
        """
        self.logger = logging.getLogger(self.__class__.__name__)

        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.tls_ca_cert = tls_ca_cert
        self.response_timeout = response_timeout

        self.client: Optional[mqtt.Client] = None
        self.connected = False

        # Track pending changes
        self.pending_changes: Dict[str, ConfigChange] = {}

        # Callbacks for responses
        self.response_callbacks: Dict[str, Callable] = {}
        self.default_response_callback: Optional[Callable] = None

        # Track all nodes we've seen
        self.known_nodes: Dict[str, Dict] = {}

        # Base topic
        self.topic_base = "gunshot/config"

        # Statistics
        self.stats = {
            "messages_received": 0,
            "changes_sent": 0,
            "responses_received": 0,
            "errors": 0,
        }

    def start(self) -> bool:
        """
        Connect to MQTT broker and start receiving responses.

        Returns:
            True if connected successfully
        """
        if self.connected:
            return True

        try:
            self.client = mqtt.Client(client_id=f"gds_config_server_{int(time.time())}")

            # Set callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message

            # Set credentials
            if self.username:
                self.client.username_pw_set(self.username, self.password)

            # TLS
            if self.use_tls:
                import ssl

                if self.tls_ca_cert:
                    self.client.tls_set(ca_certs=self.tls_ca_cert)
                else:
                    self.client.tls_set()

            self.logger.info(f"Connecting to {self.broker}:{self.port}...")
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()

            return True

        except Exception as e:
            # Intentionally broad: paho connect and SSL setup raise various exceptions
            self.stats["errors"] += 1
            self.logger.error(f"Connection failed: {e}")
            return False

    def stop(self):
        """Disconnect from broker."""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
            self.logger.info("Disconnected from broker")

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False

    def _on_connect(self, client, userdata, flags, rc):
        """Handle connection."""
        if rc == 0:
            self.connected = True
            self.logger.info("Connected to MQTT broker")

            # Subscribe to all response topics
            self.client.subscribe(f"{self.topic_base}/+/status", qos=1)
            self.client.subscribe(f"{self.topic_base}/+/response", qos=1)
            self.logger.info(f"Subscribed to {self.topic_base}/+/response")
        else:
            self.logger.error(f"Connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, rc):
        """Handle disconnection."""
        self.connected = False
        if rc != 0:
            self.logger.warning(f"Unexpected disconnect (code {rc})")

    def _on_message(self, client, userdata, msg):
        """Handle incoming message."""
        self.stats["messages_received"] += 1
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())

            self.logger.debug(f"Received on {topic}: {payload}")

            # Extract node_id from topic
            parts = topic.split("/")
            if len(parts) >= 3:
                node_id = parts[2]

                # Update known nodes
                self.known_nodes[node_id] = {
                    "last_seen": time.time(),
                    "payload": payload,
                }

                # Handle response topic
                if topic.endswith("/response"):
                    self._handle_response(node_id, payload)
                    self.stats["responses_received"] += 1
                elif topic.endswith("/status"):
                    self._handle_status(node_id, payload)

        except json.JSONDecodeError as e:
            self.stats["errors"] += 1
            self.logger.error(f"Invalid JSON: {e}")
        except Exception as e:
            # Intentionally broad: isolate message handler failures from crashing the MQTT loop
            self.stats["errors"] += 1
            self.logger.error(f"Error handling message: {e}")

    def _handle_response(self, node_id: str, payload: Dict):
        """Handle response from node."""
        # Extract change_id if present
        change_id = payload.get("change_id")

        if change_id and change_id in self.pending_changes:
            change = self.pending_changes[change_id]
            change.response_data = payload

            # Update state based on response
            status = payload.get("status")
            if status == "success":
                change.state = ChangeState.ACKNOWLEDGED
                change.acknowledged_at = time.time()

                # Check if immediately confirmed
                if payload.get("result_status") == "confirmed":
                    change.state = ChangeState.CONFIRMED
                    change.confirmed_at = time.time()

            else:
                change.state = ChangeState.FAILED
                change.error_message = payload.get("message", "Unknown error")

        # Call registered callback
        if change_id and change_id in self.response_callbacks:
            callback = self.response_callbacks.pop(change_id)
            try:
                callback(node_id, payload)
            except Exception as e:
                # Intentionally broad: isolate callback failures from crashing the response handler
                self.logger.error(f"Callback error: {e}")
        elif self.default_response_callback:
            try:
                self.default_response_callback(node_id, payload)
            except Exception as e:
                # Intentionally broad: isolate callback failures from crashing the response handler
                self.logger.error(f"Default callback error: {e}")

    def _handle_status(self, node_id: str, payload: Dict):
        """Handle status update from node."""
        status = payload.get("status")

        if status == "rolled_back":
            # Check if there's a pending change for this node
            for change_id, change in self.pending_changes.items():
                if change.node_id == node_id and change.state == ChangeState.ACKNOWLEDGED:
                    change.state = ChangeState.ROLLED_BACK
                    change.error_message = payload.get("message", "Auto-rollback triggered")
                    self.logger.warning(f"Node {node_id} rolled back change {change_id}")

    def set_node_config(
        self,
        node_id: str,
        changes: Dict[str, Any],
        change_id: Optional[str] = None,
        wait_for_response: bool = False,
        timeout: Optional[float] = None,
        callback: Optional[Callable[[str, Dict], None]] = None,
    ) -> Optional[ConfigChange]:
        """
        Send configuration change to a specific node.

        Args:
            node_id: Target node identifier
            changes: Dict of config path -> new value
            change_id: Optional unique identifier (default: auto-generated)
            wait_for_response: Block until response received
            timeout: Response timeout (default: self.response_timeout)
            callback: Optional callback for async response

        Returns:
            ConfigChange object if sent, None if failed
        """
        if not self.connected:
            self.logger.error("Not connected to MQTT broker")
            return None

        change_id = change_id or f"change-{int(time.time() * 1000)}"
        timeout = timeout or self.response_timeout

        change = ConfigChange(
            change_id=change_id,
            node_id=node_id,
            changes=changes,
            state=ChangeState.PENDING,
        )

        self.pending_changes[change_id] = change

        # Build command
        topic = f"{self.topic_base}/{node_id}/set"
        payload = {
            "command": "set_config",
            "change_id": change_id,
            "changes": changes,
            "timestamp": time.time(),
        }

        try:
            self.client.publish(topic, json.dumps(payload), qos=1)
            change.state = ChangeState.SENT
            change.sent_at = time.time()
            self.stats["changes_sent"] += 1
            self.logger.info(f"Sent config change {change_id} to {node_id}")

            # Register callback if provided
            if callback:
                self.response_callbacks[change_id] = callback

            if wait_for_response:
                # Wait for acknowledgment
                result = self._wait_for_response(change_id, timeout)
                if result:
                    return change
                else:
                    change.state = ChangeState.TIMEOUT
                    change.error_message = "Response timeout"
                    return change

            return change

        except Exception as e:
            # Intentionally broad: paho publish can raise OSError, socket errors, etc.
            self.stats["errors"] += 1
            self.logger.error(f"Failed to send config: {e}")
            change.state = ChangeState.FAILED
            change.error_message = str(e)
            return None

    def broadcast_config(
        self,
        changes: Dict[str, Any],
        exclude_nodes: Optional[List[str]] = None,
    ) -> Dict[str, Optional[ConfigChange]]:
        """
        Send configuration change to all known nodes.

        Args:
            changes: Dict of config path -> new value
            exclude_nodes: Optional list of node IDs to skip

        Returns:
            Dict of node_id -> ConfigChange
        """
        results = {}
        exclude_nodes = exclude_nodes or []

        # Use known nodes
        nodes = list(self.known_nodes.keys())

        for node_id in nodes:
            if node_id not in exclude_nodes:
                change = self.set_node_config(node_id, changes)
                results[node_id] = change

        return results

    def get_node_config(
        self,
        node_id: str,
        wait_for_response: bool = True,
        timeout: Optional[float] = None,
    ) -> Optional[Dict]:
        """
        Request current configuration from node.

        Args:
            node_id: Target node
            wait_for_response: Block until response
            timeout: Response timeout

        Returns:
            Config dict if successful, None otherwise
        """
        if not self.connected:
            return None

        topic = f"{self.topic_base}/{node_id}/get"
        request_id = f"req-{int(time.time() * 1000)}"

        payload = {
            "command": "get_config",
            "request_id": request_id,
            "timestamp": time.time(),
        }

        response_data = None

        def on_response(node: str, data: Dict):
            nonlocal response_data
            if data.get("request_id") == request_id:
                response_data = data

        # Register callback
        self.response_callbacks[request_id] = on_response

        try:
            self.client.publish(topic, json.dumps(payload), qos=1)
            self.logger.info(f"Requested config from {node_id}")

            if wait_for_response:
                if self._wait_for_response(request_id, timeout or self.response_timeout):
                    return response_data.get("config") if response_data else None

            return None

        except Exception as e:
            self.logger.error(f"Failed to request config: {e}")
            return None

    def confirm_node_change(
        self,
        node_id: str,
        change_id: str,
    ) -> bool:
        """
        Manually confirm a pending change on a node.

        Returns:
            True if confirmed successfully
        """
        if not self.connected:
            return False

        topic = f"{self.topic_base}/{node_id}/confirm"
        payload = {
            "command": "confirm",
            "change_id": change_id,
            "timestamp": time.time(),
        }

        try:
            self.client.publish(topic, json.dumps(payload), qos=1)
            self.logger.info(f"Sent confirmation for {change_id} to {node_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send confirmation: {e}")
            return False

    def rollback_node(
        self,
        node_id: str,
    ) -> bool:
        """
        Trigger rollback to last known good on a node.

        Returns:
            True if rollback command sent successfully
        """
        if not self.connected:
            return False

        topic = f"{self.topic_base}/{node_id}/rollback"
        payload = {
            "command": "rollback",
            "timestamp": time.time(),
        }

        try:
            self.client.publish(topic, json.dumps(payload), qos=1)
            self.logger.info(f"Sent rollback command to {node_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send rollback: {e}")
            return False

    def _wait_for_response(self, change_id: str, timeout: float) -> bool:
        """
        Wait for response to a change.

        Returns:
            True if response received within timeout
        """
        start = time.time()

        while time.time() - start < timeout:
            if change_id in self.pending_changes:
                change = self.pending_changes[change_id]
                if change.state in (ChangeState.ACKNOWLEDGED, ChangeState.CONFIRMED):
                    return True
                if change.state == ChangeState.FAILED:
                    return True  # Failed is still a response

            time.sleep(0.1)

        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get server statistics."""
        return {
            "connected": self.connected,
            "known_nodes": len(self.known_nodes),
            "pending_changes": len(self.pending_changes),
            **self.stats,
        }

    def get_change_status(self, change_id: str) -> Optional[ConfigChange]:
        """Get status of a pending or completed change."""
        return self.pending_changes.get(change_id)

    def get_known_nodes(self) -> List[Dict]:
        """Get list of known nodes with metadata."""
        nodes = []
        for node_id, data in self.known_nodes.items():
            nodes.append(
                {
                    "node_id": node_id,
                    "last_seen": data["last_seen"],
                    "age_seconds": time.time() - data["last_seen"],
                }
            )
        return sorted(nodes, key=lambda x: x["last_seen"], reverse=True)

    def cleanup_old_changes(self, max_age: float = 3600.0) -> int:
        """
        Remove old completed changes from tracking.

        Args:
            max_age: Maximum age in seconds to keep

        Returns:
            Number of changes removed
        """
        now = time.time()
        to_remove = []

        for change_id, change in self.pending_changes.items():
            if change.state in (ChangeState.CONFIRMED, ChangeState.FAILED, ChangeState.TIMEOUT):
                if change.created_at < now - max_age:
                    to_remove.append(change_id)

        for change_id in to_remove:
            del self.pending_changes[change_id]

        return len(to_remove)
