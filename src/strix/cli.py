"""
strix CLI entry points.

Installed console scripts delegate here:
  strix          → strix.cli:main         (node audio pipeline)
  strix-server   → strix.cli:trilateration (parliament trilateration server)
"""

import sys


def main():
    """Entry point for the `strix` console script (node audio pipeline)."""
    try:
        import main as _main
    except ImportError:
        import importlib
        import os
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if root not in sys.path:
            sys.path.insert(0, root)
        _main = importlib.import_module("main")
    _main.main()


def trilateration():
    """Entry point for the `strix-server` console script (parliament trilateration server)."""
    from src.trilateration.server import TrilaterationServer
    import argparse

    parser = argparse.ArgumentParser(description="strix parliament trilateration server")
    parser.add_argument("--broker", default="localhost", help="MQTT broker host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--time-window", type=float, default=30.0, help="Detection grouping window (seconds)")
    parser.add_argument("--min-nodes", type=int, default=3, help="Minimum nodes required for trilateration")
    args = parser.parse_args()

    server = TrilaterationServer(
        broker_host=args.broker,
        broker_port=args.port,
        time_window=args.time_window,
        min_nodes=args.min_nodes,
    )
    server.start()
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
