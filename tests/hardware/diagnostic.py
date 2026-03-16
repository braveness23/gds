#!/usr/bin/env python3
"""Quick hardware diagnostic tool.

Run this before the full test suite to verify hardware is properly connected.
Usage: python tests/hardware/diagnostic.py
"""

import logging
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def check_serial_devices():
    """Check for available serial devices."""
    print("\n" + "="*70)
    print("SERIAL DEVICES CHECK")
    print("="*70)

    try:
        import glob
        devices = glob.glob('/dev/tty[AU]*') + glob.glob('/dev/serial*')

        if devices:
            print(f"✓ Found {len(devices)} serial device(s):")
            for dev in devices:
                print(f"  - {dev}")
        else:
            print("⚠ No serial devices found")
            print("  Common GPS device paths:")
            print("    /dev/ttyUSB0  (USB GPS)")
            print("    /dev/ttyACM0  (USB GPS)")
            print("    /dev/serial0  (Raspberry Pi GPIO UART)")

        return len(devices) > 0

    except Exception as e:
        print(f"✗ Error checking serial devices: {e}")
        return False


def check_gps_dependencies():
    """Check GPS-related dependencies."""
    print("\n" + "="*70)
    print("GPS DEPENDENCIES CHECK")
    print("="*70)

    all_ok = True

    # Check pyserial
    try:
        import serial
        print(f"✓ pyserial: {serial.__version__}")
    except ImportError:
        print("✗ pyserial not installed")
        print("  Install: pip install pyserial")
        all_ok = False

    # Check pynmea2
    try:
        import pynmea2
        print(f"✓ pynmea2: {pynmea2.__version__}")
    except ImportError:
        print("✗ pynmea2 not installed")
        print("  Install: pip install pynmea2")
        all_ok = False

    return all_ok


def check_gps_connection(device="/dev/serial0", baudrate=9600):
    """Test GPS device connection."""
    print("\n" + "="*70)
    print("GPS CONNECTION TEST")
    print(f"Device: {device}")
    print(f"Baudrate: {baudrate}")
    print("="*70)

    try:
        import serial
    except ImportError:
        print("✗ pyserial not installed, skipping")
        return False

    try:
        ser = serial.Serial(device, baudrate, timeout=5)
        print(f"✓ Opened {device}")

        print("\nReading GPS data for 10 seconds...")
        print("(If you see $GP... sentences, GPS is working)\n")

        start_time = time.time()
        sentence_count = 0

        while time.time() - start_time < 10:
            try:
                line = ser.readline().decode(errors='ignore').strip()
                if line.startswith('$'):
                    sentence_count += 1
                    if sentence_count <= 3:
                        print(f"  {line}")
                    elif sentence_count == 4:
                        print("  ... (more sentences)")
            except Exception as e:
                print(f"  Read error: {e}")
                break

        ser.close()

        if sentence_count > 0:
            print(f"\n✓ Received {sentence_count} NMEA sentences")
            return True
        else:
            print(f"\n✗ No NMEA sentences received")
            print("  Check:")
            print("    - GPS module has power")
            print("    - Correct device path")
            print("    - Correct baud rate (try 4800, 9600, 38400, 115200)")
            return False

    except Exception as e:
        print(f"✗ Failed to open GPS: {e}")
        print("  Check:")
        print("    - Device exists: ls -l /dev/tty*")
        print("    - Permissions: sudo usermod -a -G dialout $USER")
        print("    - Log out and back in after adding to group")
        return False


def check_alsa_devices():
    """Check for ALSA audio devices."""
    print("\n" + "="*70)
    print("ALSA DEVICES CHECK")
    print("="*70)

    try:
        import subprocess
        result = subprocess.run(['arecord', '-l'], capture_output=True, text=True)

        if result.returncode == 0:
            print("✓ ALSA devices:")
            print(result.stdout)
            return True
        else:
            print("⚠ Could not list ALSA devices")
            return False

    except FileNotFoundError:
        print("✗ arecord command not found (ALSA tools not installed)")
        print("  Install: sudo apt install alsa-utils")
        return False
    except Exception as e:
        print(f"✗ Error checking ALSA: {e}")
        return False


def check_audio_dependencies():
    """Check audio-related dependencies."""
    print("\n" + "="*70)
    print("AUDIO DEPENDENCIES CHECK")
    print("="*70)

    all_ok = True

    # Check pyaudio
    try:
        import pyaudio
        print(f"✓ pyaudio: {pyaudio.__version__}")
    except ImportError:
        print("✗ pyaudio not installed")
        print("  Install: pip install pyaudio")
        all_ok = False

    # Check numpy
    try:
        import numpy as np
        print(f"✓ numpy: {np.__version__}")
    except ImportError:
        print("✗ numpy not installed")
        print("  Install: pip install numpy")
        all_ok = False

    # Check soundfile
    try:
        import soundfile as sf
        print(f"✓ soundfile: {sf.__version__}")
    except ImportError:
        print("⚠ soundfile not installed (optional, for saving recordings)")
        print("  Install: pip install soundfile")

    return all_ok


def check_audio_capture(device="default"):
    """Test audio capture."""
    print("\n" + "="*70)
    print("AUDIO CAPTURE TEST")
    print(f"Device: {device}")
    print("="*70)

    try:
        import pyaudio
    except ImportError:
        print("✗ pyaudio not installed, skipping")
        return False

    pa = pyaudio.PyAudio()

    try:
        # List devices
        print("\nAvailable input devices:")
        device_count = pa.get_device_count()
        for i in range(device_count):
            info = pa.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                print(f"  [{i}] {info['name']}")
                print(f"      Channels: {info['maxInputChannels']}, "
                      f"Rate: {info['defaultSampleRate']}")

        # Try to open device
        print(f"\nTesting capture from '{device}'...")

        try:
            stream = pa.open(
                format=pyaudio.paInt32,
                channels=1,
                rate=48000,
                input=True,
                frames_per_buffer=1024,
            )

            print("✓ Audio capture started")

            # Read a few buffers
            print("\nReading audio for 3 seconds...")
            for i in range(3):
                data = stream.read(1024)
                print(f"  Buffer {i+1}: {len(data)} bytes")
                time.sleep(1)

            stream.stop_stream()
            stream.close()

            print("\n✓ Audio capture successful")
            return True

        except Exception as e:
            print(f"\n✗ Failed to open audio device: {e}")
            print("  Try:")
            print("    - Different device: arecord -l")
            print("    - Check I2S overlay: cat /boot/config.txt | grep i2s")
            print("    - Test with arecord: arecord -D hw:1,0 -f S32_LE -r 48000 test.wav")
            return False

    finally:
        pa.terminate()


def main():
    """Run all diagnostic checks."""
    print("\n" + "="*70)
    print("HARDWARE DIAGNOSTIC TOOL")
    print("strix")
    print("="*70)

    results = {}

    # GPS checks
    results['serial_devices'] = check_serial_devices()
    results['gps_deps'] = check_gps_dependencies()

    if results['serial_devices'] and results['gps_deps']:
        # Allow custom device via command line
        gps_device = sys.argv[1] if len(sys.argv) > 1 else "/dev/serial0"
        results['gps_connection'] = check_gps_connection(gps_device)
    else:
        results['gps_connection'] = False
        print("\nSkipping GPS connection test (missing dependencies or devices)")

    # Audio checks
    results['alsa_devices'] = check_alsa_devices()
    results['audio_deps'] = check_audio_dependencies()

    if results['alsa_devices'] and results['audio_deps']:
        audio_device = sys.argv[2] if len(sys.argv) > 2 else "default"
        results['audio_capture'] = check_audio_capture(audio_device)
    else:
        results['audio_capture'] = False
        print("\nSkipping audio capture test (missing dependencies or devices)")

    # Summary
    print("\n" + "="*70)
    print("DIAGNOSTIC SUMMARY")
    print("="*70)

    for check, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {check}")

    all_passed = all(results.values())

    if all_passed:
        print("\n✓✓✓ ALL CHECKS PASSED ✓✓✓")
        print("\nYou can now run the full hardware test suite:")
        print("  pytest tests/hardware/ -v -s")
        return 0
    else:
        print("\n⚠ SOME CHECKS FAILED")
        print("\nFix the issues above before running hardware tests")
        print("\nFor help:")
        print("  - GPS: cat tests/hardware/README.md")
        print("  - Audio: cat tests/hardware/README.md")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nDiagnostic interrupted")
        sys.exit(130)
