"""
CLI entry point for the parliament map server.

Usage:
    strix-map
    strix-map --broker 192.168.1.100 --mqtt-port 1883 --port 8080
    python -m src.ui.parliament_map.cli --broker localhost
"""

import argparse
import logging
import sys


def main():
    parser = argparse.ArgumentParser(
        description="strix parliament map — live web UI for the trilateration server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  strix-map                                  # defaults: localhost MQTT, port 8080
  strix-map --broker 192.168.101.2          # remote MQTT broker
  strix-map --port 9000 --broker mybroker   # custom web port

Once running, open http://localhost:8080 in your browser.
        """,
    )
    parser.add_argument("--broker", default="localhost", help="MQTT broker host (default: localhost)")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port (default: 1883)")
    parser.add_argument("--port", type=int, default=8080, help="Web server port (default: 8080)")
    parser.add_argument("--mqtt-user", default=None, help="MQTT username (optional)")
    parser.add_argument("--mqtt-password", default=None, help="MQTT password (optional)")
    parser.add_argument("--max-events", type=int, default=500, help="Max events to keep in memory (default: 500)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    print(f"""
🦉 strix parliament map
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Web UI:   http://localhost:{args.port}
  MQTT:     {args.broker}:{args.mqtt_port}
  Memory:   last {args.max_events} events
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Press Ctrl+C to stop.
""")

    from src.ui.parliament_map.server import ParliamentMapServer

    server = ParliamentMapServer(
        broker_host=args.broker,
        broker_port=args.mqtt_port,
        web_port=args.port,
        mqtt_username=args.mqtt_user,
        mqtt_password=args.mqtt_password,
        max_events=args.max_events,
    )

    try:
        server.start()
    except KeyboardInterrupt:
        print("\n🦉 Parliament map stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
