# Setup Guide

> **TL;DR:** Install system packages → run `python scripts/setup_dev.py` → configure `config.yaml` → run `python main.py`. For fleet deployment, repeat per node with unique `node_id` and a shared MQTT broker.

---

## System Dependencies

### Raspberry Pi / Debian / Ubuntu

```bash
sudo apt-get update && sudo apt-get install -y \
    python3-dev python3-pip python3-venv build-essential \
    portaudio19-dev libportaudio2 libasound2-dev libsndfile1-dev \
    aubio-tools libaubio-dev \
    gpsd gpsd-clients python3-gps \
    libgpiod2 \
    git
```

### macOS

```bash
brew install portaudio aubio libsndfile
```

GPS and GPIO sensors are not supported on macOS (Raspberry Pi only).

### Windows

- **PyAudio:** `pip install pyaudio` (pre-compiled wheels available for recent Python versions)
- **Aubio:** Limited Windows support; use conda (`conda install -c conda-forge aubio`) or file-based detection mode
- Hardware sensors (GPS, BME280, DHT22) don't work on Windows; use mock implementations for development

**Validation:**
```bash
python scripts/check_dependencies.py
```

---

## GPS Setup (Raspberry Pi)

### Hardware

**Recommended modules:**
- U-blox NEO-M8N — $10–20, 2.5m CEP, 1–10 Hz, UART + PPS
- U-blox ZED-F9P — $200+, < 1cm with RTK, dual-band

**Wiring (UART):**
```
GPS Module          Raspberry Pi
VCC (3.3V)    →     Pin 1 (3.3V)
GND           →     Pin 6 (GND)
TX            →     Pin 10 (GPIO 15, RXD)
RX            →     Pin 8 (GPIO 14, TXD)
PPS           →     Pin 12 (GPIO 18)  [for microsecond timing]
```

### Software Setup

**1. Enable UART:**
```bash
# /boot/firmware/config.txt
enable_uart=1
dtoverlay=disable-bt       # optional, frees UART from Bluetooth on Pi 3/4
dtoverlay=pps-gpio,gpiopin=18  # if using PPS
```
Reboot after editing.

**2. Configure gpsd:**
```bash
# /etc/default/gpsd
START_DAEMON="true"
USBAUTO="true"
DEVICES="/dev/ttyAMA0"    # or /dev/ttyUSB0 for USB GPS
GPSD_OPTIONS="-n -G"
```

```bash
sudo systemctl enable gpsd
sudo systemctl start gpsd
```

**3. Configure chrony for PPS timing (optional but recommended):**
```bash
sudo apt install chrony pps-tools
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
chronyc sources -v    # verify PPS0 shows * (primary source)
```

With PPS, clock accuracy is < 1μs. The dominant positioning error is audio buffer timing (~1–10ms = 0.34–3.4m).

See [GPS_PPS_TIMING.md](GPS_PPS_TIMING.md) for deeper coverage: accuracy analysis, verification commands, NTP fallback for non-GPS nodes, and common issues.

### Testing GPS

```bash
cgps -s                           # terminal GPS monitor
python tools/gps_test.py --check  # project test tool
python tools/gps_test.py --monitor 30
```

**Deployment checklist:**
- [ ] UART enabled in `/boot/firmware/config.txt`
- [ ] GPS device connected and wired correctly
- [ ] gpsd installed and running (`systemctl status gpsd`)
- [ ] Device configured in `/etc/default/gpsd`
- [ ] User in `dialout` group (`sudo usermod -a -G dialout $USER`)
- [ ] GPS has clear view of sky (5–15 min cold start for first fix)
- [ ] PPS enabled and chrony synced (if using precision timing)
- [ ] Tested with `cgps -s`

### Surveying Node Positions

For best trilateration accuracy, survey exact node positions:

| Method | Accuracy | Effort |
|--------|----------|--------|
| RTK GPS | < 1cm | Moderate |
| Standard GPS (average over 1hr) | ~2m | Low |
| Google Earth pin drop | ~5m | Very low |
| Professional survey | < 1cm | High / expensive |

### Configuration

```yaml
sensors:
  gps:
    enabled: true
    host: "localhost"
    port: 2947
    update_interval: 1.0

location:
  latitude: 37.7749     # fallback if GPS unavailable
  longitude: -122.4194
  altitude: 10.0
```

---

## Environmental Sensors (Raspberry Pi)

Environmental sensors provide temperature-compensated speed of sound for trilateration accuracy.

### Sensor Options

| Sensor | Interface | Temp Accuracy | Humidity | Pressure | Cost |
|--------|-----------|--------------|----------|----------|------|
| **BME280** (recommended) | I2C | ±1°C | ±3% | ✅ | $10–20 |
| DHT22 | GPIO | ±0.5°C | ±2–5% | ❌ | $2–5 |
| DHT11 | GPIO | ±2°C | ±5% | ❌ | $1–2 |

### BME280 Wiring (I2C)

```
BME280        Raspberry Pi
VCC     →     Pin 1 (3.3V)
GND     →     Pin 6 (GND)
SCL     →     Pin 5 (GPIO 3)
SDA     →     Pin 3 (GPIO 2)
```

I2C address: 0x76 (default) or 0x77.

**Enable I2C:**
```bash
sudo raspi-config
# Interface Options → I2C → Enable

# Verify
i2cdetect -y 1    # should show 76 at address 0x76
```

**Install libraries:**
```bash
pip install adafruit-circuitpython-bme280 adafruit-blinka
```

### DHT22 Wiring (GPIO)

```
DHT22         Raspberry Pi
VCC     →     Pin 1 (3.3V)
GND     →     Pin 6 (GND)
DATA    →     Pin 7 (GPIO 4)  + 4.7kΩ pull-up to VCC
```

**Install libraries:**
```bash
pip install adafruit-circuitpython-dht
sudo apt-get install libgpiod2
```

DHT sensors have 10–20% checksum error rate — this is normal; the driver handles it.

### Testing Sensors

```bash
python tools/env_test.py                    # auto-detect
python tools/env_test.py --test-bme280 --duration 30
python tools/env_test.py --test-dht22 --gpio 4
```

### Configuration

```yaml
sensors:
  environmental:
    type: "bme280"       # "bme280", "dht22", "dht11", "none"
    i2c_address: "0x76"  # BME280 only
    gpio_pin: 4          # DHT only
    update_interval: 5.0
```

### Placement Tips

- Mount sensor **away from the Pi** (10+ cm) to avoid self-heating errors
- Shade from direct sunlight
- Use a ventilated enclosure

---

## Fleet Deployment

### 1. Prepare SD Cards

Flash Raspberry Pi OS (64-bit) to each SD card using Raspberry Pi Imager:
- Enable SSH in advanced options
- Set hostnames: `gunshot-001`, `gunshot-002`, etc.
- Use the same username/password across all nodes

### 2. Initial Node Configuration

```bash
sudo apt update && sudo apt upgrade -y
sudo raspi-config    # Set timezone, enable I2C, serial port
sudo reboot
```

### 3. Deploy Code

From your development machine:
```bash
NODES=("pi@192.168.1.101" "pi@192.168.1.102" "pi@192.168.1.103")

for node in "${NODES[@]}"; do
  echo "Deploying to $node..."
  make deploy PI_HOST=$node
done
```

Or manually on each Pi:
```bash
git clone https://github.com/braveness23/gds.git
cd gds
python scripts/setup_dev.py
```

### 4. Configure Each Node

```yaml
# config.yaml — must be unique per node
system:
  node_id: "gunshot-001"      # UNIQUE per node

output:
  mqtt:
    broker: "192.168.1.100"   # shared MQTT broker IP
    port: 1883

location:
  latitude: 37.7749           # set if no GPS
  longitude: -122.4194
```

### 5. Set Up MQTT Broker (Central Server)

```bash
sudo apt install mosquitto mosquitto-clients

# /etc/mosquitto/mosquitto.conf
listener 1883
allow_anonymous true

# Or with authentication:
# password_file /etc/mosquitto/passwd
sudo mosquitto_passwd -c /etc/mosquitto/passwd admin
sudo systemctl restart mosquitto
```

### 6. Start Services

```bash
# On each Pi
sudo cp systemd/gunshot-detector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable gunshot-detector
sudo systemctl start gunshot-detector

# Verify
sudo systemctl status gunshot-detector
sudo journalctl -u gunshot-detector -f
```

### 7. Verify Fleet Operation

```bash
# From any machine with broker access
mosquitto_sub -h <broker> -t 'gunshot/detections' -v
mosquitto_sub -h <broker> -t 'gunshot/+/health' -v
mosquitto_sub -h <broker> -t 'gunshot/gunshot-001/#' -v
```

### Network Options

| Option | Power Source | Reliability | Use Case |
|--------|-------------|-------------|----------|
| WiFi | PoE or battery | Good | Most deployments |
| Ethernet + PoE HAT | PoE switch | Best | Permanent installations |
| Meshtastic LoRa | Battery | Long range, low bandwidth | Off-grid / rural |

### Maintenance

**Update all nodes:**
```bash
for node in "${NODES[@]}"; do
  ssh $node "cd ~/gds && git pull && sudo systemctl restart gunshot-detector"
done
```

**Check node health:**
```bash
for node in "${NODES[@]}"; do
  echo "=== $node ===" && ssh $node "sudo systemctl status gunshot-detector"
done
```

**Security hardening checklist:**
- [ ] Enable MQTT authentication (username/password minimum)
- [ ] Enable TLS for MQTT (port 8883)
- [ ] Unique credentials per node
- [ ] Firewall: `sudo ufw allow 22/tcp && sudo ufw allow 8883/tcp && sudo ufw enable`
- [ ] Use VPN for inter-site communication
