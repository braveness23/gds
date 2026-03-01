"""Remote configuration client for GDS nodes.

Receives configuration commands from central server via MQTT,
applies them safely with automatic rollback protection.
"""

import json
import logging
import time
import threading
from typing import Any, Callable, Dict, Optional
from dataclasses import dataclass

import paho.mqtt.client as mqtt

from src.config.config import Config
from src.core.event_bus import EventBus, Event, EventType
from src.remote_config.manager import ConfigManager, ConfigChangeResult
from src.remote_config.safety import ValidationResult


@dataclass
class RemoteConfigStatus:
    """Status of remote configuration client."""

    connected: bool
    subscribed: bool
    last_message_time: Optional[float]
    pending_changes: int
    last_error: Optional[str]


class RemoteConfigClient:
    """
    Client that receives remote configuration commands from central server.

    Topic Structure:
    - gunshot/config/{node_id}/set      - Receive configuration changes
    - gunshot/config/{node_id}/get      - Receive config dump requests
    - gunshot/config/{node_id}/status   - Send status updates
    - gunshot/config/{node_id}/response - Send command responses

    Message Format:
    {
        "command": "set_config" | "get_config" | "confirm" | "rollback",
        "change_id": "unique-id",
        "changes": {"path.to.key": "value"},  # for set_config
        "timestamp": 1234567890.0
    }
    """

    def __init__(
        self,
        config: Config,
        node_id: Optional[str] = None,
        event_bus: Optional[EventBus] = None,
        config_manager: Optional[ConfigManager] = None,
        health_check_callback: Optional[Callable[[], bool]] = None,
        test_connection_callback: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ):
        """
        Initialize remote config client.

        Args:
            config: Config instance to manage
            node_id: Node identifier (default from config)
            event_bus: Optional event bus for publishing events
            config_manager: Optional pre-configured ConfigManager
            health_check_callback: Function to check health
            test_connection_callback: Function to test MQTT connections
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config = config
        self.node_id = node_id or config.get("system.node_id", "unknown")
        self.event_bus = event_bus

        # Initialize config manager if not provided
        if config_manager:
            self.config_manager = config_manager
        else:
            self.config_manager = ConfigManager(
                config=config,
                health_check_callback=health_check_callback,
                test_connection_callback=test_connection_callback,
            )

        # MQTT settings
        self.mqtt_config = self._load_mqtt_config()
        self.client: Optional[mqtt.Client] = None
        self.connected = False
        self.subscribed = False

        # Topic paths
        self.topic_base = f"gunshot/config/{self.node_id}"
        self.topic_set = f"{self.topic_base}/set"
        self.topic_get = f"{self.topic_base}/get"
        self.topic_status = f"{self.topic_base}/status"
        self.topic_response = f"{self.topic_base}/response"

        # Background threads
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._reconnect_thread: Optional[threading.Thread] = None

        # Statistics
        self._last_message_time: Optional[float] = None
        self._messages_received = 0
        self._messages_processed = 0
        self._errors = 0

        # Track connection failures for backoff
        self._connect_failures = 0
        self._last_connect_attempt: float = 0
        self._max_backoff = 300  # 5 minutes max

    def _load_mqtt_config(self) -> Dict[str, Any]:
        """Load MQTT configuration from config file."""
        # Use remote_config.mqtt settings if available, fall back to output.mqtt
        return {
            "broker": self.config.get(
                "remote_config.mqtt.broker", self.config.get("output.mqtt.broker", "localhost")
            ),
            "port": self.config.get(
                "remote_config.mqtt.port", self.config.get("output.mqtt.port", 1883)
            ),
            "username": self.config.get("remote_config.mqtt.username")
            or self.config.get("output.mqtt.username"),
            "password": self.config.get("remote_config.mqtt.password")
            or self.config.get("output.mqtt.password"),
            "base_topic": self.config.get("remote_config.mqtt.base_topic", "gunshot/config"),
            "enabled": self.config.get("remote_config.enabled", False),
        }

    def start(self) -> bool:
        """
        Start the remote config client.

        Returns:
            True if started successfully, False otherwise
        """
        if self._running:
            return True

        if not self.mqtt_config["enabled"]:
            self.logger.info("Remote config is disabled in configuration")
            return False

        self._running = True

        # Start MQTT client
        if not self._connect():
            # Will retry in background
            self._start_reconnect_thread()

        # Start monitor thread for pending changes
        self._monitor_thread = threading.Thread(target=self._monitor_loop)
        self._monitor_thread.daemon = True
        self._monitor_thread.start()

        self.logger.info(f"Remote config client started for node {self.node_id}")
        return True

    def stop(self):
        """Stop the remote config client."""
        self._running = False

        # Disconnect MQTT
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()

        # Wait for threads
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2.0)

        self.connected = False
        self.logger.info("Remote config client stopped")

    def _connect(self) -> bool:
        """Connect to MQTT broker."""
        try:
            # Check if we should back off
            if self._connect_failures > 0:
                backoff = min(2**self._connect_failures, self._max_backoff)
                elapsed = time.time() - self._last_connect_attempt
                if elapsed < backoff:
                    self.logger.debug(f"Waiting {backoff - elapsed:.1f}s before reconnect...")
                    return False

            self._last_connect_attempt = time.time()

            # Create client
            self.client = mqtt.Client(client_id=f"gds_config_{self.node_id}_{int(time.time())}")

            # Set up callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message

            # Set credentials if provided
            username = self.mqtt_config.get("username")
            password = self.mqtt_config.get("password")
            if username:
                self.client.username_pw_set(username, password)
                self.logger.debug("MQTT credentials set")

            # Enable TLS if configured (inherited from output.mqtt)
            if self.config.get("output.mqtt.use_tls", False):
                import ssl

                ca_cert = self.config.get("output.mqtt.tls_ca_cert")
                if ca_cert:
                    self.client.tls_set(ca_certs=ca_cert)
                else:
                    self.client.tls_set()

            broker = self.mqtt_config["broker"]
            port = self.mqtt_config["port"]

            self.logger.info(f"Connecting to MQTT broker at {broker}:{port}...")
            self.client.connect(broker, port, keepalive=60)
            self.client.loop_start()

            # Reset failure count on success
            self._connect_failures = 0

            return True

        except Exception as e:
            # Intentionally broad: paho connect and SSL setup raise various exceptions
            self._connect_failures += 1
            self._errors += 1
            self.logger.error(f"MQTT connection failed: {e}")
            return False

    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connected to MQTT."""
        if rc == 0:
            self.connected = True
            self.logger.info("Connected to MQTT broker")

            # Subscribe to command topics
            try:
                self.client.subscribe(self.topic_set, qos=1)
                self.client.subscribe(self.topic_get, qos=1)
                self.client.subscribe(f"{self.topic_base}/confirm", qos=1)
                self.client.subscribe(f"{self.topic_base}/rollback", qos=1)
                self.subscribed = True
                self.logger.info(f"Subscribed to config topics: {self.topic_base}/+")

                # Publish online status
                self._publish_status("online", "Config client connected")

            except Exception as e:
                self.logger.error(f"Failed to subscribe: {e}")
        else:
            self.connected = False
            self.logger.error(f"MQTT connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, rc):
        """Callback when disconnected from MQTT."""
        self.connected = False
        self.subscribed = False

        if rc != 0:
            self.logger.warning(f"Unexpected disconnect (code {rc})")
            self._start_reconnect_thread()

    def _on_message(self, client, userdata, msg):
        """Callback when message received."""
        self._messages_received += 1
        self._last_message_time = time.time()

        try:
            payload = json.loads(msg.payload.decode())
            topic = msg.topic

            self.logger.debug(f"Received message on {topic}: {payload}")

            # Route to appropriate handler
            if topic.endswith("/set"):
                self._handle_set_config(payload)
            elif topic.endswith("/get"):
                self._handle_get_config(payload)
            elif topic.endswith("/confirm"):
                self._handle_confirm(payload)
            elif topic.endswith("/rollback"):
                self._handle_rollback(payload)
            else:
                self.logger.warning(f"Unknown topic: {topic}")

        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON payload: {e}")
            self._send_error_response("invalid_json", f"Invalid JSON: {e}")
        except Exception as e:
            # Intentionally broad: isolate message handler failures from crashing the MQTT loop
            self.logger.exception(f"Error processing message: {e}")
            self._send_error_response("processing_error", str(e))

    def _handle_set_config(self, payload: Dict[str, Any]):
        """
        Handle set_config command.

        Payload format:
        {
            "command": "set_config",
            "change_id": "unique-id",
            "changes": {"path.to.key": "value"},
            "force": false,  # optional
            "timeout": 30    # optional, override default rollback timeout
        }
        """
        if payload.get("command") != "set_config":
            self._send_error_response("invalid_command", "Expected command: set_config")
            return

        change_id = payload.get("change_id")
        changes = payload.get("changes", {})
        force = payload.get("force", False)
        timeout = payload.get("timeout")

        if not change_id:
            self._send_error_response("missing_change_id", "change_id is required")
            return

        if not changes:
            self._send_error_response("missing_changes", "changes dict is required")
            return

        self.logger.info(f"Received set_config command: {change_id}")

        # Temporarily update rollback timeout if specified
        original_timeout = None
        if timeout and hasattr(self.config_manager, "rollback_timeout"):
            original_timeout = self.config_manager.rollback_timeout
            self.config_manager.rollback_timeout = timeout

        try:
            # Apply changes through config manager
            result = self.config_manager.apply_changes(
                changes=changes,
                change_id=change_id,
                force=force,
            )

            # Send response
            self._send_config_response(result, change_id)

            # Publish event if successful
            if result.success and self.event_bus:
                event = Event(
                    event_type=EventType.CONFIG,
                    timestamp=time.time(),
                    source=self.node_id,
                    data={
                        "change_id": change_id,
                        "changes": changes,
                        "result": "success",
                    },
                )
                self.event_bus.publish(event)

        finally:
            # Restore original timeout
            if original_timeout:
                self.config_manager.rollback_timeout = original_timeout

    def _handle_get_config(self, payload: Dict[str, Any]):
        """
        Handle get_config command.

        Returns current configuration (excluding sensitive fields).
        """
        self.logger.info("Received get_config command")

        # Get current config, excluding sensitive fields
        config_data = self._sanitize_config(self.config.data)

        request_id = payload.get("request_id", "unknown")

        response = {
            "command": "get_config_response",
            "request_id": request_id,
            "node_id": self.node_id,
            "timestamp": time.time(),
            "config": config_data,
            "status": "success",
        }

        self._publish_response(response)

    def _handle_confirm(self, payload: Dict[str, Any]):
        """Handle manual confirmation of pending change."""
        change_id = payload.get("change_id")

        if self.config_manager.pending_change:
            if change_id and self.config_manager.pending_change.change_id != change_id:
                self._send_error_response(
                    "wrong_change_id",
                    f"Expected {self.config_manager.pending_change.change_id}, got {change_id}",
                )
                return

            self.config_manager.confirm_current_config()

            response = {
                "command": "confirm_response",
                "change_id": change_id,
                "status": "confirmed",
                "timestamp": time.time(),
            }
            self._publish_response(response)
        else:
            self._send_error_response("no_pending_change", "No pending change to confirm")

    def _handle_rollback(self, payload: Dict[str, Any]):
        """Handle rollback command."""
        self.logger.info("Received rollback command")

        result = self.config_manager.rollback_to_last_known_good()

        response = {
            "command": "rollback_response",
            "status": "rolled_back" if not result.success else "failed",
            "message": result.message,
            "timestamp": time.time(),
        }
        self._publish_response(response)

    def _send_config_response(self, result: ConfigChangeResult, change_id: str):
        """Send response for config change."""
        response = {
            "command": "set_config_response",
            "change_id": change_id,
            "status": "success" if result.success else "failed",
            "result_status": result.status.value,
            "message": result.message,
            "timestamp": time.time(),
        }

        if result.validation_result:
            response["validation"] = {
                "status": result.validation_result.status.value,
                "risk_level": result.validation_result.risk_level.value,
                "warnings": result.validation_result.warnings,
                "errors": result.validation_result.errors,
            }

        if result.error:
            response["error"] = result.error

        if result.rollback_reason:
            response["rollback_reason"] = result.rollback_reason

        self._publish_response(response)

    def _send_error_response(self, error_code: str, message: str):
        """Send error response."""
        response = {
            "command": "error",
            "error_code": error_code,
            "message": message,
            "timestamp": time.time(),
        }
        self._publish_response(response)

    def _publish_response(self, response: Dict[str, Any]):
        """Publish response to response topic."""
        if not self.connected or not self.client:
            self.logger.warning("Cannot publish response - not connected")
            return

        try:
            payload = json.dumps(response)
            self.client.publish(self.topic_response, payload, qos=1)
            self._messages_processed += 1
        except Exception as e:
            # Intentionally broad: paho publish can raise OSError, socket errors, etc.
            self.logger.error(f"Failed to publish response: {e}")

    def _publish_status(self, status: str, message: str = ""):
        """Publish status update."""
        if not self.connected or not self.client:
            return

        payload = {
            "node_id": self.node_id,
            "status": status,
            "message": message,
            "timestamp": time.time(),
            "config_status": self.config_manager.get_status() if self.config_manager else {},
        }

        try:
            self.client.publish(self.topic_status, json.dumps(payload), qos=0, retain=True)
        except Exception as e:
            # Intentionally broad: paho publish can raise OSError, socket errors, etc.
            self.logger.error(f"Failed to publish status: {e}")

    def _sanitize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove sensitive fields from config for transmission.
        """
        # Deep copy to avoid modifying original
        import copy

        safe_config = copy.deepcopy(config)

        # Remove passwords
        def remove_passwords(d: dict):
            for key in list(d.keys()):
                if "password" in key.lower():
                    d[key] = "***REDACTED***"
                elif isinstance(d[key], dict):
                    remove_passwords(d[key])

        remove_passwords(safe_config)

        return safe_config

    def _monitor_loop(self):
        """Background loop to check pending changes and health."""
        check_interval = 1.0
        status_interval = 60.0
        last_status = 0.0

        while self._running:
            try:
                time.sleep(check_interval)

                # Check if any pending changes need rollback
                if self.config_manager:
                    result = self.config_manager.check_and_rollback_if_needed()
                    if result:
                        self.logger.info(f"Automatic rollback occurred: {result.message}")
                        self._publish_status("rolled_back", result.message)

                # Periodic status publish
                now = time.time()
                if now - last_status > status_interval:
                    self._publish_status("alive")
                    last_status = now

            except Exception as e:
                # Intentionally broad: isolate monitor loop from unexpected failures in callbacks
                self.logger.error(f"Error in monitor loop: {e}")

    def _start_reconnect_thread(self):
        """Start background reconnect thread."""
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            return

        def reconnect_loop():
            while self._running and not self.connected:
                if self._connect():
                    break
                time.sleep(min(2**self._connect_failures, self._max_backoff))

        self._reconnect_thread = threading.Thread(target=reconnect_loop)
        self._reconnect_thread.daemon = True
        self._reconnect_thread.start()

    def get_status(self) -> RemoteConfigStatus:
        """Get current client status."""
        return RemoteConfigStatus(
            connected=self.connected,
            subscribed=self.subscribed,
            last_message_time=self._last_message_time,
            pending_changes=1 if self.config_manager and self.config_manager.pending_change else 0,
            last_error=None,
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        return {
            "connected": self.connected,
            "running": self._running,
            "messages_received": self._messages_received,
            "messages_processed": self._messages_processed,
            "errors": self._errors,
            "connect_failures": self._connect_failures,
            "last_message_time": self._last_message_time,
        }

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False
