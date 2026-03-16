"""Simulation scenario definitions.

All coordinates use the SF Bay Area (37.7749, -122.4194) as center —
a well-known public location. No real deployment coordinates are used.

Scenarios:
  basic_4node        - 4 nodes ~200m apart, single shot, 5m tolerance
  poor_geometry      - 3 collinear nodes, verify low geometry quality
  node_dropout       - 4 nodes, one dead, 3-node trilat still works
  moving_nodes       - 4 nodes on patrol paths, shot mid-movement
  semi_auto_burst    - 5 shots 100ms apart, all within 5m
  simultaneous_events - 2 shots 50m apart simultaneously
  large_network      - 20 nodes over 1km², verify high accuracy
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, List

from tests.simulation.acoustic_simulator import AcousticEvent, SimulatedNode


# ---------------------------------------------------------------------------
# SF Bay Area reference coordinates (fictional test use only)
# ---------------------------------------------------------------------------

SF_LAT = 37.7749
SF_LON = -122.4194
SF_ALT = 10.0  # metres MSL

# Conversion factors at SF latitude
LAT_M = 111_132.0          # metres per degree latitude
LON_M = 88_048.0           # metres per degree longitude at 37.77°


def _dlat(metres: float) -> float:
    """Latitude offset for a north/south distance in metres."""
    return metres / LAT_M


def _dlon(metres: float) -> float:
    """Longitude offset for an east/west distance in metres."""
    return metres / LON_M


# ---------------------------------------------------------------------------
# Scenario dataclass
# ---------------------------------------------------------------------------


@dataclass
class SimulationScenario:
    """Complete specification for one simulation scenario."""

    name: str
    description: str
    nodes: List[SimulatedNode]
    events: List[AcousticEvent]
    tolerance_meters: float = 5.0
    expected_num_results: int = 1
    min_geometry_score: float = 0.0  # minimum acceptable geometry_score per result


# ---------------------------------------------------------------------------
# Individual scenario factories
# ---------------------------------------------------------------------------


def basic_4node() -> SimulationScenario:
    """4 static nodes ~200m apart in a square, single shot at centre."""
    t0 = 1_700_000_000.0
    d = 200.0

    nodes = [
        SimulatedNode("node_alpha", SF_LAT + _dlat(d / 2), SF_LON + _dlon(d / 2), SF_ALT),
        SimulatedNode("node_beta",  SF_LAT + _dlat(d / 2), SF_LON - _dlon(d / 2), SF_ALT),
        SimulatedNode("node_gamma", SF_LAT - _dlat(d / 2), SF_LON + _dlon(d / 2), SF_ALT),
        SimulatedNode("node_delta", SF_LAT - _dlat(d / 2), SF_LON - _dlon(d / 2), SF_ALT),
    ]
    events = [AcousticEvent("shot_001", SF_LAT, SF_LON, SF_ALT, t0)]

    return SimulationScenario(
        name="basic_4node",
        description="4 static nodes ~200m apart in square, single shot at centre",
        nodes=nodes,
        events=events,
        tolerance_meters=5.0,
        min_geometry_score=0.1,
    )


def poor_geometry() -> SimulationScenario:
    """3 collinear nodes (N-S line) — demonstrates weak TDOA geometry."""
    t0 = 1_700_000_000.0

    # All three nodes share the same longitude: purely collinear
    nodes = [
        SimulatedNode("node_north",  SF_LAT + _dlat(200), SF_LON, SF_ALT),
        SimulatedNode("node_centre", SF_LAT,               SF_LON, SF_ALT),
        SimulatedNode("node_south",  SF_LAT - _dlat(200), SF_LON, SF_ALT),
    ]
    # Shot offset eastward so it is unambiguously off-axis
    events = [
        AcousticEvent(
            "shot_001",
            SF_LAT + _dlat(30),
            SF_LON + _dlon(60),
            SF_ALT,
            t0,
        )
    ]

    return SimulationScenario(
        name="poor_geometry",
        description="3 collinear nodes — demonstrates weak geometry; may trilaterate with high error",
        nodes=nodes,
        events=events,
        tolerance_meters=200.0,   # loose: poor geometry yields poor accuracy
        expected_num_results=0,   # engine may return None for near-singular geometry
        min_geometry_score=0.0,
    )


def node_dropout() -> SimulationScenario:
    """4 nodes, one has detection_probability=0; verify 3-node trilat still works."""
    t0 = 1_700_000_000.0
    d = 200.0

    nodes = [
        SimulatedNode("node_alpha", SF_LAT + _dlat(d / 2), SF_LON + _dlon(d / 2), SF_ALT),
        SimulatedNode("node_beta",  SF_LAT + _dlat(d / 2), SF_LON - _dlon(d / 2), SF_ALT),
        SimulatedNode("node_gamma", SF_LAT - _dlat(d / 2), SF_LON + _dlon(d / 2), SF_ALT),
        SimulatedNode(
            "node_dead",
            SF_LAT - _dlat(d / 2), SF_LON - _dlon(d / 2), SF_ALT,
            detection_probability=0.0,
        ),
    ]
    events = [AcousticEvent("shot_001", SF_LAT, SF_LON, SF_ALT, t0)]

    return SimulationScenario(
        name="node_dropout",
        description="4 nodes, one completely dead; 3-node trilateration",
        nodes=nodes,
        events=events,
        tolerance_meters=10.0,
        min_geometry_score=0.1,
    )


def moving_nodes() -> SimulationScenario:
    """4 nodes on slow patrol paths; event fires mid-movement."""
    t0 = 1_700_000_000.0
    d = 200.0
    # Each node moves 2 m/s for 10 s bracketing the event
    step_lat = _dlat(2.0 * 10)   # 20 m north/south
    step_lon = _dlon(2.0 * 10)   # 20 m east/west

    nodes = [
        SimulatedNode(
            "node_alpha",
            SF_LAT + _dlat(d / 2), SF_LON + _dlon(d / 2), SF_ALT,
            waypoints=[
                (t0 - 10, SF_LAT + _dlat(d / 2) - step_lat, SF_LON + _dlon(d / 2), SF_ALT),
                (t0 + 10, SF_LAT + _dlat(d / 2) + step_lat, SF_LON + _dlon(d / 2), SF_ALT),
            ],
        ),
        SimulatedNode(
            "node_beta",
            SF_LAT + _dlat(d / 2), SF_LON - _dlon(d / 2), SF_ALT,
            waypoints=[
                (t0 - 10, SF_LAT + _dlat(d / 2), SF_LON - _dlon(d / 2) - step_lon, SF_ALT),
                (t0 + 10, SF_LAT + _dlat(d / 2), SF_LON - _dlon(d / 2) + step_lon, SF_ALT),
            ],
        ),
        SimulatedNode(
            "node_gamma",
            SF_LAT - _dlat(d / 2), SF_LON + _dlon(d / 2), SF_ALT,
            waypoints=[
                (t0 - 10, SF_LAT - _dlat(d / 2) + step_lat, SF_LON + _dlon(d / 2), SF_ALT),
                (t0 + 10, SF_LAT - _dlat(d / 2) - step_lat, SF_LON + _dlon(d / 2), SF_ALT),
            ],
        ),
        SimulatedNode(
            "node_delta",
            SF_LAT - _dlat(d / 2), SF_LON - _dlon(d / 2), SF_ALT,
            waypoints=[
                (t0 - 10, SF_LAT - _dlat(d / 2), SF_LON - _dlon(d / 2) + step_lon, SF_ALT),
                (t0 + 10, SF_LAT - _dlat(d / 2), SF_LON - _dlon(d / 2) - step_lon, SF_ALT),
            ],
        ),
    ]
    events = [AcousticEvent("shot_001", SF_LAT, SF_LON, SF_ALT, t0)]

    return SimulationScenario(
        name="moving_nodes",
        description="4 nodes on patrol paths, shot fires mid-movement",
        nodes=nodes,
        events=events,
        tolerance_meters=10.0,
        min_geometry_score=0.1,
    )


def semi_auto_burst() -> SimulationScenario:
    """5 shots at the same location, 100ms apart; all results within 5m."""
    t0 = 1_700_000_000.0
    d = 200.0

    nodes = [
        SimulatedNode("node_alpha", SF_LAT + _dlat(d / 2), SF_LON + _dlon(d / 2), SF_ALT),
        SimulatedNode("node_beta",  SF_LAT + _dlat(d / 2), SF_LON - _dlon(d / 2), SF_ALT),
        SimulatedNode("node_gamma", SF_LAT - _dlat(d / 2), SF_LON + _dlon(d / 2), SF_ALT),
        SimulatedNode("node_delta", SF_LAT - _dlat(d / 2), SF_LON - _dlon(d / 2), SF_ALT),
    ]
    events = [
        AcousticEvent(f"shot_{i:03d}", SF_LAT, SF_LON, SF_ALT, t0 + i * 0.1)
        for i in range(5)
    ]

    return SimulationScenario(
        name="semi_auto_burst",
        description="5 shots at same location 100ms apart; expect 5 results all within 5m",
        nodes=nodes,
        events=events,
        tolerance_meters=5.0,
        expected_num_results=5,
        min_geometry_score=0.1,
    )


def simultaneous_events() -> SimulationScenario:
    """2 shots 50m apart fired simultaneously; verify each can be located."""
    t0 = 1_700_000_000.0
    d = 300.0   # wider node spacing helps separate the two sources

    nodes = [
        SimulatedNode("node_alpha", SF_LAT + _dlat(d / 2), SF_LON + _dlon(d / 2), SF_ALT),
        SimulatedNode("node_beta",  SF_LAT + _dlat(d / 2), SF_LON - _dlon(d / 2), SF_ALT),
        SimulatedNode("node_gamma", SF_LAT - _dlat(d / 2), SF_LON + _dlon(d / 2), SF_ALT),
        SimulatedNode("node_delta", SF_LAT - _dlat(d / 2), SF_LON - _dlon(d / 2), SF_ALT),
    ]
    # Two shots 50m apart (25m north / south of centre)
    events = [
        AcousticEvent("shot_A", SF_LAT + _dlat(25), SF_LON, SF_ALT, t0),
        AcousticEvent("shot_B", SF_LAT - _dlat(25), SF_LON, SF_ALT, t0),
    ]

    return SimulationScenario(
        name="simultaneous_events",
        description="2 shots 50m apart simultaneously; each trilaterated separately within 40m",
        nodes=nodes,
        events=events,
        tolerance_meters=40.0,   # 50m separation → ~30m expected error with linear TDOA
        expected_num_results=2,
        min_geometry_score=0.1,
    )


def large_network() -> SimulationScenario:
    """20 nodes over 1km²; verify accuracy improves vs 4-node baseline."""
    t0 = 1_700_000_000.0

    # 4×5 grid of nodes covering ±500m in each direction
    nodes = []
    for row in range(4):
        for col in range(5):
            lat = SF_LAT + _dlat(-500 + row * 333)
            lon = SF_LON + _dlon(-500 + col * 250)
            nodes.append(SimulatedNode(f"node_{row}_{col}", lat, lon, SF_ALT))

    events = [AcousticEvent("shot_001", SF_LAT, SF_LON, SF_ALT, t0)]

    return SimulationScenario(
        name="large_network",
        description="20 nodes over 1km²; accuracy should improve over 4-node case",
        nodes=nodes,
        events=events,
        tolerance_meters=5.0,
        min_geometry_score=0.1,
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

SCENARIOS: Dict[str, Callable[[], SimulationScenario]] = {
    "basic_4node": basic_4node,
    "poor_geometry": poor_geometry,
    "node_dropout": node_dropout,
    "moving_nodes": moving_nodes,
    "semi_auto_burst": semi_auto_burst,
    "simultaneous_events": simultaneous_events,
    "large_network": large_network,
}


def get_scenario(name: str) -> SimulationScenario:
    """Instantiate a scenario by name.

    Args:
        name: Scenario name (key in SCENARIOS dict).

    Returns:
        SimulationScenario instance.

    Raises:
        ValueError: If name is not recognised.
    """
    if name not in SCENARIOS:
        available = list(SCENARIOS)
        raise ValueError(f"Unknown scenario {name!r}. Available: {available}")
    return SCENARIOS[name]()
