#!/usr/bin/env python3
"""Standalone simulation runner for the gunshot detection system.

Usage:
    python tools/run_simulation.py --scenario basic_4node
    python tools/run_simulation.py --scenario all
    python tools/run_simulation.py --scenario moving_nodes --verbose
    python tools/run_simulation.py --scenario all --seed 123
"""

import argparse
import random
import sys
from pathlib import Path

# Ensure repo root is in path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from scripts.trilateration_server import TrilaterationEngine
from tests.simulation.acoustic_simulator import AcousticSimulator, haversine_distance
from tests.simulation.mqtt_publisher import to_detection_objects
from tests.simulation.scenarios import SCENARIOS, get_scenario


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

PASS = "✅ PASS"
FAIL = "❌ FAIL"
WARN = "⚠️  WARN"


def _position_error(result_lat, result_lon, true_lat, true_lon) -> float:
    return haversine_distance(true_lat, true_lon, 0.0, result_lat, result_lon, 0.0)


def _run_scenario(name: str, rng_seed: int, verbose: bool) -> bool:
    """Run one scenario and print a human-readable report.

    Returns True if all events pass tolerance.
    """
    scenario = get_scenario(name)
    simulator = AcousticSimulator()
    engine = TrilaterationEngine(speed_of_sound=343.0)
    rng = random.Random(rng_seed)

    print(f"\n{'━' * 60}")
    print(f"📡 Scenario : {scenario.name}")
    print(f"   {scenario.description}")
    print(f"   Nodes    : {len(scenario.nodes)}")
    print(f"   Events   : {len(scenario.events)}")
    print(f"   Tolerance: {scenario.tolerance_meters:.1f} m")
    print(f"{'━' * 60}")

    all_pass = True
    trilaterated = 0
    skipped = 0

    for event in scenario.events:
        sim_detections = simulator.simulate(scenario.nodes, event, rng=rng)

        if verbose:
            print(f"\n  Event  : {event.event_id}")
            print(f"  True   : ({event.latitude:.6f}, {event.longitude:.6f}, "
                  f"{event.altitude:.1f} m)")
            print(f"  Nodes detected: {len(sim_detections)}/{len(scenario.nodes)}")
            for sd in sim_detections:
                print(f"    {sd.node.node_id:20s} dist={sd.distance_meters:7.1f}m  "
                      f"travel={sd.travel_time_seconds:.4f}s  "
                      f"reported_t={sd.detection_timestamp:.6f}")

        if len(sim_detections) < 3:
            print(f"  {WARN}  {event.event_id}: only {len(sim_detections)} detections — skipped")
            skipped += 1
            continue

        detections = to_detection_objects(sim_detections)
        result = engine.trilaterate(detections)

        if result is None:
            print(f"  {WARN}  {event.event_id}: trilateration returned None (poor geometry?)")
            skipped += 1
            continue

        error = _position_error(
            result.latitude, result.longitude,
            event.latitude, event.longitude,
        )
        status = PASS if error <= scenario.tolerance_meters else FAIL
        if error > scenario.tolerance_meters:
            all_pass = False

        print(f"\n  {status}  {event.event_id}")
        print(f"    True location  : ({event.latitude:.6f}, {event.longitude:.6f})")
        print(f"    Estimated      : ({result.latitude:.6f}, {result.longitude:.6f})")
        print(f"    Position error : {error:.2f} m  (tolerance: {scenario.tolerance_meters:.1f} m)")
        print(f"    Geometry score : {result.geometry_score:.3f}")
        print(f"    Confidence     : {result.confidence:.2%}")
        print(f"    Nodes used     : {result.num_nodes} ({', '.join(result.contributing_nodes)})")
        print(f"    Residual error : {result.residual_error:.2f} m")
        print(f"    Event type     : {result.event_type}")

        trilaterated += 1

    print(f"\n  Summary: {trilaterated} trilaterated, {skipped} skipped")
    return all_pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Gunshot detection system — acoustic simulation runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join([
            "Available scenarios:",
            *[f"  {name}" for name in SCENARIOS],
            "  all      — run every scenario",
        ]),
    )
    parser.add_argument(
        "--scenario",
        required=True,
        metavar="NAME",
        help="Scenario name or 'all'",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show per-detection detail",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed for reproducibility (default: 42)",
    )
    args = parser.parse_args()

    if args.scenario == "all":
        names = list(SCENARIOS)
    elif args.scenario in SCENARIOS:
        names = [args.scenario]
    else:
        print(f"❌ Unknown scenario {args.scenario!r}")
        print(f"   Available: {', '.join(SCENARIOS)} or 'all'")
        sys.exit(1)

    print("╔══════════════════════════════════════════════════════════╗")
    print("║          Gunshot Detection — Simulation Runner           ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"Seed: {args.seed}  |  Scenarios: {len(names)}")

    overall_pass = True
    for name in names:
        passed = _run_scenario(name, rng_seed=args.seed, verbose=args.verbose)
        if not passed:
            overall_pass = False

    print(f"\n{'═' * 60}")
    if overall_pass:
        print("✅  All scenarios PASSED")
    else:
        print("❌  One or more scenarios FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
