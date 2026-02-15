# GPS/PPS Timing - Simplified Guide for Gunshot Detection

## TL;DR - What You Actually Need

If you already have GPS/PPS disciplining your Raspberry Pi's system clock (via chrony/ntpd), then:

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

---

## Understanding Your Setup

### What You Probably Have

**Hardware:**
- GPS module connected to Pi UART (usually `/dev/ttyAMA0` or `/dev/serial0`)
- PPS signal connected to GPIO (typically GPIO 18)

**Software Stack:**
```
GPS Module
    ├─ NMEA sentences ──→ gpsd ──→ gives lat/lon/alt
    └─ PPS pulses ──→ kernel ──→ chrony/ntpd ──→ disciplines system clock
```

**Result:**
- System clock is accurate to <1 microsecond
- ALL timestamps in your system automatically benefit
- No special code needed

### Verify Your Setup

```bash
# 1. Check GPS daemon
systemctl status gpsd
cgps -s  # Should show position and time

# 2. Check time daemon
systemctl status chrony  # or 'ntp'

# 3. Check PPS is working
chronyc sources -v
# Look for a line with "PPS" and very low offset (nanoseconds)

# 4. Verify PPS device
ls -l /dev/pps0
# Should exist if kernel PPS driver is loaded

# 5. See PPS pulses (optional)
sudo ppstest /dev/pps0
# Should show pulses every second
```

### Expected chronyc output

```
MS Name/IP address         Stratum Poll Reach LastRx Last sample
===============================================================================
#* PPS0                           0   4   377     6    +12ns[  +32ns] +/-   94ns
^- 192.168.1.1                    2   6   377    23  +1.2ms[+1.3ms] +/-   45ms
```

**What this means:**
- `#*` = PPS is the primary time source (excellent!)
- `+/-   94ns` = Clock accuracy is 94 nanoseconds (amazing!)
- Second line is network NTP (fallback if PPS fails)

---

## How to Use in Your Code

### Option 1: Use System Time Directly (Recommended)

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

**Pros:**
- Simple
- Already GPS-accurate
- No additional dependencies
- Works everywhere

**Cons:**
- None! This is the right approach.

### Option 2: Higher Precision with clock_gettime

```python
import time

# Use CLOCK_REALTIME for wall clock time
timestamp = time.clock_gettime(time.CLOCK_REALTIME)

# Or CLOCK_MONOTONIC for intervals (doesn't jump on clock adjustments)
start = time.clock_gettime(time.CLOCK_MONOTONIC)
# ... do work ...
end = time.clock_gettime(time.CLOCK_MONOTONIC)
elapsed = end - start
```

**When to use:**
- `CLOCK_REALTIME` - For absolute timestamps (detection events)
- `CLOCK_MONOTONIC` - For measuring intervals (buffer processing time)

### Option 3: Direct PPS Reading (Usually NOT Needed)

```python
import os
import struct
import time

def read_pps_event():
    """Read PPS event directly from kernel (advanced use only)."""
    # This is ONLY needed if you're writing your own time sync
    # or need to timestamp at the exact PPS edge

    with open('/dev/pps0', 'rb') as pps:
        # PPS_FETCH ioctl to get event
        import fcntl
        PPS_FETCH = 0xc0187001

        # This blocks until next PPS pulse
        buf = fcntl.ioctl(pps.fileno(), PPS_FETCH, b'\0' * 24)

        # Parse pps_info_t struct
        sec, nsec = struct.unpack('ll', buf[:16])
        return sec + nsec / 1e9
```

**When to use:**
- You're building a custom time server
- You need to measure exact PPS pulse arrival
- You're doing PPS performance analysis

**For gunshot detection: DON'T use this!**

---

## Timestamp Accuracy Analysis

### Your System Clock (with PPS)

If chrony shows `+/- 100ns` uncertainty:

**Sound travel distance for 100ns:**
```
Speed of sound: 343 m/s
Time: 100 nanoseconds = 0.0000001 seconds
Distance: 343 × 0.0000001 = 0.0000343 meters = 34.3 micrometers
```

That's **34 microns** - about the width of a human hair!

### Practical Uncertainty Sources (in order of impact)

1. **Audio buffer timing** (~1-10ms = 0.34-3.4 meters)
   - When exactly did sound hit microphone vs when buffer was read?
   - This is your dominant error source

2. **Network latency** (1-100ms = 0.34-34 meters)
   - MQTT message delivery time
   - Only matters if you timestamp AFTER network transmission

3. **Temperature/humidity** (~0.6% = 2 meters per 100m)
   - Speed of sound varies with conditions
   - 343 m/s at 20°C, 331 m/s at 0°C

4. **Microphone position error** (cm to meters)
   - GPS position accuracy: ~2-5 meters typical
   - Microphone offset from GPS antenna

5. **PPS timing** (<1 microsecond = 0.3mm)
   - This is negligible!

**Conclusion:** PPS gives you amazing time accuracy. Your limiting factors are elsewhere.

---

## Configuration for Your System

### Update timing.py to Use System Clock

```python
# src/core/timing.py

import time


class SystemClock:
    """
    Use system clock (already PPS-synchronized by chrony/ntpd).

    This is simpler and better than reading /dev/pps0 directly,
    because the kernel's time discipline algorithm is much more
    sophisticated than anything we'd write ourselves.
    """

    def __init__(self, event_bus=None):
        self.event_bus = event_bus

    def get_time(self) -> float:
        """Get current time (already GPS-synchronized)."""
        return time.time()

    def get_time_ns(self) -> int:
        """Get current time in nanoseconds."""
        return time.time_ns()

    def get_monotonic(self) -> float:
        """Get monotonic time (for intervals)."""
        return time.monotonic()

    def verify_sync(self) -> dict:
        """Verify system clock is synchronized."""
        try:
            # Check if chrony is running and synced
            import subprocess
            result = subprocess.run(
                ['chronyc', 'tracking'],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0:
                output = result.stdout

                # Parse output for sync status
                synced = 'Leap status     : Normal' in output

                # Extract system time offset
                for line in output.split('\n'):
                    if 'System time' in line:
                        # Format: "System time     : 0.000012345 seconds fast of NTP time"
                        parts = line.split(':')
                        if len(parts) > 1:
                            offset_str = parts[1].strip().split()[0]
                            offset = float(offset_str)

                            return {
                                'synced': synced,
                                'offset_seconds': offset,
                                'offset_ms': offset * 1000,
                                'source': 'chrony'
                            }

                return {'synced': synced, 'source': 'chrony'}

        except Exception as e:
            # Chrony not available, try ntpd
            try:
                result = subprocess.run(
                    ['ntpq', '-p'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )

                if result.returncode == 0:
                    # Look for * (primary source)
                    synced = '*' in result.stdout
                    return {'synced': synced, 'source': 'ntpd'}

            except Exception:
                pass

        # Can't verify sync status
        return {
            'synced': None,
            'error': 'Cannot verify time sync (chrony/ntpd not accessible)'
        }


class NTPClock:
    """
    Simple NTP client for systems without GPS/PPS.
    Uses network time instead of local GPS.
    Accuracy: ~10-50ms (much worse than PPS but better than nothing).
    """

    def __init__(self, ntp_server='pool.ntp.org', event_bus=None):
        import ntplib
        self.client = ntplib.NTPClient()
        self.ntp_server = ntp_server
        self.event_bus = event_bus
        self.offset = 0.0
        self.last_sync = 0.0

    def sync(self):
        """Sync with NTP server."""
        try:
            response = self.client.request(self.ntp_server, version=3, timeout=2)
            self.offset = response.offset
            self.last_sync = time.time()

            if self.event_bus:
                from core.event_bus import Event, EventType
                self.event_bus.publish(Event(
                    event_type=EventType.TIMING,
                    timestamp=self.get_time(),
                    source='NTPClock',
                    data={
                        'offset': self.offset,
                        'server': self.ntp_server,
                        'stratum': response.stratum
                    }
                ))

            return True
        except Exception as e:
            print(f"[NTPClock] Sync failed: {e}")
            return False

    def get_time(self) -> float:
        """Get NTP-corrected time."""
        return time.time() + self.offset
```

### Update Audio Nodes

```python
# src/audio/audio_nodes.py

class ALSASourceNode(AudioSourceNode):
    def __init__(self, ..., clock=None):
        super().__init__(...)
        self.clock = clock  # Optional: SystemClock or NTPClock

    def _audio_callback(self, in_data, frame_count, time_info, status):
        # Get timestamp
        if self.clock:
            timestamp = self.clock.get_time()
        else:
            # Just use system time directly
            timestamp = time.time()

        # Rest of callback...
```

### Update Config

```yaml
# config.yaml

timing:
  # Use system clock (PPS-disciplined)
  use_system_clock: true

  # Optional: Verify sync and alert if not synced
  verify_sync: true
  verify_interval: 60  # seconds

  # Fallback to NTP if PPS fails
  ntp_fallback:
    enabled: true
    server: "pool.ntp.org"
```

---

## Testing Your Timing

### 1. Verify PPS is Working

```bash
# Install tools
sudo apt install pps-tools chrony

# Check kernel PPS
sudo ppstest /dev/pps0
# Should show pulses every second with <1us jitter

# Check chrony sources
chronyc sources -v
# Should show PPS with very low offset
```

### 2. Measure Timestamp Precision

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

### 3. Compare Nodes

```python
# test_sync.py

import time
import socket

def compare_clocks(other_node_ip):
    """Compare clock with another node."""
    # Send timestamp
    local_time = time.time()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(str(local_time).encode(), (other_node_ip, 9999))

    # Get response
    sock.settimeout(1.0)
    data, addr = sock.recvfrom(1024)
    remote_time = float(data.decode())

    # Calculate offset
    offset = remote_time - local_time

    print(f"Clock offset from {other_node_ip}: {offset * 1e6:.1f} μs")

    # For PPS-synced nodes, should be <10 μs
```

---

## Common Issues

### PPS Device Doesn't Exist

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

Check chrony config:
```bash
sudo nano /etc/chrony/chrony.conf

# Should have:
refclock PPS /dev/pps0 refid PPS lock NMEA
refclock SHM 0 offset 0.0 delay 0.2 refid NMEA

# Restart
sudo systemctl restart chrony
```

### Clock Jumping Around

```bash
# Check for conflicts
systemctl status systemd-timesyncd
# Should be disabled if using chrony

sudo systemctl disable systemd-timesyncd
sudo systemctl stop systemd-timesyncd
```

---

## Recommendation for Your Project

**Simplified timing approach:**

1. ✅ Keep your existing GPS/PPS setup (chrony/ntpd)
2. ✅ Use `time.time()` directly in your code
3. ✅ Add optional sync verification in monitoring
4. ❌ Remove `/dev/pps0` reading code (unnecessary)
5. ✅ Add NTP fallback for nodes without GPS

**Benefits:**
- Simpler code
- Leverages existing time infrastructure
- Still GPS-accurate (<1μs)
- Automatic fallback if PPS fails
- Less to debug

The kernel time discipline algorithms (chrony/ntpd) are battle-tested and much better than anything we'd write ourselves!
