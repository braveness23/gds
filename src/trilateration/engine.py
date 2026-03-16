"""TrilaterationEngine: core TDOA multilateration algorithm."""

import logging
from typing import List, Optional, Tuple

import numpy as np

from src.trilateration.models import Detection, TriangulationResult


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
