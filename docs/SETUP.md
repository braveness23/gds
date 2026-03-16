# Setup Guide

> **TL;DR:** Choose your path: Raspberry Pi with full GPS hardware, any Linux machine, or simulation-only (no hardware at all). All three paths end with `pytest tests/ -q` passing.

---

## Path 1: Raspberry Pi (full hardware)

For production trilateration accuracy: Pi 3B+ or later, GPS module with PPS output, I2S or USB microphone.

### Validated hardware

- **Board:** Raspberry Pi 3B+, 4B, or 5
- **GPS:** Adafruit Ultimate GPS HAT #2324 (validated — 17ns offset achieved)
- **Audio:** Any USB audio interface, or I2S microphone (INMP441, ICS43434)
- **Environmental:** BME280 (recommended) or DHT22

### 1. Flash Raspberry Pi OS

Use Raspberry Pi Imager (64-bit Raspberry Pi OS Lite). In advanced options:
- Enable SSH
- Set hostname: `strix-001`
- Set username and password

### 2. System packages

```bash
sudo apt-get update && sudo apt-get install -y \
    python3-dev python3-pip python3-venv build-essential \
    portaudio19-dev libportaudio2 libasound2-dev libsndfile1-dev \
    aubio-tools libaubio-dev \
    gpsd gpsd-clients python3-gps \
    libgpiod2 \
    chrony pps-tools \
    git
```

### 3. Configure UART and PPS

Edit `/boot/firmware/config.txt` (Pi 4/5) or `/boot/config.txt` (Pi 3):

```ini
enable_uart=1
dtoverlay=disable-bt          # frees UART from Bluetooth on Pi 3/4
dtoverlay=pps-gpio,gpiopin=18 # PPS signal on GPIO 18
```

Reboot after editing.

### 4. Configure gpsd

```bash
# /etc/default/gpsd
START_DAEMON="true"
USBAUTO="true"
DEVICES="/dev/ttyAMA0"      # UART GPS; use /dev/ttyUSB0 for USB GPS
GPSD_OPTIONS="-n -G"
```

```bash
sudo systemctl enable gpsd && sudo systemctl start gpsd
```

Verify:
```bash
cgps -s          # wait for GPS fix (up to 15 min cold start, needs sky view)
```

### 5. Configure chrony for PPS timing

```bash
sudo systemctl disable systemd-timesyncd
sudo systemctl stop systemd-timesyncd
```

Add to `/etc/chrony/chrony.conf`:
```
refclock PPS /dev/pps0 refid PPS lock NMEA
refclock SHM 0 offset 0.0 delay 0.2 refid NMEA
```

```bash
sudo systemctl restart chrony
chronyc sources -v    # PPS0 should show * as primary source
```

With PPS enabled, clock offset is typically < 1μs. See [GPS_PPS_TIMING.md](GPS_PPS_TIMING.md) for accuracy analysis and troubleshooting.

### 6. Install strix

```bash
git clone https://github.com/braveness23/gds.git
cd gds
python3 scripts/setup_dev.py
```

### 7. Configure and run

```bash
cp examples/config.example.yaml config.yaml
# Edit: set node_id (unique!), MQTT broker, GPS settings
python main.py --config config.yaml
```

### Verification

```bash
python3 -m pytest tests/ -q
cgps -s                          # GPS fix and timing
python tools/gps_test.py --check # strix GPS validation
chronyc sources -v               # confirm PPS is primary source
```

**GPS wiring (UART):**
```
GPS Module    Raspberry Pi
VCC (3.3V) →  Pin 1 (3.3V)
GND        →  Pin 6 (GND)
TX         →  Pin 10 (GPIO 15, RXD)
RX         →  Pin 8  (GPIO 14, TXD)
PPS        →  Pin 12 (GPIO 18)
```

---

## Path 2: Generic Linux (USB audio + GPS)

Any Linux machine with a USB audio interface and USB/serial GPS. Best for development and small deployments where millisecond-level timing is acceptable.

### System packages (Debian/Ubuntu)

```bash
sudo apt-get update && sudo apt-get install -y \
    python3-dev python3-pip python3-venv build-essential \
    portaudio19-dev libportaudio2 libasound2-dev libsndfile1-dev \
    aubio-tools libaubio-dev \
    gpsd gpsd-clients python3-gps \
    git
```

### GPS setup

For USB GPS (e.g. u-blox USB dongle), gpsd usually auto-detects:

```bash
sudo apt install gpsd gpsd-clients
sudo gpsd /dev/ttyUSB0 -n -G    # or let systemd manage it
cgps -s                          # verify fix
```

**Without PPS:** Use NTP-only mode. `NTPClock` monitors offset and fires TIMING events if drift exceeds 10ms. Trilateration accuracy degrades to ~3–30m depending on NTP quality (vs < 1m with GPS PPS).

To run without PPS:
```bash
python main.py --config config.yaml    # GPS still provides position; timing via NTP
```

### Install strix

```bash
git clone https://github.com/braveness23/gds.git
cd gds
python3 scripts/setup_dev.py
```

### Find your audio device

```bash
arecord -l     # list ALSA capture devices
```

Set `audio.device` in `config.yaml` to match (e.g. `hw:1,0`).

### Verification

```bash
python3 -m pytest tests/ -q
python tools/gps_test.py --check
```

---

## Path 3: Simulation / Development (no hardware)

No GPS or microphone needed. Best for first-time contributors, algorithm development, and CI.

### Requirements

- Python 3.7+
- Any OS (Linux, macOS, Windows)

### Install

```bash
git clone https://github.com/braveness23/gds.git
cd gds
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .[dev]
pre-commit install
```

### Run the simulation

```bash
python tools/run_simulation.py
```

See [QUICKSTART.md](QUICKSTART.md) for simulation details and available scenarios.

### Run tests

```bash
pytest tests/ -q
```

All tests should pass. The simulation framework (`tests/simulation/`) and integration tests run entirely in-process — no broker, GPS, or audio needed.

---

## Fleet deployment

See the existing deployment section in the fleet notes below. Each node needs:
- A unique `node_id` in `config.yaml`
- The shared MQTT broker address
- GPS configured (or static coordinates as fallback)

### MQTT broker (central server)

```bash
sudo apt install mosquitto mosquitto-clients

# /etc/mosquitto/mosquitto.conf
listener 1883
allow_anonymous true    # use auth in production

sudo systemctl enable --now mosquitto
```

### Run as systemd service (each node)

```bash
sudo cp systemd/gunshot-detector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gunshot-detector
sudo journalctl -u gunshot-detector -f
```

### Verify fleet

```bash
mosquitto_sub -h <broker> -t 'gunshot/detections' -v
mosquitto_sub -h <broker> -t 'gunshot/+/health' -v
```

### Security hardening checklist

- [ ] MQTT authentication (username/password minimum)
- [ ] TLS enabled (port 8883)
- [ ] Unique credentials per node
- [ ] Firewall: allow SSH (22) and MQTT TLS (8883) only
- [ ] VPN for inter-site communication
