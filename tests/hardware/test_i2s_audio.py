"""Hardware tests for I2S microphone via ALSA.

These tests require a physical I2S microphone configured as an ALSA device.
Run with: pytest tests/hardware/test_i2s_audio.py -v -s
"""

import logging
import time
from pathlib import Path

import numpy as np
import pytest

from src.audio.audio_nodes import ALSASourceNode, AudioBuffer

# Configure verbose logging for hardware tests
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

pytestmark = [pytest.mark.hardware, pytest.mark.audio]


class TestI2SAudioHardware:
    """Hardware tests for I2S microphone."""

    def test_alsa_device_info(self, audio_device):
        """Test: ALSA device can be enumerated and inspected."""
        print(f"\n{'='*70}")
        print(f"TEST: ALSA Device Information")
        print(f"Device: {audio_device}")
        print(f"{'='*70}\n")

        try:
            import pyaudio
        except ImportError:
            pytest.skip("pyaudio not installed")

        pa = pyaudio.PyAudio()

        try:
            print(f"Available Audio Devices:\n")
            default_device = pa.get_default_input_device_info()
            print(f"Default Input Device: {default_device['name']} (index: {default_device['index']})")
            print(f"  Max channels: {default_device['maxInputChannels']}")
            print(f"  Default sample rate: {default_device['defaultSampleRate']}")
            print()

            # List all input devices
            device_count = pa.get_device_count()
            for i in range(device_count):
                info = pa.get_device_info_by_index(i)
                if info['maxInputChannels'] > 0:
                    print(f"Device {i}: {info['name']}")
                    print(f"  Max channels: {info['maxInputChannels']}")
                    print(f"  Default sample rate: {info['defaultSampleRate']}")
                    print()

            # Try to find the requested device
            if audio_device != "default":
                found = False
                for i in range(device_count):
                    info = pa.get_device_info_by_index(i)
                    if audio_device in info['name']:
                        found = True
                        print(f"✓ Found requested device: {info['name']}")
                        break

                if not found:
                    print(f"⚠ Warning: Device '{audio_device}' not found by name")
                    print(f"  Available devices listed above")

            print(f"\n✓✓✓ DEVICE INFO TEST PASSED ✓✓✓\n")

        finally:
            pa.terminate()

    @pytest.mark.slow
    def test_alsa_capture_start(self, audio_device, audio_format_bits):
        """Test: I2S microphone can be opened and started."""
        print(f"\n{'='*70}")
        print(f"TEST: Audio Capture Initialization")
        print(f"Device: {audio_device}")
        print(f"Format: {audio_format_bits}-bit")
        print(f"{'='*70}\n")

        try:
            alsa = ALSASourceNode(
                device=audio_device,
                sample_rate=48000,
                channels=1,
                buffer_size=1024,
                format_bits=audio_format_bits,
            )
            print(f"✓ ALSASourceNode created")

            alsa.start()
            print(f"✓ Audio capture started")

            assert alsa.running
            assert alsa.stream is not None
            assert alsa.pa is not None

            # Give it a moment to stabilize
            time.sleep(1)

            print(f"\nStream Info:")
            print(f"  Sample rate: {alsa.sample_rate} Hz")
            print(f"  Channels: {alsa.channels}")
            print(f"  Buffer size: {alsa.buffer_size} samples")
            print(f"  Buffer duration: {alsa.buffer_size/alsa.sample_rate*1000:.1f}ms")

            print(f"\n✓✓✓ CAPTURE START TEST PASSED ✓✓✓\n")

        except ImportError:
            pytest.skip("pyaudio not installed")
        except (OSError, IOError) as e:
            pytest.fail(
                f"Failed to open audio device '{audio_device}'\n"
                f"Error: {e}\n"
                f"Check:\n"
                f"  - Run 'arecord -l' to list devices\n"
                f"  - Verify I2S overlay in /boot/config.txt (dtoverlay=i2s-mems)\n"
                f"  - Try different device: --audio-device='hw:1,0'\n"
                f"  - Try different format: --format-bits=16 or --format-bits=24"
            )
        finally:
            if "alsa" in locals():
                alsa.stop()

    @pytest.mark.slow
    def test_alsa_buffer_capture(self, audio_device, audio_format_bits):
        """Test: Audio buffers can be captured with correct format."""
        print(f"\n{'='*70}")
        print(f"TEST: Audio Buffer Capture")
        print(f"Device: {audio_device}")
        print(f"{'='*70}\n")

        try:
            alsa = ALSASourceNode(
                device=audio_device,
                sample_rate=48000,
                channels=1,
                buffer_size=1024,
                format_bits=audio_format_bits,
            )

            buffers_captured = []

            def capture_callback(buffer: AudioBuffer):
                buffers_captured.append(buffer)

            alsa.connect(capture_callback)
            alsa.start()

            print("Capturing audio for 5 seconds...\n")
            time.sleep(5)

            alsa.stop()

            print(f"Capture Results:")
            print(f"  Buffers captured: {len(buffers_captured)}")

            if buffers_captured:
                # Calculate expected buffer count
                buffer_duration = alsa.buffer_size / alsa.sample_rate
                expected_count = int(5.0 / buffer_duration)
                print(f"  Expected ~{expected_count} buffers")

                # Check buffer properties
                first_buffer = buffers_captured[0]
                last_buffer = buffers_captured[-1]

                print(f"\nBuffer Properties:")
                print(f"  Sample rate: {first_buffer.sample_rate} Hz")
                print(f"  Channels: {first_buffer.channels}")
                print(f"  Samples per buffer: {len(first_buffer.samples)}")
                print(f"  Duration per buffer: {first_buffer.duration*1000:.2f}ms")
                print(f"  Data type: {first_buffer.samples.dtype}")
                print(f"  Shape: {first_buffer.samples.shape}")

                # Check timing
                time_span = last_buffer.timestamp - first_buffer.timestamp
                print(f"\nTiming:")
                print(f"  First timestamp: {first_buffer.timestamp:.6f}")
                print(f"  Last timestamp: {last_buffer.timestamp:.6f}")
                print(f"  Time span: {time_span:.3f}s")

                # Verify buffers
                assert len(buffers_captured) > 0, "No buffers captured"
                assert first_buffer.sample_rate == 48000
                assert first_buffer.channels == 1
                assert len(first_buffer.samples) == 1024

                print(f"\n✓✓✓ BUFFER CAPTURE TEST PASSED ✓✓✓\n")
            else:
                pytest.fail("No audio buffers captured")

        except ImportError:
            pytest.skip("pyaudio not installed")
        finally:
            if "alsa" in locals() and alsa.running:
                alsa.stop()

    @pytest.mark.slow
    def test_alsa_audio_signal_quality(self, audio_device, audio_format_bits):
        """Test: Captured audio has reasonable signal characteristics."""
        print(f"\n{'='*70}")
        print(f"TEST: Audio Signal Quality")
        print(f"Device: {audio_device}")
        print(f"{'='*70}\n")

        try:
            alsa = ALSASourceNode(
                device=audio_device,
                sample_rate=48000,
                channels=1,
                buffer_size=2048,
                format_bits=audio_format_bits,
            )

            buffers_captured = []

            def capture_callback(buffer: AudioBuffer):
                buffers_captured.append(buffer)

            alsa.connect(capture_callback)
            alsa.start()

            print("🎤 Recording for 10 seconds...")
            print("   (Make some noise - talk, clap, tap the mic)\n")
            time.sleep(10)

            alsa.stop()

            if not buffers_captured:
                pytest.fail("No buffers captured")

            # Analyze signal quality
            print(f"Signal Analysis:\n")

            # Combine all samples for analysis
            all_samples = np.concatenate([b.samples for b in buffers_captured])

            # Normalize to float if needed
            if all_samples.dtype == np.int32:
                samples_float = all_samples.astype(np.float32) / (2**31 - 1)
            elif all_samples.dtype == np.int16:
                samples_float = all_samples.astype(np.float32) / (2**15 - 1)
            else:
                samples_float = all_samples.astype(np.float32)

            # Calculate statistics
            rms = np.sqrt(np.mean(samples_float**2))
            peak = np.max(np.abs(samples_float))
            dc_offset = np.mean(samples_float)
            dynamic_range_db = 20 * np.log10(peak / (rms + 1e-10))

            print(f"  RMS level: {rms:.6f} ({20*np.log10(rms + 1e-10):.1f} dB)")
            print(f"  Peak level: {peak:.6f} ({20*np.log10(peak + 1e-10):.1f} dB)")
            print(f"  DC offset: {dc_offset:.6f}")
            print(f"  Dynamic range: {dynamic_range_db:.1f} dB")

            # Check for clipping
            clipping_threshold = 0.99
            clipped_samples = np.sum(np.abs(samples_float) > clipping_threshold)
            clipping_percentage = (clipped_samples / len(samples_float)) * 100
            print(f"  Clipping: {clipped_samples} samples ({clipping_percentage:.3f}%)")

            # Check for silence (might indicate mic not working)
            silence_threshold = 0.001  # Very quiet
            if rms < silence_threshold:
                print(f"\n⚠ Warning: Signal very quiet (RMS < {silence_threshold})")
                print(f"  Check:")
                print(f"    - Microphone is connected")
                print(f"    - Correct ALSA device selected")
                print(f"    - Mic gain settings (alsamixer)")
            else:
                print(f"\n✓ Signal detected")

            # Check for DC offset issues
            if abs(dc_offset) > 0.1:
                print(f"⚠ Warning: Large DC offset detected ({dc_offset:.6f})")
                print(f"  Consider using DC removal filter")
            else:
                print(f"✓ DC offset acceptable")

            # Check for clipping
            if clipping_percentage > 0.1:
                print(f"⚠ Warning: Clipping detected ({clipping_percentage:.3f}%)")
                print(f"  Reduce input gain")
            else:
                print(f"✓ No significant clipping")

            # Basic assertion - signal should exist
            assert rms > 1e-6, "No audio signal detected (microphone may not be working)"

            print(f"\n✓✓✓ SIGNAL QUALITY TEST PASSED ✓✓✓\n")

        except ImportError:
            pytest.skip("pyaudio not installed")
        finally:
            if "alsa" in locals() and alsa.running:
                alsa.stop()

    @pytest.mark.slow
    def test_alsa_timing_precision(self, audio_device, audio_format_bits):
        """Test: Audio buffer timestamps are accurate and stable."""
        print(f"\n{'='*70}")
        print(f"TEST: Audio Timing Precision")
        print(f"Device: {audio_device}")
        print(f"{'='*70}\n")

        try:
            alsa = ALSASourceNode(
                device=audio_device,
                sample_rate=48000,
                channels=1,
                buffer_size=1024,
                format_bits=audio_format_bits,
            )

            timestamps = []

            def capture_callback(buffer: AudioBuffer):
                timestamps.append(buffer.timestamp)

            alsa.connect(capture_callback)
            alsa.start()

            print("Collecting timestamps for 20 seconds...\n")
            time.sleep(20)

            alsa.stop()

            if len(timestamps) < 2:
                pytest.fail("Not enough timestamps captured")

            # Calculate inter-buffer intervals
            intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]

            expected_interval = alsa.buffer_size / alsa.sample_rate
            mean_interval = np.mean(intervals)
            std_interval = np.std(intervals)
            min_interval = np.min(intervals)
            max_interval = np.max(intervals)

            print(f"Timing Analysis ({len(timestamps)} buffers):\n")
            print(f"  Expected interval: {expected_interval*1000:.3f}ms")
            print(f"  Mean interval: {mean_interval*1000:.3f}ms")
            print(f"  Std deviation: {std_interval*1000:.3f}ms")
            print(f"  Min interval: {min_interval*1000:.3f}ms")
            print(f"  Max interval: {max_interval*1000:.3f}ms")

            # Calculate jitter
            jitter = std_interval / mean_interval * 100
            print(f"  Jitter: {jitter:.2f}%")

            # Check interval accuracy
            interval_error = abs(mean_interval - expected_interval) / expected_interval * 100
            print(f"  Interval error: {interval_error:.2f}%")

            # Check for timing anomalies
            # Allow some variance due to OS scheduling
            if std_interval > expected_interval * 0.5:
                print(f"\n⚠ Warning: High timing variance detected")
                print(f"  This may affect timestamp accuracy for trilateration")
            else:
                print(f"\n✓ Timing variance acceptable")

            # Check monotonicity
            is_monotonic = all(i > 0 for i in intervals)
            if is_monotonic:
                print(f"✓ Timestamps monotonically increasing")
            else:
                print(f"⚠ Warning: Non-monotonic timestamps detected")

            assert is_monotonic, "Timestamps not monotonically increasing"

            print(f"\n✓✓✓ TIMING PRECISION TEST PASSED ✓✓✓\n")

        except ImportError:
            pytest.skip("pyaudio not installed")
        finally:
            if "alsa" in locals() and alsa.running:
                alsa.stop()

    @pytest.mark.slow
    def test_alsa_save_sample_recording(self, audio_device, audio_format_bits, tmp_path):
        """Test: Capture and save a sample recording for analysis."""
        print(f"\n{'='*70}")
        print(f"TEST: Sample Recording Capture")
        print(f"Device: {audio_device}")
        print(f"{'='*70}\n")

        try:
            import soundfile as sf
        except ImportError:
            pytest.skip("soundfile not installed")

        try:
            alsa = ALSASourceNode(
                device=audio_device,
                sample_rate=48000,
                channels=1,
                buffer_size=2048,
                format_bits=audio_format_bits,
            )

            buffers_captured = []

            def capture_callback(buffer: AudioBuffer):
                buffers_captured.append(buffer)

            alsa.connect(capture_callback)
            alsa.start()

            duration = 5
            print(f"🎤 Recording for {duration} seconds...")
            print(f"   (Make some noise to test detection)\n")
            time.sleep(duration)

            alsa.stop()

            if not buffers_captured:
                pytest.fail("No buffers captured")

            # Combine all samples
            all_samples = np.concatenate([b.samples for b in buffers_captured])

            # Normalize to float32 for saving
            if all_samples.dtype == np.int32:
                samples_float = all_samples.astype(np.float32) / (2**31 - 1)
            elif all_samples.dtype == np.int16:
                samples_float = all_samples.astype(np.float32) / (2**15 - 1)
            else:
                samples_float = all_samples.astype(np.float32)

            # Save to file
            output_dir = Path("tests/hardware/output")
            output_dir.mkdir(exist_ok=True)
            output_file = output_dir / "test_recording.wav"

            sf.write(output_file, samples_float, 48000)

            print(f"Recording saved to: {output_file}")
            print(f"  Duration: {len(samples_float)/48000:.2f}s")
            print(f"  Sample rate: 48000 Hz")
            print(f"  Samples: {len(samples_float)}")
            print(f"  File size: {output_file.stat().st_size / 1024:.1f} KB")

            print(f"\n✓ You can play this file to verify: aplay {output_file}")
            print(f"✓✓✓ SAMPLE RECORDING TEST PASSED ✓✓✓\n")

        except ImportError:
            pytest.skip("Required dependencies not installed")
        finally:
            if "alsa" in locals() and alsa.running:
                alsa.stop()
