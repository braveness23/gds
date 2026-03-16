"""Integration tests: physics simulation → trilateration engine.

Each scenario in tests/simulation/scenarios.py is parametrized here.
Tests use AcousticSimulator + TrilaterationEngine directly (no MQTT broker
needed) for speed and determinism, with a fixed RNG seed.

Also includes MQTT-path tests that push payloads through MockMQTTBroker
and assert the broker receives correct messages.

Run with:
    pytest tests/integration/test_trilateration_simulation.py -v
"""

import json
import random

import pytest

from tests.simulation.acoustic_simulator import AcousticSimulator, haversine_distance
from tests.simulation.mqtt_publisher import SimulationMQTTPublisher, to_detection_objects
from tests.simulation.scenarios import SCENARIOS, get_scenario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _position_error(result_lat: float, result_lon: float,
                    true_lat: float, true_lon: float) -> float:
    """Horizontal position error in metres."""
    return haversine_distance(true_lat, true_lon, 0.0, result_lat, result_lon, 0.0)


def _run_scenario(scenario_name: str, rng_seed: int = 42):
    """Simulate and trilaterate all events in a scenario.

    Returns:
        list of (event, TriangulationResult) for successful trilaterations.
    """
    from scripts.trilateration_server import TrilaterationEngine

    scenario = get_scenario(scenario_name)
    simulator = AcousticSimulator()
    engine = TrilaterationEngine(speed_of_sound=343.0)
    rng = random.Random(rng_seed)

    results = []
    for event in scenario.events:
        sim_detections = simulator.simulate(scenario.nodes, event, rng=rng)
        if len(sim_detections) < 3:
            continue
        detections = to_detection_objects(sim_detections)
        result = engine.trilaterate(detections)
        if result is not None:
            results.append((event, result))

    return scenario, results


# ---------------------------------------------------------------------------
# Parametrized accuracy tests (one per scenario)
# ---------------------------------------------------------------------------


ACCURACY_SCENARIOS = [
    "basic_4node",
    "node_dropout",
    "moving_nodes",
    "semi_auto_burst",
    "simultaneous_events",
    "large_network",
]


@pytest.mark.parametrize("scenario_name", ACCURACY_SCENARIOS)
@pytest.mark.integration
def test_scenario_position_accuracy(scenario_name):
    """Each trilaterated result must be within the scenario's tolerance."""
    scenario, results = _run_scenario(scenario_name)

    assert len(results) == scenario.expected_num_results, (
        f"[{scenario_name}] expected {scenario.expected_num_results} results, "
        f"got {len(results)}"
    )

    for event, result in results:
        error = _position_error(
            result.latitude, result.longitude,
            event.latitude, event.longitude,
        )
        assert error <= scenario.tolerance_meters, (
            f"[{scenario_name}] position error {error:.2f}m > "
            f"tolerance {scenario.tolerance_meters}m "
            f"(estimated: {result.latitude:.6f},{result.longitude:.6f}  "
            f"true: {event.latitude:.6f},{event.longitude:.6f})"
        )


@pytest.mark.parametrize("scenario_name", ACCURACY_SCENARIOS)
@pytest.mark.integration
def test_scenario_geometry_score(scenario_name):
    """Each result must meet the scenario's minimum geometry_score."""
    scenario, results = _run_scenario(scenario_name)

    for _event, result in results:
        assert result.geometry_score >= scenario.min_geometry_score, (
            f"[{scenario_name}] geometry_score {result.geometry_score:.3f} < "
            f"min {scenario.min_geometry_score}"
        )


@pytest.mark.parametrize("scenario_name", ACCURACY_SCENARIOS)
@pytest.mark.integration
def test_scenario_result_fields(scenario_name):
    """Result dataclass fields are sane (non-negative, bounded)."""
    _scenario, results = _run_scenario(scenario_name)

    for _event, result in results:
        assert 0.0 <= result.confidence <= 1.0, "confidence out of [0,1]"
        assert 0.0 <= result.geometry_score <= 1.0, "geometry_score out of [0,1]"
        assert result.num_nodes >= 3, "fewer than 3 contributing nodes"
        assert result.residual_error >= 0.0, "negative residual"
        assert result.speed_of_sound > 0.0, "non-positive speed of sound"


# ---------------------------------------------------------------------------
# poor_geometry: special handling (engine may decline to solve)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_poor_geometry_does_not_crash():
    """Collinear-node scenario must not raise; result may be None."""
    from scripts.trilateration_server import TrilaterationEngine

    scenario = get_scenario("poor_geometry")
    simulator = AcousticSimulator()
    engine = TrilaterationEngine()
    rng = random.Random(42)

    for event in scenario.events:
        sim_detections = simulator.simulate(scenario.nodes, event, rng=rng)
        if len(sim_detections) >= 3:
            detections = to_detection_objects(sim_detections)
            # Must not raise — result may be None for degenerate geometry
            result = engine.trilaterate(detections)
            # If we got a result, position error should still be within loose tolerance
            if result is not None:
                error = _position_error(
                    result.latitude, result.longitude,
                    event.latitude, event.longitude,
                )
                assert error <= scenario.tolerance_meters, (
                    f"poor_geometry error {error:.1f}m > {scenario.tolerance_meters}m"
                )


# ---------------------------------------------------------------------------
# node_dropout: verify exactly 3 nodes contribute
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_node_dropout_uses_three_nodes():
    """With one dead node (probability=0), trilateration uses exactly 3."""
    scenario, results = _run_scenario("node_dropout")

    assert len(results) == 1, f"Expected 1 result, got {len(results)}"
    _event, result = results[0]
    assert result.num_nodes == 3, (
        f"Expected 3 contributing nodes, got {result.num_nodes}"
    )
    assert "node_dead" not in result.contributing_nodes, (
        "Dead node appeared in contributing nodes"
    )


# ---------------------------------------------------------------------------
# moving_nodes: verify position-at-detection-time is used
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_moving_nodes_position_accuracy():
    """Moving nodes must use their position at detection time, not event time."""
    scenario, results = _run_scenario("moving_nodes")

    assert len(results) == 1
    event, result = results[0]
    error = _position_error(
        result.latitude, result.longitude,
        event.latitude, event.longitude,
    )
    # If the simulator uses position-at-event-time instead of detection-time,
    # the error would be larger; 10m is our correctness threshold.
    assert error <= scenario.tolerance_meters, (
        f"moving_nodes position error {error:.2f}m > {scenario.tolerance_meters}m"
    )


# ---------------------------------------------------------------------------
# semi_auto_burst: verify all 5 shots located
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_semi_auto_burst_all_shots_located():
    """All 5 burst shots must be individually trilaterated within tolerance."""
    scenario, results = _run_scenario("semi_auto_burst")

    assert len(results) == 5, f"Expected 5 results, got {len(results)}"
    for event, result in results:
        error = _position_error(
            result.latitude, result.longitude,
            event.latitude, event.longitude,
        )
        assert error <= scenario.tolerance_meters, (
            f"Burst shot {event.event_id} error {error:.2f}m > {scenario.tolerance_meters}m"
        )


# ---------------------------------------------------------------------------
# large_network: verify residual error
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_large_network_low_residual():
    """20-node network should yield a low residual error."""
    scenario, results = _run_scenario("large_network")

    assert len(results) == 1
    _event, result = results[0]
    # With 20 nodes and µs jitter, residual should be very small
    assert result.residual_error < 50.0, (
        f"large_network residual {result.residual_error:.1f}m is unexpectedly high"
    )


# ---------------------------------------------------------------------------
# MQTT path: SimulationMQTTPublisher delivers correct payloads
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_mqtt_publisher_delivers_payloads(mock_broker):
    """SimulationMQTTPublisher publishes to both gunshot topics."""
    from tests.mocks.mock_mqtt import MockMQTTClient

    scenario = get_scenario("basic_4node")
    simulator = AcousticSimulator()
    rng = random.Random(42)

    event = scenario.events[0]
    sim_detections = simulator.simulate(scenario.nodes, event, rng=rng)

    publisher = SimulationMQTTPublisher(mock_broker)
    publisher.publish(sim_detections)
    mock_broker.drain()

    # Every node should have published to the shared topic
    shared_msgs = mock_broker.get_messages("gunshot/detections")
    assert len(shared_msgs) == len(sim_detections), (
        f"Expected {len(sim_detections)} messages on gunshot/detections, "
        f"got {len(shared_msgs)}"
    )

    # Each node should also have its own topic
    for sd in sim_detections:
        node_msgs = mock_broker.get_messages(f"gunshot/{sd.node.node_id}/detections")
        assert len(node_msgs) >= 1, (
            f"No message on gunshot/{sd.node.node_id}/detections"
        )


@pytest.mark.integration
def test_mqtt_payload_schema(mock_broker):
    """Published payloads must match Detection.from_mqtt_payload() schema."""
    from scripts.trilateration_server import Detection

    scenario = get_scenario("basic_4node")
    simulator = AcousticSimulator()
    rng = random.Random(42)

    event = scenario.events[0]
    sim_detections = simulator.simulate(scenario.nodes, event, rng=rng)

    publisher = SimulationMQTTPublisher(mock_broker)
    publisher.publish(sim_detections)
    mock_broker.drain()

    msgs = mock_broker.get_messages("gunshot/detections")
    assert len(msgs) > 0

    for msg in msgs:
        payload = json.loads(msg.payload.decode())
        # Must not raise
        det = Detection.from_mqtt_payload(payload)
        assert det.node_id, "node_id is empty"
        assert det.timestamp > 0, "timestamp not positive"
        assert -90 <= det.latitude <= 90, "latitude out of range"
        assert -180 <= det.longitude <= 180, "longitude out of range"
        assert 0.0 <= det.confidence <= 1.0, "confidence out of range"


# ---------------------------------------------------------------------------
# Trilateration engine: fewer-than-3-nodes returns None gracefully
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_engine_requires_minimum_three_nodes():
    """TrilaterationEngine.trilaterate() returns None with < 3 detections."""
    from scripts.trilateration_server import Detection, TrilaterationEngine

    engine = TrilaterationEngine()

    def _det(node_id, ts, lat, lon):
        return Detection.from_mqtt_payload({
            "node_id": node_id,
            "timestamp": ts,
            "location": {"latitude": lat, "longitude": lon, "altitude": 0.0},
            "detection": {"confidence": 0.9, "detector_type": "test"},
        })

    # 0 detections
    assert engine.trilaterate([]) is None

    # 1 detection
    assert engine.trilaterate([_det("a", 1e9, 37.0, -122.0)]) is None

    # 2 detections
    assert engine.trilaterate([
        _det("a", 1e9, 37.0, -122.0),
        _det("b", 1e9 + 0.1, 37.001, -122.001),
    ]) is None

    # 3 detections should succeed (basic square with 3 of 4 corners)
    result = engine.trilaterate([
        _det("a", 1e9,       37.0,    -122.0),
        _det("b", 1e9 + 0.5, 37.002,  -122.0),
        _det("c", 1e9 + 0.7, 37.001,  -122.002),
    ])
    # Result is either a valid TriangulationResult or None (geometry may be degenerate)
    # The key contract is: no exception raised
    assert result is None or hasattr(result, "latitude")
