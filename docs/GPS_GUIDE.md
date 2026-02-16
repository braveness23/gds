# GPS and PPS Timing Guide

Complete guide for GPS positioning and PPS timing synchronization on Raspberry Pi.

## Table of Contents

1. [Overview](#overview)
2. [Hardware Setup](#hardware-setup)
3. [Software Setup](#software-setup)
4. [PPS Timing Setup](#pps-timing-setup)
5. [Using GPS in Code](#using-gps-in-code)
6. [Testing and Verification](#testing-and-verification)
7. [Troubleshooting](#troubleshooting)
8. [Best Practices](#best-practices)

---

## Overview

GPS provides three critical capabilities for gunshot detection:

- **Node location** - Latitude, longitude, altitude for trilateration
- **Position updates** - Real-time tracking for mobile nodes
- **PPS timing** - Microsecond-accurate clock synchronization

### What You'll Have

**Hardware:**
- GPS module connected to Pi UART (usually `/dev/ttyAMA0`)
- PPS signal connected to GPIO (typically GPIO 18)

**Software Stack:**
```
GPS Module
    ├─ NMEA sentences ──→ gpsd ──→ provides lat/lon/alt
    └─ PPS pulses ──→ kernel ──→ chrony/ntpd ──→ disciplines system clock
```

**Result:**
- Position accuracy: 2-5m (standard GPS) or <1cm (RTK)
- Time accuracy: <1 microsecond (with PPS)
- All timestamps automatically GPS-synchronized

---

## Hardware Setup

### GPS Module Options

**Recommended: U-blox NEO-6M or NEO-M8N**
- Cost: $10-$20
- Accuracy: 2.5m CEP
- Update rate: 1-10 Hz
- UART interface
- PPS output available

**Budget: GT-U7 (U-blox 7)**
- Cost: $5-$10
- Accuracy: 2.5m CEP
- Update rate: 1 Hz
- Basic UART interface

**High-end: U-blox ZED-F9P (RTK)**
- Cost: $200+
- Accuracy: <1cm with RTK
- Update rate: 10 Hz
- Dual-band (L1/L2)
- Best for surveying node positions

### Wiring to Raspberry Pi

**UART Connection (most common):**
```
GPS Module          Raspberry Pi
VCC (3.3V)    →     Pin 1 (3.3V)
GND           →     Pin 6 (GND)
TX            →     Pin 10 (GPIO 15, RXD)
RX            →     Pin 8 (GPIO 14, TXD)
PPS           →     Pin 12 (GPIO 18) [optional, for timing]
```

**USB Connection (alternative):**
```
GPS with USB adapter → Raspberry Pi USB port
Device appears as: /dev/ttyUSB0 or /dev/ttyACM0
```

---

## Software Setup

### 1. Enable UART

```bash
# Edit boot config
sudo nano /boot/firmware/config.txt

# Add or modify these lines:
enable_uart=1
dtoverlay=disable-bt  # If using Pi with Bluetooth (optional)

# Save and reboot
sudo reboot
```

### 2. Install gpsd

```bash
# Install gpsd and tools
sudo apt update
sudo apt install gpsd gpsd-clients python3-gps

# Verify installation
gpsd -V
```

### 3. Configure gpsd

```bash
# Edit gpsd configuration
sudo nano /etc/default/gpsd

# Set these values:
START_DAEMON="true"
USBAUTO="true"
DEVICES="/dev/ttyAMA0"  # Or /dev/ttyUSB0 for USB GPS
GPSD_OPTIONS="-n -G"
```

**Device options:**
- `/dev/ttyAMA0` - Primary UART on Pi 3/4/5
- `/dev/serial0` - Alias that always points to primary UART
- `/dev/ttyUSB0` - USB GPS adapter
- `/dev/ttyACM0` - USB GPS adapter (alternative)

**GPSD_OPTIONS:**
- `-n` - Don't wait for client to connect before polling GPS
- `-G` - Listen on all network interfaces (for remote access)

### 4. Start and Enable gpsd

```bash
# Stop any running instance
sudo systemctl stop gpsd
sudo systemctl stop gpsd.socket

# Start fresh
sudo systemctl start gpsd
sudo systemctl start gpsd.socket

# Enable on boot
sudo systemctl enable gpsd

# Check status
sudo systemctl status gpsd
```

---

## PPS Timing Setup

PPS (Pulse Per Second) provides microsecond-accurate time synchronization.

### TL;DR - What You Need to Know

Once PPS is configured, your system clock is GPS-synchronized automatically:

**✅ DO THIS:**
```python
import time

# Capture timestamp - it's already GPS-accurate!
timestamp = time.time()

# Or for even better precision
timestamp = time.clock_gettime(time.CLOCK_REALTIME)
```

**❌ DON'T DO THIS:**
```python
# You DON'T need to read /dev/pps0 directly
# The system clock is already PPS-synchronized
```

### 1. Enable PPS Kernel Module

```bash
# Edit boot config
sudo nano /boot/firmware/config.txt

# Add:
dtoverlay=pps-gpio,gpiopin=18

# Reboot
sudo reboot
```

### 2. Verify PPS Device

```bash
# Check device exists
ls -l /dev/pps0

# Test PPS pulses
sudo ppstest /dev/pps0

# Should show pulses every second:
# source 0 - assert 1707436789.000000123, sequence: 12345
```

### 3. Configure Chrony (Time Synchronization)

```bash
# Install chrony
sudo apt install chrony pps-tools

# Edit chrony config
sudo nano /etc/chrony/chrony.conf

# Add these lines:
refclock PPS /dev/pps0 refid PPS lock NMEA
refclock SHM 0 offset 0.0 delay 0.2 refid NMEA

# Restart chrony
sudo systemctl restart chrony

# Disable conflicting time services
sudo systemctl disable systemd-timesyncd
sudo systemctl stop systemd-timesyncd
```

### 4. Verify Time Synchronization

```bash
# Check chrony sources
chronyc sources -v

# Look for output like:
# MS Name/IP address         Stratum Poll Reach LastRx Last sample
# ========================================================================
# #* PPS0                           0   4   377     6    +12ns[  +32ns] +/-   94ns
# ^- 192.168.1.1                    2   6   377    23  +1.2ms[+1.3ms] +/-   45ms
```

**What this means:**
- `#*` = PPS is the primary time source (excellent!)
- `+/-   94ns` = Clock accuracy is 94 nanoseconds
- Second line is network NTP (fallback if PPS fails)

### Timestamp Accuracy Analysis

**Sound travel distance for 100ns time uncertainty:**
```
Speed of sound: 343 m/s
Time: 100 nanoseconds = 0.0000001 seconds
Distance: 343 × 0.0000001 = 0.0000343 meters = 34.3 micrometers
```

That's **34 microns** - about the width of a human hair!

**Practical uncertainty sources (in order of impact):**

1. **Audio buffer timing** (~1-10ms = 0.34-3.4 meters) - Dominant error
2. **Network latency** (1-100ms = 0.34-34 meters)
3. **Temperature/humidity** (~0.6% = 2m per 100m)
4. **Microphone position error** (2-5 meters with standard GPS)
5. **PPS timing** (<1 microsecond = 0.3mm) - Negligible!

**Conclusion:** PPS gives amazing time accuracy. Your limiting factors are elsewhere.

---

## Using GPS in Code

### Configuration

```yaml
# config.yaml

sensors:
  gps:
    enabled: true              # Use real GPS
    host: "localhost"          # gpsd host
    port: 2947                 # gpsd port
    update_interval: 1.0       # Poll rate (seconds)

# Fallback location (used if GPS disabled or unavailable)
location:
  latitude: 37.7749
  longitude: -122.4194
  altitude: 10.0

# Timing
timing:
  use_system_clock: true       # System clock is PPS-disciplined
  verify_sync: true            # Alert if not synced
  verify_interval: 60          # Check every 60 seconds
```

### Basic Usage

```python
from sensors.gps import GPSReader, create_gps_reader
from core.event_bus import get_event_bus

# Create GPS reader
event_bus = get_event_bus()
gps = GPSReader(event_bus=event_bus)

# Connect and start
gps.connect()
gps.start()

# Wait for fix
if gps.wait_for_fix(timeout=60):
    print("GPS ready!")

    # Get current position
    position = gps.get_position()
    print(f"Location: ({position.latitude}, {position.longitude})")
else:
    print("GPS timeout - no fix")

# Stop when done
gps.stop()
```

### With Callback

```python
def on_position_update(position):
    if position.has_fix:
        print(f"Updated: ({position.latitude:.6f}, {position.longitude:.6f})")

gps.add_callback(on_position_update)
gps.start()
```

### Using GPS-Synchronized Time

```python
import time

class ALSASourceNode:
    def _audio_callback(self, in_data, frame_count, time_info, status):
        # System clock is already PPS-synchronized!
        timestamp = time.time()

        # Process audio...
        buffer = AudioBuffer(
            samples=samples,
            timestamp=timestamp,  # GPS-accurate timestamp!
            sample_rate=self.sample_rate,
            channels=self.channels,
            buffer_index=self.buffer_index
        )

        self.emit(buffer)
```

### Factory Function (Recommended)

```python
from sensors.gps import create_gps_reader
from config.config import Config

# Automatically chooses GPS or static based on config
config = Config('config.yaml')
gps = create_gps_reader(config, event_bus)

gps.connect()
gps.start()
```

### Alternative Implementations

**Static Location (Fallback):**
```python
from sensors.static_gps import StaticGPSDevice

# For testing or fixed installations
gps = StaticGPSDevice(
    latitude=37.7749,
    longitude=-122.4194,
    altitude=10.0
)

position = gps._read_sensor()
```

**Mock GPS (Testing):**
```python
from sensors.mock_gps import MockGPSDevice

# For unit tests or simulation
gps = MockGPSDevice(
    latitude=37.0,
    longitude=-122.0,
    altitude=10.0,
    move=True
)
position = gps._read_sensor()
```

### GPS Data Structure

```python
@dataclass
class GPSData:
    latitude: float       # Decimal degrees (-90 to 90)
    longitude: float      # Decimal degrees (-180 to 180)
    altitude: float       # Meters above sea level
    timestamp: float      # Unix timestamp
    fix_quality: int      # 0=none, 1=GPS, 2=DGPS, 3=PPS, 4=RTK
    satellites: int       # Number in view
    hdop: float          # Horizontal dilution of precision
    speed: float         # Speed in m/s
    track: float         # Direction in degrees
```

---

## Testing and Verification

### Quick Test with cgps

```bash
# Terminal UI for GPS
cgps -s

# You should see:
# - Latitude/Longitude updating
# - Satellites in view
# - Fix type (3D fix is best)
```

**Expected output:**
```
┌───────────────────────────────────────────┐
│    Time:       2024-02-09T23:45:12.000Z  │
│    Latitude:   37.774900 N               │
│    Longitude:  122.419400 W              │
│    Altitude:   10.5 m                    │
│    Speed:      0.0 m/s                   │
│    Heading:    0.0 deg                   │
│    Climb:      0.0 m/s                   │
│    Status:     3D FIX (4/9 satellites)   │
│    HDOP:       1.2                       │
└───────────────────────────────────────────┘
```

### Test with gpsmon

```bash
# Detailed GPS monitor
gpsmon

# Shows:
# - Raw NMEA sentences
# - Satellite info
# - Signal strength
```

### Test with Project Tool

```bash
# Check system status
python tools/gps_test.py --check

# Test connection
python tools/gps_test.py --test

# Monitor for 30 seconds
python tools/gps_test.py --monitor 30

# Interactive mode
python tools/gps_test.py --interactive
```

### Test Timestamp Precision

```python
# test_timing.py

import time
import numpy as np

def test_timestamp_precision():
    """Measure timestamp precision."""
    timestamps = []

    # Capture 1000 timestamps as fast as possible
    for _ in range(1000):
        timestamps.append(time.time())

    # Calculate intervals
    intervals = np.diff(timestamps)

    print(f"Min interval: {intervals.min() * 1e6:.3f} μs")
    print(f"Max interval: {intervals.max() * 1e6:.3f} μs")
    print(f"Mean interval: {intervals.mean() * 1e6:.3f} μs")
    print(f"Std dev: {intervals.std() * 1e6:.3f} μs")

    # On PPS-synced system, you should see:
    # - Min: ~0.1 μs (clock resolution)
    # - Jitter: ~1-10 μs (scheduling)

test_timestamp_precision()
```

---

## Troubleshooting

### No GPS Device Found

**Symptoms:**
- `cgps` shows no data
- `/dev/ttyAMA0` doesn't exist

**Solutions:**

1. **Check UART is enabled:**
```bash
ls -l /dev/ttyAMA0
ls -l /dev/serial0

# Should show character device, not "No such file"
```

2. **Check boot config:**
```bash
grep uart /boot/firmware/config.txt

# Should show: enable_uart=1
```

3. **For USB GPS:**
```bash
ls /dev/ttyUSB* /dev/ttyACM*

# Use the device that appears
```

4. **Check dmesg for errors:**
```bash
sudo dmesg | grep tty
sudo dmesg | grep GPS
```

### gpsd Not Receiving Data

**Symptoms:**
- gpsd running but `cgps` shows no fix
- No satellite data

**Solutions:**

1. **Check GPS is actually connected:**
```bash
# Read raw data from GPS
cat /dev/ttyAMA0

# Should see NMEA sentences scrolling:
# $GPGGA,123456.00,3747.4900,N,12225.1640,W...
# (Ctrl+C to stop)
```

2. **Check gpsd is using correct device:**
```bash
ps aux | grep gpsd

# Should show: /usr/sbin/gpsd -n /dev/ttyAMA0
```

3. **Restart gpsd:**
```bash
sudo killall gpsd
sudo systemctl restart gpsd
sudo systemctl restart gpsd.socket
```

4. **Check permissions:**
```bash
# Add user to dialout group
sudo usermod -a -G dialout $USER

# Log out and back in for changes to take effect
```

### No GPS Fix (Stuck at "Searching")

**Symptoms:**
- gpsd running and receiving data
- Satellites visible but no fix
- Status shows "NO FIX"

**Solutions:**

1. **Ensure clear view of sky:**
   - GPS needs to see satellites
   - Won't work indoors (usually)
   - May work near window
   - Best outdoors with clear horizon

2. **Wait longer:**
   - First fix (cold start): 5-15 minutes
   - Subsequent fixes (warm start): 30-60 seconds
   - After power loss: may need full cold start

3. **Check antenna:**
   - Ensure antenna is connected
   - External antenna usually better than built-in
   - Antenna should face sky

4. **Check satellite data:**
```bash
gpsmon

# Look for satellites with signal strength (SNR)
# Need at least 4 satellites with SNR > 20 for fix
```

### PPS Device Doesn't Exist

**Symptoms:**
- `/dev/pps0` doesn't exist
- `ppstest` fails

**Solutions:**

```bash
# Enable PPS in boot config
sudo nano /boot/firmware/config.txt

# Add:
dtoverlay=pps-gpio,gpiopin=18

# Reboot
sudo reboot

# Verify
ls -l /dev/pps0
```

### Chrony Not Using PPS

**Symptoms:**
- PPS device exists but chrony doesn't show it
- Time accuracy is poor

**Solutions:**

```bash
# Check chrony config
sudo nano /etc/chrony/chrony.conf

# Should have:
refclock PPS /dev/pps0 refid PPS lock NMEA
refclock SHM 0 offset 0.0 delay 0.2 refid NMEA

# Restart
sudo systemctl restart chrony

# Verify
chronyc sources -v
# Should show PPS0 with * or # marker
```

### Clock Jumping Around

**Symptoms:**
- System time is unstable
- chrony shows large offsets

**Solutions:**

```bash
# Check for conflicts
systemctl status systemd-timesyncd
# Should be disabled if using chrony

sudo systemctl disable systemd-timesyncd
sudo systemctl stop systemd-timesyncd
```

### Poor GPS Accuracy

**Symptoms:**
- GPS fix acquired
- Position jumping around
- HDOP > 5

**Solutions:**

1. **Improve antenna placement:**
   - Higher is better (roof, pole)
   - Away from metal objects
   - Clear view of sky (360° if possible)

2. **Wait for better satellite geometry:**
   - HDOP < 2 is excellent
   - HDOP 2-5 is good
   - HDOP > 5 is poor

3. **Consider RTK GPS:**
   - For <1cm accuracy
   - Requires base station or NTRIP service
   - Much more expensive

---

## Best Practices

### Surveying Node Positions

For best trilateration accuracy, survey exact positions:

**Method 1: RTK GPS (best)**
- Use RTK GPS module
- Accuracy: <1cm
- Record position over 1 hour
- Average the readings

**Method 2: Standard GPS (good)**
- Let GPS run for 1+ hours
- Record all positions
- Average the readings
- Accuracy: ~2m

**Method 3: Mapping Software (acceptable)**
- Use Google Earth / Maps
- Drop pin at node location
- Read coordinates
- Accuracy: ~5m

**Method 4: Professional Survey (excellent)**
- Hire surveyor
- Get CORS/benchmark coordinates
- Accuracy: <1cm
- Expensive but best for permanent installations

### Deployment Checklist

- [ ] UART enabled in /boot/firmware/config.txt
- [ ] GPS device connected to correct pins
- [ ] gpsd installed and running
- [ ] Correct device configured in /etc/default/gpsd
- [ ] User in dialout group
- [ ] GPS has clear view of sky
- [ ] Waited sufficient time for fix (5-15 min cold start)
- [ ] Antenna connected (if external)
- [ ] PPS enabled if using precision timing
- [ ] Chrony configured and synced (if using PPS)
- [ ] Tested with `cgps -s` or `gpsmon`
- [ ] Tested with tools/gps_test.py

### General Tips

1. ✅ **Always test GPS before deployment**
   - Verify fix acquired
   - Check accuracy
   - Test in deployment location

2. ✅ **Use external antenna if possible**
   - Better satellite view
   - More reliable fix
   - Easier positioning

3. ✅ **Survey node positions for permanent installations**
   - More accurate than GPS alone
   - Can use static location provider
   - Update config with surveyed coordinates

4. ✅ **Monitor GPS health**
   - Check for fix loss
   - Track satellite count
   - Alert on poor HDOP

5. ✅ **Have fallback location**
   - Set static location in config
   - System continues working if GPS fails
   - Can use last known position

6. ✅ **Consider power consumption**
   - GPS draws 20-50mA
   - Can disable during low battery
   - Cache position if stationary

### Monitoring GPS Health

```python
stats = gps.get_stats()

# Check:
# - positions_read: should increase
# - no_fix_count: should be low
# - last_fix_time: should be recent
# - has_current_fix: should be True
```

### Via MQTT

GPS position updates published to event bus → MQTT:

```bash
mosquitto_sub -t "gunshot/+/status" -v

# Look for gps_position events
```

### Via Logging

```bash
# GPS events logged to system log
sudo journalctl -u gunshot-detector | grep GPS
```

---

## Performance Expectations

**Update Rate:**
- Typical: 1 Hz (1 update/second)
- High-end: 5-10 Hz

**Position Accuracy:**
- Standard GPS: 2-5m CEP
- DGPS: 1-2m CEP
- RTK: 1-2cm CEP

**Time Accuracy (with PPS):**
- PPS: <1 microsecond
- Without PPS: ~10-50ms (NTP)

**Time to First Fix:**
- Cold start: 26s (spec) to 15 minutes (reality)
- Warm start: <1 minute
- Hot start: <10 seconds

**Satellite Requirements:**
- Minimum: 4 satellites for 3D fix
- Good: 6-8 satellites
- Excellent: 10+ satellites

---

## Further Reading

- gpsd documentation: https://gpsd.gitlab.io/gpsd/
- NMEA sentences: https://www.gpsinformation.org/dale/nmea.htm
- U-blox documentation: https://www.u-blox.com/
- Chrony documentation: https://chrony.tuxfamily.org/
- RTK setup: Search for "raspberry pi rtk gps"
