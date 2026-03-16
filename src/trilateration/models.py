"""Data models for trilateration: Detection and TriangulationResult."""

from dataclasses import asdict, dataclass
from typing import List


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
