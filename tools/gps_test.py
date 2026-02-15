#!/usr/bin/env python3
"""
GPS Reader Test and Debug Tool

This script helps test and debug GPS functionality:
- Check if gpsd is running
- Display current GPS position
- Show satellite information
- Monitor GPS accuracy
- Test position updates
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sensors.gps import GPSData, GPSReader, StaticLocationProvider


def check_gpsd_status():
    """Check if gpsd is running."""
    import subprocess

    print("=" * 60)
    print("Checking gpsd status...")
    print("=" * 60)

    try:
        result = subprocess.run(
            ["systemctl", "status", "gpsd"], capture_output=True, text=True, timeout=2
        )

        if "Active: active (running)" in result.stdout:
            print("✅ gpsd is running")
            return True
        else:
            print("❌ gpsd is NOT running")
            print("\nTo start gpsd:")
            print("  sudo systemctl start gpsd")
            print("  sudo systemctl enable gpsd")
            return False

    except FileNotFoundError:
        print("❌ systemctl not found (not a systemd system)")
        return False
    except Exception as e:
        print(f"❌ Could not check gpsd status: {e}")
        return False


def check_gps_device():
    """Check for GPS device."""
    import os

    print("\n" + "=" * 60)
    print("Checking for GPS device...")
    print("=" * 60)

    devices = ["/dev/ttyAMA0", "/dev/ttyUSB0", "/dev/ttyACM0", "/dev/serial0"]

    found = False
    for device in devices:
        if os.path.exists(device):
            print(f"✅ Found GPS device: {device}")
            found = True

    if not found:
        print("❌ No GPS device found")
        print("\nCommon GPS devices:")
        for dev in devices:
            print(f"  {dev}")
        print("\nCheck:")
        print("  - GPS module is connected")
        print("  - UART is enabled (raspi-config)")
        print("  - Device permissions (may need to add user to dialout group)")

    return found


def test_gpsd_connection():
    """Test connection to gpsd."""
    print("\n" + "=" * 60)
    print("Testing gpsd connection...")
    print("=" * 60)

    try:
        reader = GPSReader()
        reader.connect()
        print("✅ Successfully connected to gpsd")
        return reader
    except ImportError:
        print("❌ GPS Python module not installed")
        print("\nInstall with:")
        print("  pip install gps")
        print("  or")
        print("  sudo apt install python3-gps")
        return None
    except Exception as e:
        print(f"❌ Failed to connect to gpsd: {e}")
        print("\nTroubleshooting:")
        print("  1. Check gpsd is running: sudo systemctl status gpsd")
        print("  2. Check gpsd config: cat /etc/default/gpsd")
        print("  3. Restart gpsd: sudo systemctl restart gpsd")
        print("  4. Check gpsd logs: sudo journalctl -u gpsd")
        return None


def monitor_gps(duration=30):
    """Monitor GPS for a period of time."""
    print("\n" + "=" * 60)
    print(f"Monitoring GPS for {duration} seconds...")
    print("=" * 60)
    print()

    reader = test_gpsd_connection()
    if not reader:
        return

    # Callback to print position updates
    positions = []

    def on_position(position: GPSData):
        positions.append(position)

        if position.has_fix:
            print(
                f"✅ FIX: ({position.latitude:.6f}, {position.longitude:.6f}, "
                f"{position.altitude:.1f}m) | {position.fix_type_name} | "
                f"Sats: {position.satellites} | HDOP: {position.hdop:.1f}"
            )
        else:
            print("❌ NO FIX | Searching for satellites...")

    reader.add_callback(on_position)

    # Start reading
    reader.start()

    # Monitor
    start_time = time.time()
    try:
        while time.time() - start_time < duration:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nStopped by user")

    reader.stop()

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    if positions:
        fixes = [p for p in positions if p.has_fix]

        print(f"Total positions: {len(positions)}")
        print(f"Positions with fix: {len(fixes)}")
        print(f"Fix rate: {len(fixes)/len(positions)*100:.1f}%")

        if fixes:
            avg_lat = sum(p.latitude for p in fixes) / len(fixes)
            avg_lon = sum(p.longitude for p in fixes) / len(fixes)
            avg_alt = sum(p.altitude for p in fixes) / len(fixes)
            avg_hdop = sum(p.hdop for p in fixes) / len(fixes)

            print("\nAverage position:")
            print(f"  Latitude:  {avg_lat:.6f}")
            print(f"  Longitude: {avg_lon:.6f}")
            print(f"  Altitude:  {avg_alt:.1f}m")
            print(f"  HDOP:      {avg_hdop:.1f}")

            # Calculate position spread (accuracy estimate)
            if len(fixes) > 1:
                lat_spread = max(p.latitude for p in fixes) - min(
                    p.latitude for p in fixes
                )
                lon_spread = max(p.longitude for p in fixes) - min(
                    p.longitude for p in fixes
                )

                # Approximate meters (rough)
                lat_meters = lat_spread * 111132.92
                lon_meters = (
                    lon_spread * 111132.92 * 0.7
                )  # Approximate for mid-latitudes

                print("\nPosition spread (accuracy estimate):")
                print(f"  Latitude:  {lat_meters:.1f}m")
                print(f"  Longitude: {lon_meters:.1f}m")
        else:
            print("\n❌ No GPS fix acquired during monitoring")
            print("\nTroubleshooting:")
            print("  - Ensure GPS antenna has clear view of sky")
            print("  - May take 5-15 minutes for initial fix")
            print("  - Check antenna connection")
            print("  - Try outdoors away from buildings")
    else:
        print("❌ No GPS data received")


def test_static_location():
    """Test static location provider."""
    print("\n" + "=" * 60)
    print("Testing Static Location Provider...")
    print("=" * 60)

    # Example location (San Francisco)
    provider = StaticLocationProvider(
        latitude=37.7749, longitude=-122.4194, altitude=10.0
    )

    position = provider.get_position()

    print("\nStatic position:")
    print(f"  Latitude:  {position.latitude:.6f}")
    print(f"  Longitude: {position.longitude:.6f}")
    print(f"  Altitude:  {position.altitude:.1f}m")
    print(f"  Fix type:  {position.fix_type_name}")
    print(f"  Has fix:   {position.has_fix}")

    print("\n✅ Static location provider working correctly")


def interactive_mode():
    """Interactive GPS debugging mode."""
    print("\n" + "=" * 60)
    print("Interactive GPS Mode")
    print("=" * 60)
    print("\nCommands:")
    print("  p - Show current position")
    print("  m - Monitor for 30 seconds")
    print("  w - Wait for fix")
    print("  s - Show statistics")
    print("  q - Quit")
    print()

    reader = test_gpsd_connection()
    if not reader:
        return

    reader.start()

    try:
        while True:
            cmd = input("\n> ").strip().lower()

            if cmd == "q":
                break
            elif cmd == "p":
                pos = reader.get_position()
                if pos:
                    if pos.has_fix:
                        print(
                            f"Position: ({pos.latitude:.6f}, {pos.longitude:.6f}, "
                            f"{pos.altitude:.1f}m)"
                        )
                        print(f"Fix: {pos.fix_type_name}, HDOP: {pos.hdop:.1f}")
                    else:
                        print("No GPS fix")
                else:
                    print("No position data yet")

            elif cmd == "m":
                print("Monitoring for 30 seconds...")
                start = time.time()
                while time.time() - start < 30:
                    pos = reader.get_position()
                    if pos and pos.has_fix:
                        print(
                            f"  {pos.latitude:.6f}, {pos.longitude:.6f}, "
                            f"{pos.altitude:.1f}m"
                        )
                    else:
                        print("  No fix")
                    time.sleep(2)

            elif cmd == "w":
                print("Waiting for GPS fix (60s timeout)...")
                if reader.wait_for_fix(60):
                    print("✅ Fix acquired!")
                else:
                    print("❌ Timeout - no fix")

            elif cmd == "s":
                stats = reader.get_stats()
                print("Statistics:")
                for key, value in stats.items():
                    print(f"  {key}: {value}")

            else:
                print("Unknown command")

    except KeyboardInterrupt:
        print("\n")

    finally:
        reader.stop()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="GPS Reader Test Tool")
    parser.add_argument(
        "--check", action="store_true", help="Check gpsd status and GPS device"
    )
    parser.add_argument("--test", action="store_true", help="Test gpsd connection")
    parser.add_argument(
        "--monitor", type=int, metavar="SECONDS", help="Monitor GPS for N seconds"
    )
    parser.add_argument(
        "--static", action="store_true", help="Test static location provider"
    )
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")

    args = parser.parse_args()

    print(
        """
╔════════════════════════════════════════════════════════════╗
║              GPS Reader Test Tool                          ║
╚════════════════════════════════════════════════════════════╝
    """
    )

    if args.check:
        check_gpsd_status()
        check_gps_device()

    elif args.test:
        check_gpsd_status()
        test_gpsd_connection()

    elif args.monitor:
        monitor_gps(args.monitor)

    elif args.static:
        test_static_location()

    elif args.interactive:
        interactive_mode()

    else:
        # Run all checks by default
        check_gpsd_status()
        check_gps_device()

        print("\n" + "=" * 60)
        print("Quick Test Options:")
        print("=" * 60)
        print()
        print("  python gps_test.py --test           # Test connection")
        print("  python gps_test.py --monitor 30     # Monitor for 30s")
        print("  python gps_test.py --static         # Test static location")
        print("  python gps_test.py --interactive    # Interactive mode")


if __name__ == "__main__":
    main()
