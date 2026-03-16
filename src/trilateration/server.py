"""TrilaterationServer: MQTT-integrated fusion server for strix parliaments."""

import json
import logging
import threading
import time
from datetime import datetime
from typing import List, Optional

from src.trilateration.engine import TrilaterationEngine
from src.trilateration.models import Detection, TriangulationResult


class TrilaterationServer:
    """
    Main trilateration server that:
    - Subscribes to MQTT detection events
    - Groups detections by time proximity
    - Performs trilateration
    - Publishes results
    """

    def __init__(
        self,
        broker: str,
        port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
        time_window: float = 30.0,
        min_nodes: int = 3,
        max_nodes: int = 10,
        speed_of_sound: float = 343.0,
    ):
        """
        Initialize trilateration server.

        Args:
            broker: MQTT broker address
            port: MQTT broker port
            username: MQTT username (optional)
            password: MQTT password (optional)
            time_window: Maximum time window for grouping detections (seconds)
                        30s allows for thunder at ~10km distance
            min_nodes: Minimum nodes required for trilateration
            max_nodes: Maximum nodes to use (best ones selected)
            speed_of_sound: Initial speed of sound (m/s)
        """
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.time_window = time_window
        self.min_nodes = min_nodes
        self.max_nodes = max_nodes

        self.engine = TrilaterationEngine(speed_of_sound)
        self.client = None
        self.connected = False

        # Detection buffer: timestamp -> list of detections
        self.detection_buffer = []
        self.buffer_lock = threading.Lock()

        # Processing thread
        self.processing_thread = None
        self.running = False

        # Statistics
        self.stats = {
            "detections_received": 0,
            "events_trilaterated": 0,
            "events_failed": 0,
        }

    def connect(self):
        """Connect to MQTT broker."""
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            raise ImportError("paho-mqtt not installed. Run: pip install paho-mqtt")

        self.client = mqtt.Client(client_id=f"trilateration_server_{int(time.time())}")

        # Set callbacks
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        # Set credentials if provided
        if self.username:
            self.client.username_pw_set(self.username, self.password)

        logging.getLogger(__name__).info(
            f"[TrilaterationServer] Connecting to {self.broker}:{self.port}..."
        )
        self.client.connect(self.broker, self.port, keepalive=60)
        self.client.loop_start()

        # Start processing thread
        self.running = True
        self.processing_thread = threading.Thread(target=self._processing_loop)
        self.processing_thread.daemon = True
        self.processing_thread.start()

        lg = logging.getLogger(__name__)
        lg.info("[TrilaterationServer] Server started")
        max_distance = self.time_window * self.engine.speed_of_sound / 1000
        lg.info(
            f"  Time window: {self.time_window}s "
            f"(allows events up to ~{max_distance:.1f}km away)"
        )
        lg.info(f"  Min nodes: {self.min_nodes}")
        lg.info(f"  Speed of sound: {self.engine.speed_of_sound} m/s")

    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connected."""
        if rc == 0:
            self.connected = True
            logging.getLogger(__name__).info("[TrilaterationServer] Connected to MQTT broker")

            # Subscribe to all detection topics
            self.client.subscribe("gunshot/detections", qos=1)
            self.client.subscribe("gunshot/+/detections", qos=1)

            logging.getLogger(__name__).info("[TrilaterationServer] Subscribed to detection topics")
        else:
            logging.getLogger(__name__).error(
                f"[TrilaterationServer] Connection failed with code {rc}"
            )

    def _on_message(self, client, userdata, msg):
        """Callback when detection message received."""
        try:
            payload = json.loads(msg.payload.decode())
            detection = Detection.from_mqtt_payload(payload)

            # Add to buffer
            with self.buffer_lock:
                self.detection_buffer.append(detection)
                self.stats["detections_received"] += 1

            logging.getLogger(__name__).info(
                f"[TrilaterationServer] Detection from {detection.node_id} "
                f"at {detection.timestamp:.6f}s (buffer: {len(self.detection_buffer)})"
            )

        except Exception:
            logging.getLogger(__name__).exception("[TrilaterationServer] Error processing message")

    def _processing_loop(self):
        """Background loop to process detections."""
        logging.getLogger(__name__).info("[TrilaterationServer] Processing loop started")

        while self.running:
            try:
                # Process buffer every second
                time.sleep(1.0)

                with self.buffer_lock:
                    if len(self.detection_buffer) < self.min_nodes:
                        continue

                    # Prune stale detections (Fix 2: prevent unbounded growth)
                    if self.detection_buffer:
                        newest = max(d.timestamp for d in self.detection_buffer)
                        cutoff = newest - self.time_window * 2
                        self.detection_buffer = [
                            d for d in self.detection_buffer if d.timestamp >= cutoff
                        ]

                    # Find groups and copy out — lock released before processing (Fix 1)
                    groups_to_process = list(self._find_detection_groups())

                if not groups_to_process:
                    continue

                logging.getLogger(__name__).info(
                    f"\n[TrilaterationServer] Found {len(groups_to_process)} detection group(s)"
                )

                # Process without holding buffer_lock to avoid deadlock
                for group in groups_to_process:
                    self._process_group(group)

            except Exception:
                logging.getLogger(__name__).exception(
                    "[TrilaterationServer] Error in processing loop"
                )

    def _find_detection_groups(self) -> List[List[Detection]]:
        """
        Find groups of detections that are close in time.

        Uses a sliding window approach to find clusters.
        """
        if not self.detection_buffer:
            return []

        # Sort by timestamp
        sorted_detections = sorted(self.detection_buffer, key=lambda d: d.timestamp)

        groups = []
        used_indices = set()

        for i, detection in enumerate(sorted_detections):
            if i in used_indices:
                continue

            # Find all detections within time window
            group = [detection]
            group_node_ids = {detection.node_id}  # Fix 3: O(1) membership checks
            used_indices.add(i)

            for j, other in enumerate(sorted_detections[i + 1 :], start=i + 1):
                if j in used_indices:
                    continue

                time_diff = abs(other.timestamp - detection.timestamp)

                if time_diff <= self.time_window:
                    # Same node shouldn't trigger twice in same window
                    if other.node_id not in group_node_ids:
                        group.append(other)
                        group_node_ids.add(other.node_id)
                        used_indices.add(j)
                else:
                    # Outside time window, stop searching
                    break

            # Only keep groups with enough nodes
            if len(group) >= self.min_nodes:
                groups.append(group)

        return groups

    def _process_group(self, detections: List[Detection]):
        """
        Process a group of detections through trilateration.
        """
        lg = logging.getLogger(__name__)
        lg.info(f"\n[TrilaterationServer] Processing group of {len(detections)} detections:")
        for d in detections:
            lg.info(f"  - {d.node_id}: {d.timestamp:.6f}s ({d.latitude:.4f}, {d.longitude:.4f})")

        # Select best nodes if we have too many
        if len(detections) > self.max_nodes:
            detections = self._select_best_nodes(detections)
            lg.info(f"  Selected best {len(detections)} nodes")

        # Update speed of sound if temperature data available
        # (In real deployment, get from environmental sensors)
        # For now, use default

        # Perform trilateration
        result = self.engine.trilaterate(detections)

        if result:
            self.stats["events_trilaterated"] += 1
            lg.info(f"\n{'='*60}")
            lg.info("✅ TRILATERATION SUCCESS")
            lg.info(f"{'='*60}")
            lg.info(f"Event Type: {result.event_type}")
            lg.info(
                f"Location: ({result.latitude:.6f}, {result.longitude:.6f}, {result.altitude:.1f}m)"
            )
            lg.info(f"Timestamp: {datetime.fromtimestamp(result.timestamp).isoformat()}")
            lg.info(f"Confidence: {result.confidence:.2%}")
            lg.info(f"Nodes: {result.num_nodes} ({', '.join(result.contributing_nodes)})")
            lg.info(f"Time Window: {result.time_window:.3f}s")
            lg.info(f"Geometry Score: {result.geometry_score:.2f}")
            lg.info(f"Residual Error: {result.residual_error:.1f}m")
            lg.info(f"{'='*60}\n")

            # Publish result
            self._publish_result(result)

            # Remove processed detections from buffer
            with self.buffer_lock:
                node_ids = {d.node_id for d in detections}
                self.detection_buffer = [
                    d
                    for d in self.detection_buffer
                    if d.node_id not in node_ids or abs(d.timestamp - result.timestamp) > 1.0
                ]
        else:
            self.stats["events_failed"] += 1
            lg.warning("[TrilaterationServer] Trilateration failed for this group")

    def _select_best_nodes(self, detections: List[Detection]) -> List[Detection]:
        """
        Select best nodes for trilateration if we have too many.

        Criteria:
        - Highest confidence
        - Best geometric diversity
        """
        # Sort by confidence
        sorted_detections = sorted(detections, key=lambda d: d.confidence, reverse=True)

        # Take top max_nodes
        return sorted_detections[: self.max_nodes]

    def _publish_result(self, result: TriangulationResult):
        """Publish trilateration result to MQTT."""
        if not self.connected:
            return

        topic = "gunshot/trilateration/results"
        payload = json.dumps(result.to_dict())

        self.client.publish(topic, payload, qos=1)
        logging.getLogger(__name__).info(f"[TrilaterationServer] Published result to {topic}")

    def get_stats(self) -> dict:
        """Get server statistics."""
        return {
            **self.stats,
            "buffer_size": len(self.detection_buffer),
            "connected": self.connected,
        }

    def disconnect(self):
        """Disconnect from broker."""
        self.running = False

        if self.processing_thread:
            self.processing_thread.join(timeout=2.0)

        if self.client:
            self.client.loop_stop()
            self.client.disconnect()

        logging.getLogger(__name__).info("\n[TrilaterationServer] Statistics:")
        logging.getLogger(__name__).info(
            f"  Detections received: {self.stats['detections_received']}"
        )
        logging.getLogger(__name__).info(
            f"  Events trilaterated: {self.stats['events_trilaterated']}"
        )
        logging.getLogger(__name__).info(f"  Events failed: {self.stats['events_failed']}")
