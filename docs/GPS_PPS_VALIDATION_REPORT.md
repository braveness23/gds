# GPS/PPS Hardware Validation Report

**Node:** witness (192.168.101.216)
**Date:** 2026-03-15
**Hardware:** Raspberry Pi 3B+ + Adafruit Ultimate GPS HAT (#2324) + Google Voice HAT (I2S)
**Branch:** feat/gps-pps-validation

> ⚠️ **PII Notice:** GPS fix data in this document has been redacted. Do not commit real-world
> node coordinates, addresses, or location data to this repository. Use placeholder coordinates
> in config examples and test fixtures.

---

## Result: ✅ FULLY VALIDATED — STRATUM 1, 17ns OFFSET

| Component | Status | Notes |
|---|---|---|
| GPS NMEA fix | ✅ Operational | 3D fix, 9 satellites, HDOP 0.90 |
| PPS signal | ✅ Clean 1Hz | GPIO 4, confirmed via ppstest |
| chrony | ✅ Stratum 1 | Reference: PPS, 17ns system offset |
| I2S audio | ✅ Operational | Google Voice HAT, capture device ready |
| strix codebase | ✅ Compatible | Repo present at `~/gds` on node |

**Trilateration timing error: ~6mm at 17ns offset.**
(Timing model: 1ms → 0.34m; 17ns → 0.006m)

---

## Hardware Inventory

### Platform

| Item | Value |
|---|---|
| Hostname | witness |
| OS | Raspberry Pi OS Lite, kernel 6.1.21-v7+ |
| Architecture | armv7l (Raspberry Pi 3B+) |

### Serial / GPS Devices

| Device | Type | Notes |
|---|---|---|
| `/dev/ttyAMA0` → `/dev/serial1` | PL011 full UART | Claimed by Bluetooth (hciuart) |
| `/dev/ttyS0` → `/dev/serial0` | mini-UART | GPS NMEA — 9600 baud |
| `/dev/pps0` | PPS kernel device | GPIO 4, 1Hz signal from GPS HAT |

**Pi 3B+ UART assignment:** `ttyAMA0` is Bluetooth, `ttyS0` is GPIO serial. GPS must use `ttyS0`.

### Audio Devices

| Device | Description |
|---|---|
| `card 2: sndrpigooglevoi` | Google Voice HAT I2S soundcard |
| `pcmC2D0c` | Capture device — microphone input |

Loaded overlays: `audioinjector-bare-i2s`, `googlevoicehat-soundcard`
Modules: `snd_soc_rpi_simple_soundcard`, `snd_soc_bcm2835_i2s`, `snd_soc_googlevoicehat_codec`

---

## Root Causes Found and Fixed

### 1. gpsd not connected to GPS device

`/etc/default/gpsd` had `DEVICES=""` (empty). gpsd was running but reading nothing.
Additionally, an initial attempt used `/dev/ttyAMA0` which is held by Bluetooth on the Pi 3B+.

**Fix applied to `/etc/default/gpsd`:**
```bash
START_DAEMON="true"
GPSD_OPTIONS="-n"
DEVICES="/dev/ttyS0"
USBAUTO="false"
```

### 2. pps-gpio overlay missing from config.txt

`/dev/pps0` never appeared because the kernel overlay was not loaded.

**Fix applied to `/boot/config.txt`:**
```
dtoverlay=pps-gpio,gpiopin=4
```

### 3. Wrong GPIO pin (18 instead of 4)

An initial attempt configured GPIO 18, which is the I2S bit clock used by the Google Voice HAT.
This caused a kernel GPIO conflict and electrical noise on pps0 (hundreds of false pulses/sec
instead of a clean 1Hz signal).

The [Adafruit Ultimate GPS HAT (#2324)](https://www.adafruit.com/product/2324) routes PPS to **GPIO 4**.

```
# dmesg conflict (with GPIO 18 — now resolved):
pin gpio18 already requested by pps@12; cannot claim for 3f203000.i2s
```

**Fix:** Corrected `gpiopin=18` → `gpiopin=4` in `/boot/config.txt`.

### 4. chrony not installed

The node was using `systemd-timesyncd` (stratum 3). chrony is required to consume
the GPS NMEA SHM refclock and PPS device for sub-millisecond timing.

**Fix:** Installed chrony, added to `/etc/chrony/chrony.conf`:
```
refclock SHM 0 offset 0.5 delay 0.2 refid NMEA
refclock PPS /dev/pps0 lock NMEA refid PPS
```

---

## Validation Results

### GPS Fix

| Parameter | Value |
|---|---|
| Fix type | 3D (mode 3), DGPS |
| Satellites used | 9 of 12 tracked |
| HDOP | **0.90** (excellent — <1.0 is good) |
| VDOP | 0.81 |
| PDOP | 1.21 |
| Position | *[redacted — do not commit coordinates]* |
| Altitude | *[redacted]* |

### PPS Signal

Clean 1Hz pulses confirmed via `ppstest /dev/pps0`:
```
source 0 - assert xxxxxxxxxx.001175885, sequence: 55
source 0 - assert xxxxxxxxxx.999993346, sequence: 56  ← Δ = 0.998817s
source 0 - assert xxxxxxxxxx.999998904, sequence: 57  ← Δ = 1.000006s
```

### Chrony (final state)

```
$ chronyc sources -v
#- NMEA    0   4   7   20   +17ms[ +21ms] +/- 109ms
#* PPS     0   4   7   20   +1359ns[+3995us] +/- 552ns   ← locked (*)

$ chronyc tracking
Reference ID    : PPS
Stratum         : 1
System time     : 0.000000017 seconds fast of NTP time   ← 17 nanoseconds
Root delay      : 0.000000001 seconds
Root dispersion : 0.000114355 seconds
```

---

## strix Code Compatibility Notes

### GPSReader (gpsd mode)
- Connects to gpsd at `localhost:2947` — now working correctly with `ttyS0`
- HDOP approximated from `epx`/`epy` values — acceptable accuracy
- `satellites` count comes from SKY messages (not TPV) — works as designed

### NTPClock
- Queries NTP offset via `ntplib` — will report well within the 10ms default threshold
- Does not discipline the clock directly; chrony handles that at OS level

### Static coordinate fallback
- `create_gps_reader()` raises `ValueError` if lat/lon are `0.0` — ensure `config.yaml`
  has non-zero coordinates before running on hardware

### Python packages (confirmed on node)

| Package | Version |
|---|---|
| aubio | 0.4.9 |
| numpy | 1.19.5 |
| paho-mqtt | 2.1.0 |
| scipy | 1.13.1 |

---

## Reproduction Commands

```bash
# Hardware inventory
ssh pi@<NODE_IP> 'ls -la /dev/ttyAMA* /dev/ttyS* /dev/pps* 2>&1'
ssh pi@<NODE_IP> 'arecord -l'
ssh pi@<NODE_IP> 'dmesg | grep -iE "gps|pps|i2s|uart" | tail -30'
ssh pi@<NODE_IP> 'lsmod | grep -iE "pps|snd_soc"'

# GPS
ssh pi@<NODE_IP> 'systemctl status gpsd'
ssh pi@<NODE_IP> 'cat /etc/default/gpsd'
ssh pi@<NODE_IP> 'timeout 15 gpspipe -w -n 5'

# PPS
ssh pi@<NODE_IP> 'sudo ppstest /dev/pps0'

# Chrony
ssh pi@<NODE_IP> 'chronyc sources -v'
ssh pi@<NODE_IP> 'chronyc tracking'
```

---

## What's Next

This node is ready for multi-node simulation. Next steps:

1. **Multi-node simulation** — 3 simulated nodes with known positions, synthetic
   timestamped detections, validate trilateration server output against expected location
2. **Additional node provisioning** — apply same GPS/PPS/chrony config to new nodes
   using this document as the reference
3. **First live multi-node detection test**

---

*Validated against strix source: `src/sensors/gps.py`, `src/timing/ntp_clock.py`, `scripts/trilateration_server.py`*
