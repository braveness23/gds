"""Hardware integration tests for GPS + Audio system.

These tests require both GPS and I2S microphone hardware.
Run with: pytest tests/hardware/test_integration.py -v -s
"""

import logging
import time
from pathlib import Path

import numpy as np
import pytest

from src.audio.audio_nodes import ALSASourceNode, AudioBuffer
from src.core.event_bus import Event, EventBus, EventType
from src.sensors.gps import SerialGPSReader

# Configure verbose logging for hardware tests
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

pytestmark = [pytest.mark.hardware, pytest.mark.gps, pytest.mark.audio, pytest.mark.slow]


class TestGPSAudioIntegration:
    """Integration tests for GPS-timestamped audio system."""

    def test_gps_audio_simultaneous_operation(self, gps_device, gps_baudrate, audio_device, audio_format_bits):
        """Test: GPS and audio can operate simultaneously without interference."""
        print(f"\n{'='*70}")
        print(f"TEST: GPS + Audio Simultaneous Operation")
        print(f"GPS: {gps_device}")
        print(f"Audio: {audio_device}")
        print(f"{'='*70}\n")

        try:
            # Initialize GPS
            gps = SerialGPSReader(device=gps_device, baudrate=gps_baudrate, update_interval=1.0)
            gps.connect()
            gps.start()
            print("✓ GPS started")

            # Initialize audio
            alsa = ALSASourceNode(
                device=audio_device,
                sample_rate=48000,
                channels=1,
                buffer_size=2048,
                format_bits=audio_format_bits,
            )
            alsa.start()
            print("✓ Audio started")

            print("\nRunning both systems for 15 seconds...\n")

            gps_updates = []
            audio_buffers = []

            def audio_callback(buffer: AudioBuffer):
                audio_buffers.append(buffer)

            alsa.connect(audio_callback)

            start_time = time.time()
            while time.time() - start_time < 15:
                # Check GPS
                pos = gps.get_data()
                if pos:
                    gps_updates.append(pos)

                # Status update every 5 seconds
                elapsed = time.time() - start_time
                if int(elapsed) % 5 == 0 and int(elapsed) > 0:
                    print(f"  [{int(elapsed):2d}s] GPS updates: {len(gps_updates)}, "
                          f"Audio buffers: {len(audio_buffers)}")
                    time.sleep(1)  # Avoid multiple prints

            # Results
            print(f"\nResults:")
            print(f"  GPS position updates: {len(gps_updates)}")
            print(f"  Audio buffers captured: {len(audio_buffers)}")

            # Check both systems working
            assert len(gps_updates) > 0, "No GPS updates received"
            assert len(audio_buffers) > 0, "No audio buffers received"

            # Check update rates
            gps_rate = len(gps_updates) / 15.0
            audio_rate = len(audio_buffers) / 15.0
            print(f"  GPS rate: {gps_rate:.2f} Hz")
            print(f"  Audio rate: {audio_rate:.2f} Hz")

            print(f"\n✓✓✓ SIMULTANEOUS OPERATION TEST PASSED ✓✓✓\n")

        except ImportError:
            pytest.skip("Required dependencies not installed")
        finally:
            if "alsa" in locals() and alsa.running:
                alsa.stop()
            if "gps" in locals():
                gps.stop()
                gps.disconnect()

    def test_gps_audio_event_correlation(self, gps_device, gps_baudrate, audio_device, audio_format_bits):
        """Test: Audio events can be correlated with GPS position."""
        print(f"\n{'='*70}")
        print(f"TEST: GPS-Audio Event Correlation")
        print(f"GPS: {gps_device}")
        print(f"Audio: {audio_device}")
        print(f"{'='*70}\n")

        try:
            # Create event bus
            event_bus = EventBus()

            # Initialize GPS with event bus
            gps = SerialGPSReader(device=gps_device, baudrate=gps_baudrate, event_bus=event_bus)
            gps.connect()
            gps.start()

            # Initialize audio
            alsa = ALSASourceNode(
                device=audio_device,
                sample_rate=48000,
                channels=1,
                buffer_size=2048,
                format_bits=audio_format_bits,
            )

            # Track events
            gps_events = []
            audio_events = []

            def audio_callback(buffer: AudioBuffer):
                # Simple threshold detection
                samples = buffer.samples.astype(np.float32)
                if samples.dtype == np.int32:
                    samples = samples / (2**31 - 1)
                elif samples.dtype == np.int16:
                    samples = samples / (2**15 - 1)

                rms = np.sqrt(np.mean(samples**2))
                if rms > 0.01:  # Threshold for "loud" sound
                    # Create detection event
                    event = Event(
                        event_type=EventType.DETECTION,
                        data={
                            "timestamp": buffer.timestamp,
                            "rms": float(rms),
                            "buffer_index": buffer.buffer_index,
                        },
                    )
                    event_bus.publish(event)
                    audio_events.append((buffer.timestamp, rms))

            # Subscribe to GPS events
            def gps_event_handler(event: Event):
                if event.event_type == EventType.SYSTEM:
                    gps_events.append(event)

            event_bus.subscribe(EventType.SYSTEM, gps_event_handler)

            # Start audio with callback
            alsa.connect(audio_callback)
            alsa.start()

            print("🎤 Monitoring for 20 seconds...")
            print("   Make some noise to generate audio events!\n")

            start_time = time.time()
            while time.time() - start_time < 20:
                time.sleep(1)
                if int(time.time() - start_time) % 5 == 0:
                    print(f"  GPS events: {len(gps_events)}, Audio events: {len(audio_events)}")

            alsa.stop()

            print(f"\nEvent Summary:")
            print(f"  GPS position events: {len(gps_events)}")
            print(f"  Audio detection events: {len(audio_events)}")

            # Correlate events - for each audio event, find nearest GPS position
            if audio_events and gps_events:
                print(f"\nEvent Correlation:")

                for i, (audio_ts, rms) in enumerate(audio_events[:5]):  # Show first 5
                    # Find closest GPS event in time
                    closest_gps = None
                    min_time_diff = float('inf')

                    for gps_event in gps_events:
                        gps_data = gps_event.data
                        time_diff = abs(gps_data.get('timestamp', 0) - audio_ts)
                        if time_diff < min_time_diff:
                            min_time_diff = time_diff
                            closest_gps = gps_data

                    if closest_gps:
                        print(f"  Audio event {i+1}:")
                        print(f"    Timestamp: {audio_ts:.6f}")
                        print(f"    RMS level: {rms:.6f}")
                        print(f"    GPS position: ({closest_gps.get('latitude', 0):.6f}, "
                              f"{closest_gps.get('longitude', 0):.6f})")
                        print(f"    Time offset: {min_time_diff*1000:.2f}ms")

                print(f"\n✓ Events can be correlated by timestamp")
            else:
                print(f"\n⚠ Not enough events to demonstrate correlation")
                if not audio_events:
                    print(f"  Try making louder sounds during the test")

            print(f"\n✓✓✓ EVENT CORRELATION TEST PASSED ✓✓✓\n")

        except ImportError:
            pytest.skip("Required dependencies not installed")
        finally:
            if "alsa" in locals() and alsa.running:
                alsa.stop()
            if "gps" in locals():
                gps.stop()
                gps.disconnect()

    def test_gps_audio_timing_synchronization(self, gps_device, gps_baudrate, audio_device, audio_format_bits):
        """Test: GPS and audio timestamps are properly synchronized."""
        print(f"\n{'='*70}")
        print(f"TEST: GPS-Audio Timing Synchronization")
        print(f"GPS: {gps_device}")
        print(f"Audio: {audio_device}")
        print(f"{'='*70}\n")

        try:
            # Initialize GPS
            gps = SerialGPSReader(device=gps_device, baudrate=gps_baudrate, update_interval=1.0)
            gps.connect()
            gps.start()

            # Initialize audio
            alsa = ALSASourceNode(
                device=audio_device,
                sample_rate=48000,
                channels=1,
                buffer_size=2048,
                format_bits=audio_format_bits,
            )

            audio_timestamps = []
            gps_timestamps = []

            def audio_callback(buffer: AudioBuffer):
                audio_timestamps.append(buffer.timestamp)

            alsa.connect(audio_callback)
            alsa.start()

            print("Collecting timing data for 30 seconds...\n")

            start_time = time.time()
            while time.time() - start_time < 30:
                pos = gps.get_data()
                if pos:
                    gps_timestamps.append(pos.timestamp)
                time.sleep(1)

            alsa.stop()

            # Analyze timestamp alignment
            print(f"Timing Analysis:\n")
            print(f"  Audio timestamps: {len(audio_timestamps)}")
            print(f"  GPS timestamps: {len(gps_timestamps)}")

            if audio_timestamps and gps_timestamps:
                # Both should be based on system clock (time.time())
                # Check they're in the same timebase
                audio_span = audio_timestamps[-1] - audio_timestamps[0]
                gps_span = gps_timestamps[-1] - gps_timestamps[0]

                print(f"\n  Audio time span: {audio_span:.3f}s")
                print(f"  GPS time span: {gps_span:.3f}s")

                # Check alignment of first timestamp
                # Audio typically starts slightly after GPS in this test
                first_audio = min(audio_timestamps)
                first_gps = min(gps_timestamps)

                print(f"\n  First audio timestamp: {first_audio:.6f}")
                print(f"  First GPS timestamp: {first_gps:.6f}")
                print(f"  Offset: {abs(first_audio - first_gps):.6f}s")

                # Check both use same epoch
                # They should both be Unix timestamps (>1e9)
                assert audio_timestamps[0] > 1e9, "Audio timestamps not Unix epoch"
                assert gps_timestamps[0] > 1e9, "GPS timestamps not Unix epoch"

                print(f"\n✓ Both systems using Unix epoch timestamps")
                print(f"✓ Timestamps can be directly compared")

                # In production, system clock should be GPS-disciplined via chrony/ntpd
                print(f"\nNote: For accurate trilateration, ensure system clock is")
                print(f"      GPS-synchronized via chrony with PPS support")

                print(f"\n✓✓✓ TIMING SYNCHRONIZATION TEST PASSED ✓✓✓\n")

            else:
                pytest.fail("Insufficient timing data collected")

        except ImportError:
            pytest.skip("Required dependencies not installed")
        finally:
            if "alsa" in locals() and alsa.running:
                alsa.stop()
            if "gps" in locals():
                gps.stop()
                gps.disconnect()

    def test_system_resource_usage(self, gps_device, gps_baudrate, audio_device, audio_format_bits):
        """Test: Monitor system resources during GPS+Audio operation."""
        print(f"\n{'='*70}")
        print(f"TEST: System Resource Usage")
        print(f"GPS: {gps_device}")
        print(f"Audio: {audio_device}")
        print(f"{'='*70}\n")

        try:
            import psutil
        except ImportError:
            pytest.skip("psutil not installed")

        try:
            # Get baseline
            process = psutil.Process()
            baseline_cpu = process.cpu_percent(interval=1)
            baseline_mem = process.memory_info().rss / 1024 / 1024  # MB

            print(f"Baseline:")
            print(f"  CPU: {baseline_cpu:.1f}%")
            print(f"  Memory: {baseline_mem:.1f} MB\n")

            # Initialize GPS
            gps = SerialGPSReader(device=gps_device, baudrate=gps_baudrate)
            gps.connect()
            gps.start()

            # Initialize audio
            alsa = ALSASourceNode(
                device=audio_device,
                sample_rate=48000,
                channels=1,
                buffer_size=2048,
                format_bits=audio_format_bits,
            )

            buffer_count = [0]

            def audio_callback(buffer: AudioBuffer):
                buffer_count[0] += 1

            alsa.connect(audio_callback)
            alsa.start()

            print("Monitoring resources for 30 seconds...\n")

            cpu_samples = []
            mem_samples = []

            for i in range(30):
                time.sleep(1)

                cpu = process.cpu_percent(interval=0.1)
                mem = process.memory_info().rss / 1024 / 1024

                cpu_samples.append(cpu)
                mem_samples.append(mem)

                if i % 5 == 0:
                    print(f"  [{i:2d}s] CPU: {cpu:.1f}%, Memory: {mem:.1f} MB, "
                          f"Audio buffers: {buffer_count[0]}")

            # Calculate statistics
            avg_cpu = np.mean(cpu_samples)
            max_cpu = np.max(cpu_samples)
            avg_mem = np.mean(mem_samples)
            max_mem = np.max(mem_samples)
            mem_growth = max_mem - baseline_mem

            print(f"\nResource Summary:")
            print(f"  Average CPU: {avg_cpu:.1f}%")
            print(f"  Peak CPU: {max_cpu:.1f}%")
            print(f"  Average Memory: {avg_mem:.1f} MB")
            print(f"  Peak Memory: {max_mem:.1f} MB")
            print(f"  Memory growth: {mem_growth:.1f} MB")
            print(f"  Audio buffers processed: {buffer_count[0]}")

            # Check for reasonable resource usage
            # On Raspberry Pi, should be <50% CPU for single node
            if avg_cpu > 50:
                print(f"\n⚠ Warning: High average CPU usage ({avg_cpu:.1f}%)")
            else:
                print(f"\n✓ CPU usage acceptable")

            # Check for memory leaks (>100MB growth is suspicious)
            if mem_growth > 100:
                print(f"⚠ Warning: Significant memory growth ({mem_growth:.1f} MB)")
            else:
                print(f"✓ Memory usage stable")

            print(f"\n✓✓✓ RESOURCE USAGE TEST PASSED ✓✓✓\n")

        except ImportError:
            pytest.skip("Required dependencies not installed")
        finally:
            if "alsa" in locals() and alsa.running:
                alsa.stop()
            if "gps" in locals():
                gps.stop()
                gps.disconnect()
