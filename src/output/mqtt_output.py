"""MQTT output for publishing detection events to broker.

This module enables distributed coordination by publishing local detection
events to a central MQTT broker where they can be consumed by trilateration
servers, dashboards, and other nodes.
"""

import json
import time
import threading
from typing import Optional, Dict, Any
from core.event_bus import Event, EventType


class MQTTOutputNode:
    """
    Publish detection events to MQTT broker.

    Architecture:
    - Subscribes to local event bus (process-internal)
    - Publishes events to MQTT broker (network)
    - Each node has unique node_id
    - Central broker receives from all nodes
    """

    def __init__(self,
                 broker: str,
                 port: int = 1883,
                 topic: str = "gunshot/detections",
                 node_id: str = "gunshot_node",
                 qos: int = 1,
                 username: Optional[str] = None,
                 password: Optional[str] = None,
                 use_tls: bool = False,
                 event_bus=None,
                 gps_reader=None,
                 env_sensor=None):
        """
        Initialize MQTT output.

        Args:
            broker: MQTT broker hostname/IP
            port: MQTT broker port (default 1883, or 8883 for TLS)
            topic: Base topic for publishing
            node_id: Unique identifier for this node
            qos: Quality of Service (0=fire-and-forget, 1=at-least-once, 2=exactly-once)
            username: MQTT username (optional)
            password: MQTT password (optional)
            event_bus: Local event bus to subscribe to
            gps_reader: GPS reader for location data (optional)
            env_sensor: Environmental sensor for conditions (optional)
        """
        self.broker = broker
        self.port = port
        self.base_topic = topic
        self.node_id = node_id
        self.qos = qos
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.event_bus = event_bus
        self.gps_reader = gps_reader
        self.env_sensor = env_sensor

        self.client = None
        self.connected = False
        self.reconnect_thread = None
        self.running = False

        # Statistics
        self.messages_published = 0
        self.messages_failed = 0
        self.last_publish_time = None

    def connect(self):
        """Connect to MQTT broker."""
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            raise ImportError("paho-mqtt not installed. Run: pip install paho-mqtt")

        self.client = mqtt.Client(client_id=f"{self.node_id}_{int(time.time())}")

        # Increase inflight message limit for high-rate detections
        self.client.max_inflight_messages_set(200)  # Default is 20, increase for burst events
        self.client.max_queued_messages_set(1000)   # Queue more messages in memory

        # Set callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish = self._on_publish

        # Set credentials if provided
        if self.username:
            self.client.username_pw_set(self.username, self.password)

        # Enable TLS if requested
        if self.use_tls:
            import ssl
            self.client.tls_set(cert_reqs=ssl.CERT_NONE)
            self.client.tls_insecure_set(True)

        try:
            print(f"[MQTTOutput] Connecting to {self.broker}:{self.port}...")
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()
            self.running = True

            # Subscribe to local event bus
            if self.event_bus:
                self.event_bus.subscribe(EventType.DETECTION, self._on_detection_event)
                self.event_bus.subscribe(EventType.HEALTH, self._on_health_event)
                self.event_bus.subscribe(EventType.SYSTEM, self._on_system_event)

            print(f"[MQTTOutput] MQTT output initialized for node '{self.node_id}'")

        except Exception as e:
            print(f"[MQTTOutput] Connection failed: {e}")
            self._start_reconnect_thread()

    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connected to broker."""
        if rc == 0:
            self.connected = True
            print(f"[MQTTOutput] Connected to MQTT broker at {self.broker}:{self.port}")

            # Publish online status
            self._publish_status("online")
        else:
            self.connected = False
            print(f"[MQTTOutput] Connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, rc):
        """Callback when disconnected from broker."""
        self.connected = False
        if rc != 0:
            print(f"[MQTTOutput] Unexpected disconnection (code {rc}), will retry...")
            self._start_reconnect_thread()
        else:
            print(f"[MQTTOutput] Disconnected from broker")

    def _on_publish(self, client, userdata, mid):
        """Callback when message is published."""
        self.last_publish_time = time.time()

    def _start_reconnect_thread(self):
        """Start background thread to reconnect."""
        if self.reconnect_thread and self.reconnect_thread.is_alive():
            return  # Already trying to reconnect

        self.reconnect_thread = threading.Thread(target=self._reconnect_loop)
        self.reconnect_thread.daemon = True
        self.reconnect_thread.start()

    def _reconnect_loop(self):
        """Background loop to reconnect."""
        while self.running and not self.connected:
            try:
                print(f"[MQTTOutput] Attempting to reconnect...")
                self.client.reconnect()
                time.sleep(5)  # Wait between attempts
            except Exception as e:
                print(f"[MQTTOutput] Reconnect failed: {e}")
                time.sleep(5)

    def _on_detection_event(self, event: Event):
        """Handle detection event from local event bus."""
        if not self.connected:
            self.messages_failed += 1
            return

        # Build message payload
        message = self._build_detection_message(event)

        # Publish to multiple topics for different consumers
        topics = [
            f"{self.base_topic}",                      # All detections
            f"gunshot/{self.node_id}/detections",      # This node's detections
        ]

        for topic in topics:
            self._publish(topic, message)

    def _on_health_event(self, event: Event):
        """Handle health event from local event bus."""
        if not self.connected:
            return

        message = {
            "node_id": self.node_id,
            "timestamp": event.timestamp,
            "type": "health",
            "data": event.data
        }

        topic = f"gunshot/{self.node_id}/health"
        self._publish(topic, message)

    def _on_system_event(self, event: Event):
        """Handle system event from local event bus."""
        if not self.connected:
            return

        message = {
            "node_id": self.node_id,
            "timestamp": event.timestamp,
            "type": "system",
            "data": event.data
        }

        topic = f"gunshot/{self.node_id}/status"
        self._publish(topic, message)

    def _build_detection_message(self, event: Event) -> Dict[str, Any]:
        """Build detection message with all available data."""
        message = {
            "node_id": self.node_id,
            "timestamp": event.timestamp,
            "detection": event.data
        }

        # Add GPS location if available
        if self.gps_reader:
            try:
                position = self.gps_reader.get_position()
                if position:
                    message["location"] = {
                        "latitude": position.latitude,
                        "longitude": position.longitude,
                        "altitude": position.altitude,
                        "fix_quality": position.fix_quality,
                        "satellites": position.satellites
                    }
            except Exception as e:
                print(f"[MQTTOutput] Failed to get GPS position: {e}")

        # Add environmental data if available
        if self.env_sensor:
            try:
                env_data = self.env_sensor.get_data()
                if env_data:
                    message["environment"] = {
                        "temperature": env_data.temperature,
                        "humidity": env_data.humidity,
                        "pressure": env_data.pressure
                    }
            except Exception as e:
                print(f"[MQTTOutput] Failed to get environmental data: {e}")

        return message

    def _publish(self, topic: str, message: Dict[str, Any]):
        """Publish message to MQTT topic."""
        try:
            payload = json.dumps(message)
            result = self.client.publish(topic, payload, qos=self.qos)

            if result.rc == 0:
                self.messages_published += 1
            else:
                self.messages_failed += 1
                print(f"[MQTTOutput] Publish failed to {topic} (rc={result.rc})")
            
            # Check if message queue is getting full
            if result.rc == 1:  # MQTT_ERR_NOMEM - queue full
                print(f"[MQTTOutput] WARNING: Message queue full! Messages being dropped.")

        except Exception as e:
            self.messages_failed += 1
            print(f"[MQTTOutput] Error publishing to {topic}: {e}")

    def _publish_status(self, status: str):
        """Publish node status."""
        message = {
            "node_id": self.node_id,
            "timestamp": time.time(),
            "status": status,
            "uptime": time.time() - self.start_time if hasattr(self, 'start_time') else 0
        }

        topic = f"gunshot/{self.node_id}/status"
        self._publish(topic, message)

    def disconnect(self):
        """Disconnect from broker."""
        self.running = False

        if self.connected:
            self._publish_status("offline")

        if self.client:
            self.client.loop_stop()
            self.client.disconnect()

        print(f"[MQTTOutput] Disconnected (published {self.messages_published} messages, "
              f"{self.messages_failed} failed)")

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics."""
        return {
            "connected": self.connected,
            "messages_published": self.messages_published,
            "messages_failed": self.messages_failed,
            "last_publish_time": self.last_publish_time
        }


class MQTTFleetCoordinator:
    """
    Subscribe to MQTT broker and coordinate fleet.

    This would run on a central server to:
    - Collect detections from all nodes
    - Perform trilateration
    - Monitor fleet health
    - Send commands to nodes
    """

    def __init__(self,
                 broker: str,
                 port: int = 1883,
                 username: Optional[str] = None,
                 password: Optional[str] = None,
                 use_tls: bool = False):
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls

        self.client = None
        self.connected = False
        self.detection_callback = None
        self.health_callback = None

        # Track nodes
        self.active_nodes = {}  # node_id -> last_seen_time
        self.detections = []    # List of all detections

    def connect(self):
        """Connect to MQTT broker and subscribe to topics."""
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            raise ImportError("paho-mqtt not installed. Run: pip install paho-mqtt")

        self.client = mqtt.Client(client_id=f"fleet_coordinator_{int(time.time())}")

        # Set callbacks
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        # Set credentials if provided
        if self.username:
            self.client.username_pw_set(self.username, self.password)

        # Enable TLS if requested
        if self.use_tls:
            import ssl
            self.client.tls_set(cert_reqs=ssl.CERT_NONE)
            self.client.tls_insecure_set(True)

        print(f"[FleetCoordinator] Connecting to {self.broker}:{self.port}...")
        self.client.connect(self.broker, self.port, keepalive=60)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connected."""
        if rc == 0:
            self.connected = True
            print(f"[FleetCoordinator] Connected to MQTT broker")

            # Subscribe to all detection topics
            self.client.subscribe("gunshot/detections", qos=1)
            self.client.subscribe("gunshot/+/detections", qos=1)
            self.client.subscribe("gunshot/+/health", qos=1)
            self.client.subscribe("gunshot/+/status", qos=1)

            print(f"[FleetCoordinator] Subscribed to fleet topics")
        else:
            print(f"[FleetCoordinator] Connection failed with code {rc}")

    def _on_message(self, client, userdata, msg):
        """Callback when message received."""
        try:
            payload = json.loads(msg.payload.decode())
            topic_parts = msg.topic.split('/')

            # Update active nodes
            if 'node_id' in payload:
                self.active_nodes[payload['node_id']] = time.time()

            # Route to appropriate handler
            if 'detections' in msg.topic:
                self._handle_detection(payload)
            elif 'health' in msg.topic:
                self._handle_health(payload)
            elif 'status' in msg.topic:
                self._handle_status(payload)

        except Exception as e:
            print(f"[FleetCoordinator] Error processing message: {e}")

    def _handle_detection(self, payload: Dict[str, Any]):
        """Handle detection from a node."""
        self.detections.append(payload)

        print(f"[FleetCoordinator] Detection from {payload.get('node_id', 'unknown')} "
              f"at {payload.get('timestamp', 0):.3f}s")

        if self.detection_callback:
            self.detection_callback(payload)

    def _handle_health(self, payload: Dict[str, Any]):
        """Handle health update from a node."""
        if self.health_callback:
            self.health_callback(payload)

    def _handle_status(self, payload: Dict[str, Any]):
        """Handle status update from a node."""
        node_id = payload.get('node_id')
        status = payload.get('status')

        if status == 'online':
            print(f"[FleetCoordinator] Node {node_id} came online")
        elif status == 'offline':
            print(f"[FleetCoordinator] Node {node_id} went offline")

    def set_detection_callback(self, callback):
        """Set callback for detection events."""
        self.detection_callback = callback

    def set_health_callback(self, callback):
        """Set callback for health events."""
        self.health_callback = callback

    def get_active_nodes(self, timeout: float = 60.0) -> list:
        """Get list of nodes seen recently."""
        current_time = time.time()
        active = []

        for node_id, last_seen in self.active_nodes.items():
            if current_time - last_seen < timeout:
                active.append({
                    'node_id': node_id,
                    'last_seen': last_seen,
                    'age': current_time - last_seen
                })

        return active

    def get_recent_detections(self, window: float = 10.0) -> list:
        """Get detections within time window."""
        current_time = time.time()
        cutoff = current_time - window

        recent = [d for d in self.detections if d.get('timestamp', 0) > cutoff]
        return sorted(recent, key=lambda x: x.get('timestamp', 0))

    def disconnect(self):
        """Disconnect from broker."""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()

        print(f"[FleetCoordinator] Disconnected (received {len(self.detections)} detections)")
