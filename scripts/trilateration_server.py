#!/usr/bin/env python3
"""
Trilateration Server for strix

This server:
- Subscribes to detection events from all nodes via MQTT
- Groups detections by time proximity (configurable window)
- Performs TDOA (Time Difference of Arrival) trilateration
- Calculates sound source location
- Publishes results back to MQTT

Supports both short-range events (gunshots) and long-range events (thunder).
"""

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class Detection:
    """Detection event from a node."""

    node_id: str
    timestamp: float
    latitude: float
    longitude: float
    altitude: float
    confidence: float
    detector_type: str

    @classmethod
    def from_mqtt_payload(cls, payload: dict) -> "Detection":
        """Create Detection from MQTT message."""
        location = payload.get("location", {})
        detection_data = payload.get("detection", {})

        return cls(
            node_id=payload["node_id"],
            timestamp=payload["timestamp"],
            latitude=location.get("latitude", 0.0),
            longitude=location.get("longitude", 0.0),
            altitude=location.get("altitude", 0.0),
            confidence=detection_data.get("confidence", 0.0),
            detector_type=detection_data.get("detector_type", "unknown"),
        )


@dataclass
class TriangulationResult:
    """Result of trilateration calculation."""

    timestamp: float  # Average timestamp of contributing detections
    latitude: float
    longitude: float
    altitude: float
    confidence: float  # Overall confidence (0-1)
    num_nodes: int
    contributing_nodes: List[str]
    event_type: str  # 'gunshot', 'thunder', 'sonic_boom', etc.
    time_window: float  # Time span of detections (seconds)
    geometry_score: float  # Quality of node geometry (0-1)
    residual_error: float  # RMS error of solution (meters)
    speed_of_sound: float  # Calculated or assumed (m/s)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class TrilaterationEngine:
    """
    Core trilateration algorithm using Time Difference of Arrival (TDOA).

    This implements multilateration using the differences in arrival times
    between sensors to calculate the position of the sound source.
    """

    def __init__(self, speed_of_sound: float = 343.0):
        """
        Initialize trilateration engine.

        Args:
            speed_of_sound: Speed of sound in m/s (343 m/s at 20°C)
        """
        self.speed_of_sound = speed_of_sound

    def update_speed_of_sound(self, temperature: float, humidity: float = 50.0):
        """
        Update speed of sound based on atmospheric conditions.

        Formula: v = 331.3 + 0.606 * T (simplified)
        More accurate: includes humidity and pressure

        Args:
            temperature: Temperature in Celsius
            humidity: Relative humidity in percent
        """
        # Simplified formula (accurate enough for our purposes)
        self.speed_of_sound = 331.3 + (0.606 * temperature)

        logger = logging.getLogger(__name__)
        logger.info(
            "[Trilateration] Speed of sound updated to %.1f m/s for %s°C",
            self.speed_of_sound,
            temperature,
        )

    def trilaterate(self, detections: List[Detection]) -> Optional[TriangulationResult]:
        """
        Perform trilateration on a set of detections.

        Args:
            detections: List of Detection objects (need at least 3)

        Returns:
            TriangulationResult or None if trilateration fails
        """
        if len(detections) < 3:
            logging.getLogger(__name__).warning(
                f"[Trilateration] Need at least 3 detections, got {len(detections)}"
            )
            return None

        # Sort by timestamp
        detections = sorted(detections, key=lambda d: d.timestamp)

        # Extract positions and times
        positions = np.array([[d.latitude, d.longitude, d.altitude] for d in detections])
        timestamps = np.array([d.timestamp for d in detections])

        # Convert lat/lon to meters (approximate, good for local area)
        positions_m = self._latlon_to_meters(positions)

        # Use first detection as reference (earliest time)
        time_diffs = timestamps - timestamps[0]  # Time differences in seconds
        distance_diffs = time_diffs * self.speed_of_sound  # Distance differences in meters

        # Check geometry quality
        geometry_score = self._evaluate_geometry(positions_m)

        if geometry_score < 0.1:
            logging.getLogger(__name__).warning(
                f"[Trilateration] Poor geometry (score: {geometry_score:.2f}), skipping"
            )
            return None

        # Solve for position using least squares
        try:
            source_position, residual = self._solve_position(positions_m, distance_diffs)
        except Exception:
            logging.getLogger(__name__).exception("[Trilateration] Solver failed")
            return None

        # Convert back to lat/lon
        source_latlon = self._meters_to_latlon(source_position, positions[0])

        # Classify event type based on time window
        time_window = timestamps[-1] - timestamps[0]
        event_type = self._classify_event(time_window, positions_m, detections)

        # Calculate overall confidence
        confidence = self._calculate_confidence(detections, geometry_score, residual, time_window)

        result = TriangulationResult(
            timestamp=float(np.mean(timestamps)),
            latitude=float(source_latlon[0]),
            longitude=float(source_latlon[1]),
            altitude=float(source_latlon[2]) if len(source_latlon) > 2 else 0.0,
            confidence=float(confidence),
            num_nodes=len(detections),
            contributing_nodes=[d.node_id for d in detections],
            event_type=event_type,
            time_window=float(time_window),
            geometry_score=float(geometry_score),
            residual_error=float(residual),
            speed_of_sound=float(self.speed_of_sound),
        )

        return result

    def _latlon_to_meters(self, positions: np.ndarray) -> np.ndarray:
        """
        Convert lat/lon/alt to local XYZ coordinates in meters.

        Uses simple equirectangular projection (good for small areas <100km).
        Reference point is the first position.
        """
        ref = positions[0]

        # Meters per degree at reference latitude
        lat_m = 111132.92  # Approximately constant
        lon_m = 111132.92 * np.cos(np.radians(ref[0]))

        xyz = np.zeros_like(positions)
        xyz[:, 0] = (positions[:, 1] - ref[1]) * lon_m  # X = longitude
        xyz[:, 1] = (positions[:, 0] - ref[0]) * lat_m  # Y = latitude
        xyz[:, 2] = positions[:, 2] - ref[2]  # Z = altitude

        return xyz

    def _meters_to_latlon(self, xyz: np.ndarray, ref: np.ndarray) -> np.ndarray:
        """
        Convert local XYZ coordinates back to lat/lon/alt.
        """
        lat_m = 111132.92
        lon_m = 111132.92 * np.cos(np.radians(ref[0]))

        latlon = np.zeros(3)
        latlon[0] = ref[0] + (xyz[1] / lat_m)  # Latitude
        latlon[1] = ref[1] + (xyz[0] / lon_m)  # Longitude
        latlon[2] = ref[2] + xyz[2]  # Altitude

        return latlon

    def _solve_position(
        self, positions: np.ndarray, distance_diffs: np.ndarray
    ) -> Tuple[np.ndarray, float]:
        """
        Solve for source position using TDOA multilateration.

        Uses the augmented linearised TDOA system that treats the unknown
        source-to-reference distance (d0) as an extra variable, giving the
        exact closed-form solution for n >= 4 sensors and a good least-norm
        approximation for n = 3.

        For sensor i relative to reference sensor 0 (at origin):
            2*(si)·x  +  2*rii0*d0  =  |si|²  -  rii0²
        where rii0 = c*(ti - t0) is the TDOA range difference.
        """
        n = len(positions)
        ref_pos = positions[0]

        # Augmented matrix: columns [x, y, z, d0]
        A_aug = np.zeros((n - 1, 4))
        b = np.zeros(n - 1)

        for i in range(1, n):
            diff = positions[i] - ref_pos         # si vector (ref at origin)
            d_sensor = np.linalg.norm(diff)        # inter-sensor distance |si|
            rii0 = distance_diffs[i]               # TDOA range difference

            A_aug[i - 1, :3] = 2 * diff            # position columns
            A_aug[i - 1, 3] = 2 * rii0             # d0 column
            b[i - 1] = d_sensor ** 2 - rii0 ** 2  # correct RHS

        try:
            result, _, _, _ = np.linalg.lstsq(A_aug, b, rcond=None)
        except np.linalg.LinAlgError:
            raise ValueError("Singular matrix in augmented TDOA least squares")

        x = result[:3]   # position estimate (ignore d0 at index 3)

        # Residual: RMS of equation errors
        residual = float(np.sqrt(np.mean((A_aug @ result - b) ** 2)))

        return x, residual

    def _evaluate_geometry(self, positions: np.ndarray) -> float:
        """
        Evaluate quality of sensor geometry (GDOP - Geometric Dilution of Precision).

        Good geometry: sensors spread out in different directions
        Bad geometry: sensors clustered or in a line

        Returns score 0-1 (higher is better)
        """
        if len(positions) < 3:
            return 0.0

        # Calculate centroid
        centroid = np.mean(positions, axis=0)

        # Vectors from centroid to each sensor
        vectors = positions - centroid

        # Calculate spread (standard deviation of distances)
        distances = np.linalg.norm(vectors, axis=1)
        spread = np.std(distances)

        if spread < 1.0:  # Sensors too close together
            return 0.1

        # Calculate angular diversity
        # Good geometry has sensors spread in different directions
        if len(positions) >= 3:
            # Use volume of convex hull as proxy for angular diversity
            try:
                from scipy.spatial import ConvexHull

                hull = ConvexHull(positions[:, :2])  # 2D hull (lat/lon)
                area = hull.volume  # In 2D, volume = area

                # Normalize by typical sensor spacing
                avg_distance = np.mean(distances)
                if avg_distance > 0:
                    normalized_area = area / (avg_distance**2)
                    score = min(normalized_area / 10.0, 1.0)  # Scale to 0-1
                else:
                    score = 0.1
            except Exception as e:
                # Fallback: use simple spread measure and log the exception for diagnostics
                logging.getLogger(__name__).debug(
                    "ConvexHull computation failed, falling back to spread measure: %s",
                    e,
                    exc_info=True,
                )
                score = min(spread / 100.0, 1.0)
        else:
            score = min(spread / 100.0, 1.0)

        return score

    def _classify_event(
        self, time_window: float, positions: np.ndarray, detections: List[Detection]
    ) -> str:
        """
        Classify event type based on time window and other characteristics.

        Args:
            time_window: Time span of detections (seconds)
            positions: Sensor positions in meters
            detections: Original detection objects
        """
        # Calculate approximate distance between sensors
        max_distance = 0.0
        for i in range(len(positions)):
            for j in range(i + 1, len(positions)):
                dist = np.linalg.norm(positions[i] - positions[j])
                max_distance = max(max_distance, dist)

        # Expected time for sound to travel max distance (not used directly)
        # expected_time = max_distance / self.speed_of_sound

        # Classify based on time window
        if time_window < 0.1:
            # Very fast (< 100ms) - local event
            return "gunshot"
        elif time_window < 0.5:
            # Fast (< 500ms) - nearby event
            return "explosion"
        elif time_window < 2.0:
            # Medium (< 2s) - moderate distance
            return "thunder_near"
        elif time_window < 10.0:
            # Slow (< 10s) - distant event
            return "thunder_distant"
        else:
            # Very slow (> 10s) - very distant
            return "thunder_very_distant"

    def _calculate_confidence(
        self,
        detections: List[Detection],
        geometry_score: float,
        residual: float,
        time_window: float,
    ) -> float:
        """
        Calculate overall confidence in the trilateration result.

        Factors:
        - Number of detections (more is better)
        - Individual detection confidences
        - Geometry quality
        - Residual error
        - Time window consistency
        """
        # Factor 1: Number of detections (3 = 0.5, 4 = 0.75, 5+ = 1.0)
        num_factor = min((len(detections) - 2) / 3.0, 1.0)

        # Factor 2: Average detection confidence
        avg_confidence = np.mean([d.confidence for d in detections])

        # Factor 3: Geometry score (already 0-1)
        geometry_factor = geometry_score

        # Factor 4: Residual error (lower is better)
        # Good: < 10m, Poor: > 100m
        residual_factor = 1.0 / (1.0 + residual / 10.0)

        # Factor 5: Time window consistency
        # For gunshots, expect tight timing (< 100ms)
        # For thunder, can be much longer (seconds to tens of seconds)
        # Be lenient - we don't penalize long windows since thunder is valid
        if time_window < 0.1:
            time_factor = 1.0  # Excellent timing
        elif time_window < 1.0:
            time_factor = 0.9  # Good timing
        elif time_window < 5.0:
            time_factor = 0.8  # Acceptable timing
        else:
            time_factor = 0.7  # Long window (thunder)

        # Combined confidence (weighted average)
        confidence = (
            num_factor * 0.2
            + avg_confidence * 0.3
            + geometry_factor * 0.2
            + residual_factor * 0.2
            + time_factor * 0.1
        )

        return min(confidence, 1.0)


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

                    # Find groups of detections within time window
                    groups = self._find_detection_groups()

                    if not groups:
                        continue

                    logging.getLogger(__name__).info(
                        f"\n[TrilaterationServer] Found {len(groups)} detection group(s)"
                    )

                    # Process each group
                    for group in groups:
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
            used_indices.add(i)

            for j, other in enumerate(sorted_detections[i + 1 :], start=i + 1):
                if j in used_indices:
                    continue

                time_diff = abs(other.timestamp - detection.timestamp)

                if time_diff <= self.time_window:
                    # Same node shouldn't trigger twice in same window
                    if other.node_id not in [d.node_id for d in group]:
                        group.append(other)
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


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Trilateration Server for Gunshot Detection")
    parser.add_argument("--broker", default="localhost", help="MQTT broker address")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--username", help="MQTT username")
    parser.add_argument("--password", help="MQTT password")
    parser.add_argument(
        "--time-window",
        type=float,
        default=30.0,
        help="Time window for grouping detections (seconds) - default 30s for thunder",
    )
    parser.add_argument(
        "--min-nodes",
        type=int,
        default=3,
        help="Minimum nodes required for trilateration",
    )
    parser.add_argument("--max-nodes", type=int, default=10, help="Maximum nodes to use")
    parser.add_argument(
        "--speed-of-sound",
        type=float,
        default=343.0,
        help="Speed of sound in m/s (343 @ 20°C)",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    logging.getLogger(__name__).info(
        """
╔════════════════════════════════════════════════════════════╗
║            Trilateration Server v1.0                       ║
║         Gunshot Detection & Thunder Location              ║
╚════════════════════════════════════════════════════════════╝
    """
    )

    server = TrilaterationServer(
        broker=args.broker,
        port=args.port,
        username=args.username,
        password=args.password,
        time_window=args.time_window,
        min_nodes=args.min_nodes,
        max_nodes=args.max_nodes,
        speed_of_sound=args.speed_of_sound,
    )

    # Connect and run
    server.connect()

    # Run until Ctrl+C
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("\n\nShutting down...")
        server.disconnect()


if __name__ == "__main__":
    main()
