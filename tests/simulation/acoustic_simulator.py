"""Physics-accurate acoustic event simulator.

Given a set of nodes and an acoustic event, calculates exact detection
timestamps accounting for:
- 3D haversine distance
- Speed of sound (with optional temperature compensation)
- Per-node clock offset (systematic error)
- Per-node clock jitter (gaussian noise)
- Per-node detection probability
- Moving nodes via waypoint interpolation
"""

import math
import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class SimulatedNode:
    """A detection node in the simulation network."""

    node_id: str
    latitude: float
    longitude: float
    altitude: float
    clock_offset_seconds: float = 0.0   # systematic clock error
    clock_jitter_seconds: float = 1e-6  # gaussian noise std dev (1 µs default)
    detection_probability: float = 1.0  # chance node detects the event at all
    # Moving node support: list of (timestamp, lat, lon, alt) waypoints
    waypoints: List[Tuple[float, float, float, float]] = field(default_factory=list)

    def position_at(self, t: float) -> Tuple[float, float, float]:
        """Return node (lat, lon, alt) at time t, interpolating waypoints if set."""
        if not self.waypoints:
            return self.latitude, self.longitude, self.altitude

        if t <= self.waypoints[0][0]:
            _, lat, lon, alt = self.waypoints[0]
            return lat, lon, alt

        if t >= self.waypoints[-1][0]:
            _, lat, lon, alt = self.waypoints[-1]
            return lat, lon, alt

        for i in range(len(self.waypoints) - 1):
            t0, lat0, lon0, alt0 = self.waypoints[i]
            t1, lat1, lon1, alt1 = self.waypoints[i + 1]
            if t0 <= t <= t1:
                alpha = (t - t0) / (t1 - t0)
                return (
                    lat0 + alpha * (lat1 - lat0),
                    lon0 + alpha * (lon1 - lon0),
                    alt0 + alpha * (alt1 - alt0),
                )

        return self.latitude, self.longitude, self.altitude


@dataclass
class AcousticEvent:
    """An acoustic event (e.g. gunshot) to be simulated."""

    event_id: str
    latitude: float
    longitude: float
    altitude: float
    timestamp: float          # Unix epoch of the event
    speed_of_sound: float = 343.0
    event_type: str = "gunshot"


@dataclass
class SimulatedDetection:
    """Detection of an acoustic event by one node, with noise applied."""

    node: SimulatedNode
    event: AcousticEvent
    detection_timestamp: float    # reported time (with offset + jitter applied)
    distance_meters: float        # true distance from event to node
    travel_time_seconds: float    # true acoustic travel time
    node_latitude: float          # node position at detection time
    node_longitude: float
    node_altitude: float


def haversine_distance(
    lat1: float, lon1: float, alt1: float,
    lat2: float, lon2: float, alt2: float,
) -> float:
    """3D distance in meters: haversine for horizontal + direct for vertical."""
    R = 6_371_000.0  # Earth radius in metres
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    horiz = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    vert = alt2 - alt1
    return math.sqrt(horiz ** 2 + vert ** 2)


def speed_of_sound_at(temperature_celsius: float) -> float:
    """Speed of sound (m/s) using temperature-compensated formula."""
    return 331.3 * math.sqrt(1 + temperature_celsius / 273.15)


class AcousticSimulator:
    """Simulates acoustic event propagation to a distributed node network."""

    def simulate(
        self,
        nodes: List[SimulatedNode],
        event: AcousticEvent,
        rng: Optional[random.Random] = None,
    ) -> List[SimulatedDetection]:
        """Simulate detections of event by all nodes.

        Args:
            nodes: List of nodes in the network.
            event: The acoustic event to simulate.
            rng: Optional seeded Random instance for reproducibility.

        Returns:
            List of SimulatedDetection for nodes that detected the event
            (nodes that fail detection_probability check are excluded).
        """
        if rng is None:
            rng = random.Random()

        detections = []

        for node in nodes:
            # Apply detection probability dropout
            if rng.random() > node.detection_probability:
                continue

            # First estimate: node position at event time
            node_lat, node_lon, node_alt = node.position_at(event.timestamp)
            dist = haversine_distance(
                event.latitude, event.longitude, event.altitude,
                node_lat, node_lon, node_alt,
            )
            travel_time = dist / event.speed_of_sound

            # Refine for moving nodes: re-estimate position at detection time
            detection_time_est = event.timestamp + travel_time
            node_lat, node_lon, node_alt = node.position_at(detection_time_est)
            dist = haversine_distance(
                event.latitude, event.longitude, event.altitude,
                node_lat, node_lon, node_alt,
            )
            travel_time = dist / event.speed_of_sound

            # True detection time
            true_detection_time = event.timestamp + travel_time

            # Apply systematic clock offset + gaussian jitter
            jitter = rng.gauss(0.0, node.clock_jitter_seconds)
            reported_time = true_detection_time + node.clock_offset_seconds + jitter

            # Final node position at detection time (for payload)
            final_lat, final_lon, final_alt = node.position_at(true_detection_time)

            detections.append(SimulatedDetection(
                node=node,
                event=event,
                detection_timestamp=reported_time,
                distance_meters=dist,
                travel_time_seconds=travel_time,
                node_latitude=final_lat,
                node_longitude=final_lon,
                node_altitude=final_alt,
            ))

        return detections
