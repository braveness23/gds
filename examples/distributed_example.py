#!/usr/bin/env python3
"""
Distributed fleet example showing MQTT coordination.

This demonstrates how multiple nodes publish to a central broker
and how a coordinator collects detections for trilateration.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audio.audio_nodes import FileSourceNode
from core.event_bus import get_event_bus
from detection.detection_nodes import AubioOnsetNode
from output.mqtt_output import MQTTFleetCoordinator, MQTTOutputNode
from processing.processing_nodes import HighPassFilterNode, MonoConversionNode


def simulate_node(node_id: str, audio_file: str, broker: str, location: tuple):
    """
    Simulate a single detection node.

    In real deployment, this would run on each Raspberry Pi.
    """
    print(f"\n{'='*60}")
    print(f"Starting Node: {node_id}")
    print(f"Location: {location}")
    print(f"{'='*60}\n")

    # Get local event bus (each node has its own)
    event_bus = get_event_bus()

    # Mock GPS position
    class MockGPS:
        def __init__(self, lat, lon, alt):
            from dataclasses import dataclass

            @dataclass
            class Position:
                latitude: float
                longitude: float
                altitude: float
                fix_quality: int = 2
                satellites: int = 8

            self.position = Position(lat, lon, alt)

        def get_position(self):
            return self.position

    gps = MockGPS(*location)

    # Create MQTT output (subscribes to local event bus)
    mqtt_out = MQTTOutputNode(
        broker=broker, port=1883, node_id=node_id, event_bus=event_bus, gps_reader=gps
    )
    mqtt_out.connect()

    # Wait for MQTT connection
    time.sleep(1)

    # Build detection pipeline
    source = FileSourceNode(filepath=audio_file, buffer_size=1024, realtime=True)
    mono = MonoConversionNode()
    hpf = HighPassFilterNode(cutoff_freq=5000)
    detector = AubioOnsetNode(
        name=f"Aubio_{node_id}",
        method="complex",
        hop_size=512,
        threshold=0.3,
        event_bus=event_bus,  # Detections go to local event bus
    )

    # Connect pipeline
    source.connect(mono.receive)
    mono.connect(hpf.receive)
    hpf.connect(detector.receive)

    print(f"[{node_id}] Pipeline ready, starting detection...")

    # Start processing
    source.start()

    # Run until file complete
    while source.running:
        time.sleep(0.1)

    print(f"\n[{node_id}] Processing complete")
    mqtt_out.disconnect()


def run_coordinator(broker: str, duration: float = 30.0):
    """
    Run fleet coordinator that collects detections from all nodes.

    In real deployment, this would run on a central server.
    """
    print(f"\n{'='*60}")
    print("Fleet Coordinator")
    print(f"Broker: {broker}")
    print(f"{'='*60}\n")

    coordinator = MQTTFleetCoordinator(broker=broker, port=1883)

    # Set up callbacks
    def on_detection(payload):
        node_id = payload.get("node_id", "unknown")
        timestamp = payload.get("timestamp", 0)
        location = payload.get("location", {})
        detection = payload.get("detection", {})

        print(f"\n🎯 DETECTION FROM {node_id}")
        print(f"   Time: {timestamp:.6f}s")
        print(
            f"   Location: ({location.get('latitude', 'N/A'):.4f}, "
            f"{location.get('longitude', 'N/A'):.4f})"
        )
        print(f"   Type: {detection.get('detector_type', 'unknown')}")
        print(f"   Confidence: {detection.get('confidence', 0):.2f}")

    def on_health(payload):
        node_id = payload.get("node_id", "unknown")
        data = payload.get("data", {})
        print(f"[Health] {node_id}: {data}")

    coordinator.set_detection_callback(on_detection)
    coordinator.set_health_callback(on_health)

    # Connect and monitor
    coordinator.connect()

    print("Monitoring fleet... (Ctrl+C to stop)\n")

    start_time = time.time()

    try:
        while time.time() - start_time < duration:
            time.sleep(1)

            # Show active nodes every 5 seconds
            if int(time.time() - start_time) % 5 == 0:
                active = coordinator.get_active_nodes()
                print(f"\n[Coordinator] Active nodes: {len(active)}")
                for node in active:
                    print(f"  - {node['node_id']}: last seen {node['age']:.1f}s ago")

    except KeyboardInterrupt:
        print("\n\nStopping coordinator...")

    # Summary
    print(f"\n{'='*60}")
    print("Summary")
    print(f"{'='*60}")
    print(f"Total detections received: {len(coordinator.detections)}")
    print(f"Active nodes: {len(coordinator.get_active_nodes())}")

    # Show recent detections for trilateration
    recent = coordinator.get_recent_detections(window=2.0)
    if len(recent) >= 3:
        print("\n📍 Trilateration Candidates (within 2s window):")
        for det in recent[:5]:
            print(f"  - Node {det['node_id']} at {det['timestamp']:.6f}s")
            loc = det.get("location", {})
            print(
                f"    Location: ({loc.get('latitude', 'N/A')}, {loc.get('longitude', 'N/A')})"
            )

    coordinator.disconnect()


def main():
    """Main entry point."""
    print(
        """
╔════════════════════════════════════════════════════════════╗
║         Distributed Gunshot Detection Fleet Demo          ║
╚════════════════════════════════════════════════════════════╝

This demo shows:
- Multiple detection nodes (simulated)
- MQTT broker coordination
- Fleet monitoring
- Trilateration data collection

Usage:
  python distributed_example.py coordinator [broker]
  python distributed_example.py node <node_id> <audio_file> [broker]

Examples:
  # Terminal 1: Start coordinator
  python distributed_example.py coordinator localhost

  # Terminal 2: Start node 1
  python distributed_example.py node node_001 test.wav localhost

  # Terminal 3: Start node 2
  python distributed_example.py node node_002 test.wav localhost

Requirements:
  - MQTT broker running (mosquitto)
  - Start with: mosquitto -v
    """
    )

    if len(sys.argv) < 2:
        print("Error: Missing arguments")
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "coordinator":
        broker = sys.argv[2] if len(sys.argv) > 2 else "localhost"
        run_coordinator(broker, duration=60.0)

    elif mode == "node":
        if len(sys.argv) < 4:
            print("Error: node mode requires <node_id> <audio_file>")
            sys.exit(1)

        node_id = sys.argv[2]
        audio_file = sys.argv[3]
        broker = sys.argv[4] if len(sys.argv) > 4 else "localhost"

        # Mock locations (would come from GPS in real deployment)
        locations = {
            "node_001": (37.7749, -122.4194, 10.0),  # San Francisco
            "node_002": (37.7750, -122.4190, 10.0),  # 50m east
            "node_003": (37.7748, -122.4190, 10.0),  # 50m south-east
        }

        location = locations.get(node_id, (0.0, 0.0, 0.0))
        simulate_node(node_id, audio_file, broker, location)

    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
