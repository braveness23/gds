# Hardware Tests

This directory contains tests for physical hardware on Raspberry Pi.

## Hardware Requirements

- **GPS**: Serial GPS module connected to Raspberry Pi (e.g., `/dev/ttyUSB0`, `/dev/ttyACM0`, `/dev/serial0`)
- **Audio**: I2S microphone configured as ALSA device (e.g., `hw:1,0` or named device)

## Running Tests

### Run all hardware tests:
```bash
pytest tests/hardware/ -v -s
```

### Run specific hardware test:
```bash
# GPS only
pytest tests/hardware/test_serial_gps.py -v -s

# Audio only
pytest tests/hardware/test_i2s_audio.py -v -s

# Integration
pytest tests/hardware/test_integration.py -v -s
```

### Run with custom device paths:
```bash
# GPS on different port
pytest tests/hardware/test_serial_gps.py -v -s --gps-device=/dev/ttyUSB0

# I2S mic on specific card
pytest tests/hardware/test_i2s_audio.py -v -s --audio-device="hw:1,0"
```

## Test Markers

Tests use pytest markers for categorization:
- `@pytest.mark.hardware` - Requires physical hardware
- `@pytest.mark.gps` - Requires GPS module
- `@pytest.mark.audio` - Requires microphone
- `@pytest.mark.slow` - May take >10 seconds

Skip hardware tests in CI:
```bash
pytest -m "not hardware"
```

## Troubleshooting

### GPS Issues

**No data from GPS:**
```bash
# Check device exists
ls -l /dev/tty* | grep -E 'USB|ACM|serial'

# Test direct read
cat /dev/ttyUSB0  # Should see NMEA sentences

# Check permissions
sudo usermod -a -G dialout $USER  # Add yourself to dialout group
# Log out and back in

# Test with different baud rates (common: 4800, 9600, 38400, 115200)
pytest tests/hardware/test_serial_gps.py -v -s --baudrate=4800
```

**GPS not getting fix:**
- Ensure antenna has clear sky view
- Wait 30-60 seconds for cold start
- Tests will wait up to 120 seconds by default

### Audio Issues

**No audio device:**
```bash
# List ALSA devices
arecord -l

# Test recording
arecord -D hw:1,0 -f S32_LE -r 48000 -c 1 -d 5 test.wav

# Check I2S configuration
cat /boot/config.txt | grep dtoverlay
# Should have: dtoverlay=i2s-mems
```

**Wrong sample format:**
I2S mics typically use 32-bit samples. Try:
```bash
pytest tests/hardware/test_i2s_audio.py -v -s --format-bits=32
```

## Test Output

Tests provide verbose diagnostics:
- GPS: Fix status, satellite count, position accuracy
- Audio: Device info, buffer timing, signal levels
- Integration: Timestamp synchronization, event correlation

All tests save artifacts to `tests/hardware/output/` for analysis.
