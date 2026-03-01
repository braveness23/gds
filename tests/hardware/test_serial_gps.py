"""Hardware tests for serial GPS module.

These tests require a physical GPS module connected via serial.
Run with: pytest tests/hardware/test_serial_gps.py -v -s
"""

import logging
import time

import pytest

from src.sensors.gps import SerialGPSReader

# Configure verbose logging for hardware tests
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

pytestmark = [pytest.mark.hardware, pytest.mark.gps]


class TestSerialGPSHardware:
    """Hardware tests for serial GPS reader."""

    @pytest.mark.slow
    def test_gps_connection(self, gps_device, gps_baudrate):
        """Test: GPS device can be opened and connected."""
        print(f"\n{'='*70}")
        print(f"TEST: GPS Connection")
        print(f"Device: {gps_device}")
        print(f"Baud rate: {gps_baudrate}")
        print(f"{'='*70}\n")

        try:
            gps = SerialGPSReader(device=gps_device, baudrate=gps_baudrate)
            print(f"✓ SerialGPSReader created")

            gps.connect()
            print(f"✓ Connected to GPS device")

            assert gps.connected
            assert gps.serial is not None
            assert gps.serial.is_open

            print(f"\n✓✓✓ GPS CONNECTION TEST PASSED ✓✓✓\n")

        except ImportError as e:
            pytest.skip(f"Required dependencies not installed: {e}")
        except (OSError, IOError) as e:
            pytest.fail(
                f"Failed to open GPS device {gps_device}\n"
                f"Error: {e}\n"
                f"Check:\n"
                f"  - Device exists: ls -l {gps_device}\n"
                f"  - Permissions: sudo usermod -a -G dialout $USER\n"
                f"  - Correct baud rate (try --baudrate=4800 or 115200)"
            )
        finally:
            if "gps" in locals():
                gps.disconnect()

    @pytest.mark.slow
    def test_gps_nmea_sentences(self, gps_device, gps_baudrate):
        """Test: GPS outputs valid NMEA sentences."""
        print(f"\n{'='*70}")
        print(f"TEST: NMEA Sentence Reception")
        print(f"Device: {gps_device}")
        print(f"{'='*70}\n")

        try:
            gps = SerialGPSReader(device=gps_device, baudrate=gps_baudrate)
            gps.connect()

            print("Reading NMEA sentences for 10 seconds...")
            print("(This shows raw GPS output - should see $GP... sentences)\n")

            sentences_seen = []
            start_time = time.time()
            valid_count = 0

            while time.time() - start_time < 10:
                try:
                    line = gps.serial.readline().decode(errors="ignore").strip()
                    if line.startswith("$"):
                        sentence_type = line.split(",")[0]
                        if sentence_type not in sentences_seen:
                            sentences_seen.append(sentence_type)
                            print(f"  Found: {sentence_type}")
                        valid_count += 1

                        # Show first few complete sentences
                        if valid_count <= 5:
                            print(f"    {line}")

                except (OSError, UnicodeDecodeError) as e:
                    print(f"  Read error: {e}")
                    continue

            print(f"\nSummary:")
            print(f"  Valid NMEA sentences: {valid_count}")
            print(f"  Unique types: {len(sentences_seen)}")
            print(f"  Types seen: {', '.join(sentences_seen)}")

            # Should see at least some NMEA sentences
            assert valid_count > 0, "No NMEA sentences received from GPS"
            assert len(sentences_seen) > 0, "No sentence types detected"

            # Common NMEA sentence types
            print(f"\n  Expected types: $GPGGA (position), $GPRMC (recommended minimum)")
            print(f"\n✓✓✓ NMEA RECEPTION TEST PASSED ✓✓✓\n")

        except ImportError:
            pytest.skip("Required dependencies not installed")
        finally:
            if "gps" in locals():
                gps.disconnect()

    @pytest.mark.slow
    def test_gps_fix_acquisition(self, gps_device, gps_baudrate, gps_timeout):
        """Test: GPS can acquire satellite fix."""
        print(f"\n{'='*70}")
        print(f"TEST: GPS Fix Acquisition")
        print(f"Device: {gps_device}")
        print(f"Timeout: {gps_timeout}s")
        print(f"{'='*70}\n")

        try:
            gps = SerialGPSReader(device=gps_device, baudrate=gps_baudrate)
            gps.connect()
            gps.start()

            print("⏱  Waiting for GPS fix...")
            print("   (Ensure GPS antenna has clear sky view)")
            print("   (Cold start can take 30-60 seconds)\n")

            start_time = time.time()
            last_status_time = start_time
            got_fix = False
            best_position = None

            while time.time() - start_time < gps_timeout:
                # Read position
                position = gps.get_data()

                # Print status every 5 seconds
                if time.time() - last_status_time >= 5:
                    elapsed = int(time.time() - start_time)
                    if position:
                        print(f"  [{elapsed:3d}s] Fix: {position.fix_quality}, Sats: {position.satellites}, "
                              f"HDOP: {position.hdop:.1f}")
                    else:
                        print(f"  [{elapsed:3d}s] Waiting for data...")
                    last_status_time = time.time()

                # Check for fix
                if position and position.has_fix:
                    got_fix = True
                    best_position = position
                    break

                time.sleep(1)

            elapsed = time.time() - start_time

            if got_fix:
                print(f"\n✓ GPS FIX ACQUIRED in {elapsed:.1f}s!\n")
                print(f"Position Details:")
                print(f"  Latitude:  {best_position.latitude:.8f}°")
                print(f"  Longitude: {best_position.longitude:.8f}°")
                print(f"  Altitude:  {best_position.altitude:.2f}m")
                print(f"  Fix Quality: {best_position.fix_quality}")
                print(f"  Satellites: {best_position.satellites}")
                print(f"  HDOP: {best_position.hdop:.2f}")
                if best_position.speed > 0:
                    print(f"  Speed: {best_position.speed:.2f} m/s")
                    print(f"  Track: {best_position.track:.1f}°")

                # Verify position is reasonable (not 0,0)
                assert best_position.latitude != 0.0 or best_position.longitude != 0.0, \
                    "GPS reports fix but position is (0,0)"

                print(f"\n✓✓✓ GPS FIX TEST PASSED ✓✓✓\n")
            else:
                pytest.fail(
                    f"GPS did not acquire fix within {gps_timeout}s\n"
                    f"Check:\n"
                    f"  - Antenna has clear view of sky (not indoors)\n"
                    f"  - Wait longer (cold start can take 60s)\n"
                    f"  - Antenna is properly connected\n"
                    f"  - GPS module has power"
                )

        except ImportError:
            pytest.skip("Required dependencies not installed")
        finally:
            if "gps" in locals():
                gps.stop()
                gps.disconnect()

    @pytest.mark.slow
    def test_gps_position_updates(self, gps_device, gps_baudrate):
        """Test: GPS provides regular position updates."""
        print(f"\n{'='*70}")
        print(f"TEST: Position Update Rate")
        print(f"Device: {gps_device}")
        print(f"{'='*70}\n")

        try:
            gps = SerialGPSReader(device=gps_device, baudrate=gps_baudrate, update_interval=1.0)
            gps.connect()
            gps.start()

            print("Monitoring position updates for 30 seconds...\n")

            positions = []
            start_time = time.time()

            while time.time() - start_time < 30:
                position = gps.get_data()
                if position:
                    positions.append(position)
                time.sleep(1)

            # Calculate update rate
            update_count = len(positions)
            elapsed = time.time() - start_time
            update_rate = update_count / elapsed

            print(f"\nUpdate Statistics:")
            print(f"  Duration: {elapsed:.1f}s")
            print(f"  Updates received: {update_count}")
            print(f"  Update rate: {update_rate:.2f} Hz")

            # Check for fixes
            fixes = [p for p in positions if p.has_fix]
            print(f"  Positions with fix: {len(fixes)}/{update_count}")

            if fixes:
                avg_hdop = sum(p.hdop for p in fixes) / len(fixes)
                avg_sats = sum(p.satellites for p in fixes) / len(fixes)
                print(f"  Average HDOP: {avg_hdop:.2f}")
                print(f"  Average satellites: {avg_sats:.1f}")

                # Show position stability (should be fairly stable if not moving)
                lats = [p.latitude for p in fixes]
                lons = [p.longitude for p in fixes]
                lat_range = max(lats) - min(lats)
                lon_range = max(lons) - min(lons)
                print(f"\nPosition Stability:")
                print(f"  Latitude range: {lat_range*111000:.2f}m")  # ~111km per degree
                print(f"  Longitude range: {lon_range*111000:.2f}m")

            # Should get at least some updates
            assert update_count > 0, "No position updates received"

            print(f"\n✓✓✓ POSITION UPDATE TEST PASSED ✓✓✓\n")

        except ImportError:
            pytest.skip("Required dependencies not installed")
        finally:
            if "gps" in locals():
                gps.stop()
                gps.disconnect()

    @pytest.mark.slow
    def test_gps_timing_accuracy(self, gps_device, gps_baudrate):
        """Test: GPS timestamps are accurate and monotonic."""
        print(f"\n{'='*70}")
        print(f"TEST: GPS Timing Accuracy")
        print(f"Device: {gps_device}")
        print(f"{'='*70}\n")

        try:
            gps = SerialGPSReader(device=gps_device, baudrate=gps_baudrate, update_interval=1.0)
            gps.connect()
            gps.start()

            print("Collecting timestamps for 20 seconds...\n")

            timestamps = []
            start_time = time.time()

            while time.time() - start_time < 20:
                position = gps.get_data()
                if position:
                    timestamps.append(position.timestamp)
                time.sleep(1)

            # Analyze timestamp intervals
            if len(timestamps) > 1:
                intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]

                print(f"Timestamp Analysis:")
                print(f"  Samples: {len(timestamps)}")
                print(f"  Min interval: {min(intervals):.6f}s")
                print(f"  Max interval: {max(intervals):.6f}s")
                print(f"  Mean interval: {sum(intervals)/len(intervals):.6f}s")

                # Check monotonicity
                is_monotonic = all(intervals[i] > 0 for i in range(len(intervals)))
                print(f"  Monotonic: {is_monotonic}")

                # Check for large gaps (>5 seconds)
                large_gaps = [i for i in intervals if i > 5.0]
                if large_gaps:
                    print(f"  ⚠ Warning: {len(large_gaps)} intervals >5s detected")

                assert is_monotonic, "Timestamps not monotonically increasing"
                print(f"\n✓✓✓ TIMING ACCURACY TEST PASSED ✓✓✓\n")
            else:
                pytest.skip("Not enough timestamps collected")

        except ImportError:
            pytest.skip("Required dependencies not installed")
        finally:
            if "gps" in locals():
                gps.stop()
                gps.disconnect()
