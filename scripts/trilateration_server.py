#!/usr/bin/env python3
"""
Trilateration Server CLI for strix

Thin CLI wrapper around src.trilateration.TrilaterationServer.
See src/trilateration/ for the full implementation.
"""

import logging

from src.trilateration import TrilaterationServer

# Re-export for backwards compatibility with any code that imports from this module
from src.trilateration import Detection, TrilaterationEngine, TriangulationResult

__all__ = ["Detection", "TrilaterationEngine", "TriangulationResult", "TrilaterationServer"]


def main():
    """Main entry point."""
    import argparse
    import time

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
║            Trilateration Server v2.0                       ║
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
