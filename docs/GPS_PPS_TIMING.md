# GPS PPS Timing

> **TL;DR:** When chrony is PPS-disciplined, `time.time()` is already GPS-accurate. The system clock drifts < 1µs from GPS. Python code just calls `time.time()` — no PPS library needed. The dominant positioning error is audio buffer timing (~1–10ms), not clock sync.

---

## How It Works

### The Simple Version

GPS modules output a **PPS (Pulse Per Second)** signal — a hardware pulse exactly on the UTC second, accurate to < 1µs. This pulse connects to a GPIO pin (default: GPIO 18 / Pin 12).

Linux's chrony daemon uses this pulse to discipline the system clock. Once synchronized:

```
time.time()  →  GPS-accurate timestamp  →  < 1µs error
```

**You don't need to read `/dev/pps0` in application code.** The kernel and chrony handle it. The audio callback in `ALSASourceNode._audio_callback` captures `time.time()` immediately on buffer arrival — that's all the timing logic needed.

### The Accuracy Chain

```
GPS Satellite  →  GPS Module  →  PPS pulse (GPIO 18)
                                       │
                                 Kernel PPS driver
                                       │
                              chrony (NTP daemon)
                                       │
                              System clock (CLOCK_REALTIME)
                                       │
                              Python: time.time()
                                       │
                              AudioBuffer.timestamp
```

### Error Budget

| Source | Error | Impact on Position |
|--------|-------|--------------------|
| PPS clock sync | < 1µs | 0.0003m |
| NTP (no PPS) | 10–100ms | 3.4–34m |
| Audio buffer timing | 1–10ms (dominant) | 0.34–3.4m |
| Speed of sound (temperature) | 1°C error = 0.6m/s | ~1.7m/km |
| GPS position error | ±2–5m typical | Direct position offset |
| Multipath reflections | Variable | Use earliest arrival |

**With GPS PPS:** 10–50m practical accuracy at typical gunshot ranges.
**Without PPS (NTP only):** 50–500m positioning error.

---

## Hardware Setup

### Wiring

```
GPS Module         Raspberry Pi
VCC (3.3V)   →    Pin 1  (3.3V)
GND          →    Pin 6  (GND)
TX           →    Pin 10 (GPIO 15, RXD)
RX           →    Pin 8  (GPIO 14, TXD)
PPS          →    Pin 12 (GPIO 18)     ← critical for timing
```

Recommended module: **U-blox NEO-M8N** (~$15): 2.5m CEP, 1–10 Hz, UART + PPS output.

### Enable PPS in Firmware

Add to `/boot/firmware/config.txt`:

```
enable_uart=1
dtoverlay=disable-bt          # frees UART from Bluetooth (Pi 3/4)
dtoverlay=pps-gpio,gpiopin=18 # enable PPS on GPIO 18
```

Reboot after editing.

---

## Software Setup

### 1. Install chrony and PPS tools

```bash
sudo apt install chrony pps-tools

# Disable systemd-timesyncd — it conflicts with chrony
sudo systemctl disable systemd-timesyncd
sudo systemctl stop systemd-timesyncd
```

### 2. Configure gpsd

```bash
# /etc/default/gpsd
START_DAEMON="true"
USBAUTO="true"
DEVICES="/dev/ttyAMA0 /dev/pps0"  # include PPS device
GPSD_OPTIONS="-n -G"
```

```bash
sudo systemctl enable gpsd
sudo systemctl start gpsd
```

### 3. Configure chrony for PPS

Add to `/etc/chrony/chrony.conf`:

```
refclock SHM 0 offset 0.0 delay 0.2 refid NMEA
refclock PPS /dev/pps0 refid PPS lock NMEA
```

The `lock NMEA` clause tells chrony to only trust PPS when it agrees with NMEA GPS time — prevents false lock on the wrong second.

```bash
sudo systemctl restart chrony
```

---

## Verification

### Check PPS signal is arriving

```bash
sudo ppstest /dev/pps0
# Expected output: source 0 - assert 1234567890.000000001, sequence: 42
```

If this hangs, the GPIO wiring or dtoverlay is wrong.

### Check chrony sync status

```bash
chronyc sources -v
```

Look for the PPS line marked with `*` (selected source) and offset in nanoseconds:

```
MS Name/IP address         Stratum Poll Reach LastRx Last sample
===============================================================================
#* PPS                           0   4   377     6  -23ns[  -15ns] +/-   51ns
^? NMEA                          0   4   377     7  +120ms[+120ms] +/-  200ms
```

The `#` prefix means it's a reference clock (local hardware). `*` means currently selected. The offset `-23ns` means the system clock is 23 nanoseconds ahead of GPS — excellent.

### Check chrony tracking

```bash
chronyc tracking
```

Key fields:

```
Reference ID    : 50505300 (PPS)
Stratum         : 1
System time     : 0.000000021 seconds fast of NTP time    ← ~21ns
RMS offset      : 0.000000023 seconds
Frequency       : 1.234 ppm fast
```

`Stratum: 1` with `PPS` as reference ID = GPS PPS disciplined. System time offset < 100ns is excellent.

### Confirm from Python

Once chrony is PPS-locked, no Python code is needed — `time.time()` is already GPS-accurate:

```python
import time
import subprocess

def verify_pps_sync() -> bool:
    """Check if system clock is GPS/PPS disciplined."""
    result = subprocess.run(["chronyc", "tracking"], capture_output=True, text=True)
    return "PPS" in result.stdout and "Stratum         : 1" in result.stdout

if verify_pps_sync():
    print("System clock is GPS-disciplined. time.time() is GPS-accurate.")
```

---

## NTP Fallback (Nodes Without GPS)

For nodes without a GPS module, time.time() accuracy depends on NTP:

| NTP Source | Typical Accuracy |
|-----------|-----------------|
| Local PPS-disciplined server on same LAN | < 1ms |
| public NTP pool (pool.ntp.org) | 5–50ms |
| No NTP | Drifts 1–100ms/minute |

**Fleet recommendation:** Run one GPS+PPS node as an NTP server. Configure all other nodes to use it:

```bash
# /etc/chrony/chrony.conf on non-GPS nodes
server 192.168.1.100 iburst prefer    # your GPS node IP
```

This gives non-GPS nodes ~0.1–1ms accuracy — much better than the public NTP pool, and good enough for sub-10m trilateration.

---

## Configuration

The `timing:` section in `config.example.yaml` is reserved for a future `NTPClock` / `SystemClock` module (see [STATUS.md](STATUS.md) — Timing/Synchronization is 0% implemented). Currently the system relies entirely on the OS clock being pre-synchronized by chrony/gpsd.

Planned config:

```yaml
timing:
  use_system_clock: true      # rely on OS clock (chrony-disciplined)
  verify_sync: true           # check chronyc tracking on startup
  verify_interval: 60         # re-verify every 60s
  ntp_fallback:
    enabled: true
    server: "192.168.1.100"   # local GPS-disciplined NTP server
```

---

## Common Issues

### PPS not detected (`/dev/pps0` missing)

```bash
ls /dev/pps*          # should show /dev/pps0
dmesg | grep pps      # look for: pps_core: LinuxPPS API registered
```

If missing: check `dtoverlay=pps-gpio,gpiopin=18` is in `/boot/firmware/config.txt` and the Pi was rebooted.

### chrony not using PPS (`*` missing from PPS line)

The `lock NMEA` clause requires NMEA to be stable first. Check gpsd is running and has a fix:

```bash
systemctl status gpsd
cgps -s              # terminal GPS monitor; wait for fix
```

### systemd-timesyncd conflicts with chrony

```bash
sudo systemctl disable systemd-timesyncd
sudo systemctl stop systemd-timesyncd
systemctl status chronyd   # should be active (running)
```

### Bluetooth conflicting with UART (Pi 3/4)

Add to `/boot/firmware/config.txt`:

```
dtoverlay=disable-bt
```

Then: `sudo systemctl disable hciuart`

### GPS has fix but poor timing (offset > 1ms)

The PPS pulse may be connected but the `lock NMEA` reference is missing. Verify:

```bash
cat /etc/chrony/chrony.conf | grep -E "SHM|PPS"
```

Both the `SHM 0` (NMEA) and `PPS /dev/pps0 lock NMEA` lines must be present.

---

## What GDS Currently Implements

| Feature | Status |
|---------|--------|
| Audio timestamps via `time.time()` | ✅ Implemented — `ALSASourceNode._audio_callback` |
| GPS position via gpsd | ✅ Implemented — `src/sensors/gps.py` |
| PPS clock discipline | ✅ Via OS/chrony — no Python code needed |
| Startup PPS verification | ❌ Not implemented — `verify_sync()` planned |
| NTPClock offset monitoring | ❌ Not implemented — planned in Phase 4 |
| Runtime clock health events | ❌ Not implemented |

See [STATUS.md](STATUS.md) → Phase 4 for timing implementation roadmap.
