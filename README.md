# Gunshot Detection System

[![CI](https://github.com/braveness23/gds/actions/workflows/ci.yml/badge.svg)](https://github.com/braveness23/gds/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.7%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

A distributed acoustic gunshot detection and trilateration system for Raspberry Pi fleets with GPS/PPS timing.

## What It Does

- Listens for acoustic gunshot events via a microphone
- Timestamps detections with GPS-synchronized clocks (microsecond precision via PPS)
- Publishes events to an MQTT broker
- A central trilateration server calculates gunshot position from time-of-arrival differences across multiple nodes

**Current status: ~75–80% complete.** Core detection, MQTT publishing, GPS integration, environmental sensors, system monitoring, and remote configuration all work. Comprehensive test suite (77% coverage). See [docs/STATUS.md](docs/STATUS.md).

## Hardware Requirements

**Minimum:**

- Raspberry Pi 3B+ or later
- I2S MEMS microphone or USB audio interface
- MicroSD card (16GB+)

**Recommended:**

- Raspberry Pi 4 or 5
- GPS module with PPS output (U-blox NEO-M8N)
- BME280 temperature/humidity sensor (improves trilateration accuracy)

## Quick Start

### 1. System Dependencies

```bash
sudo apt-get update && sudo apt-get install -y \
    python3-dev python3-pip python3-venv build-essential \
    portaudio19-dev libportaudio2 libasound2-dev libsndfile1-dev \
    aubio-tools libaubio-dev \
    gpsd gpsd-clients python3-gps git
```

### 2. Python Environment

```bash
git clone https://github.com/braveness23/gds.git
cd gds
python scripts/setup_dev.py    # creates .venv, installs deps, sets up pre-commit
```

Or manually:

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .[dev]
pre-commit install
```

### 3. Configure

```bash
cp examples/config.example.yaml config.yaml
```

Edit `config.yaml` with your settings:

```yaml
system:
  node_id: "pi_gunshot_001"    # unique per node

audio:
  source_type: "alsa"
  device: "hw:0,0"             # find with: arecord -l

output:
  mqtt:
    enabled: true
    broker: "192.168.1.100"    # your MQTT broker IP
    topic: "gunshot/detections"
```

### 4. Run

```bash
python main.py --config config.yaml

# Test with audio file (no microphone needed):
python main.py --config config.yaml --test examples/test_audio.wav

# Without MQTT:
python main.py --config config.yaml --no-mqtt
```

### 5. Run as Service

```bash
sudo cp systemd/gunshot-detector.service /etc/systemd/system/
sudo systemctl enable --now gunshot-detector
sudo journalctl -u gunshot-detector -f
```

## Architecture

```text
┌─────────────────┐
│  Audio Source   │  (I2S/ALSA microphone)
│  + GPS/PPS      │
│  + Env Sensors  │
└────────┬────────┘
         ▼
┌─────────────────┐
│   Processing    │  (HPF filter, mono conversion, gain)
└────────┬────────┘
         ▼
┌─────────────────┐
│   Detectors     │  (Aubio onset detection, threshold)
└────────┬────────┘
         ▼
┌─────────────────┐
│   Event Bus     │  (in-process pub/sub)
└────────┬────────┘
         ▼
┌─────────────────┐
│    Outputs      │  (MQTT)
└─────────────────┘
         │ MQTT
         ▼
  MQTT Broker  →  Trilateration Server  →  Dashboard
```

Each node operates independently. Network failures don't affect local detection.

## Project Structure

```text
gds/
├── main.py                 # entry point
├── src/
│   ├── core/               # event bus, logging
│   ├── audio/              # audio sources and pipeline nodes
│   ├── processing/         # signal processing (HPF, gain, etc.)
│   ├── detection/          # detection algorithms (Aubio, threshold)
│   ├── output/             # MQTT output
│   ├── sensors/            # GPS, environmental sensors
│   ├── monitoring/         # system monitoring (CPU, memory, disk, temperature)
│   └── config/             # configuration management
├── scripts/
│   ├── setup_dev.py        # one-command dev setup
│   ├── trilateration_server.py  # central positioning server
│   └── update_requirements.py  # regenerate requirements files
├── tests/                  # pytest suite
├── tools/                  # diagnostic tools (gps_test.py, env_test.py)
├── examples/               # config.example.yaml
└── docs/                   # documentation
```

## Documentation

| Doc | Contents |
| --- | -------- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, event bus, MQTT topics, trilateration algorithm, event flow |
| [docs/SETUP.md](docs/SETUP.md) | Hardware wiring, GPS/PPS, sensors, fleet deployment |
| [docs/GPS_PPS_TIMING.md](docs/GPS_PPS_TIMING.md) | GPS PPS timing deep-dive — accuracy, chrony setup, verification, common issues |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Testing guide, platform abstraction, security audit |
| [docs/STATUS.md](docs/STATUS.md) | Component status, roadmap, future features |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

## Troubleshooting

**Audio device not found:**

```bash
arecord -l                   # list ALSA devices
cat /proc/asound/cards
```

**GPS not getting fix:**

```bash
cgps -s                      # terminal monitor
python tools/gps_test.py --check
```

Ensure antenna has clear sky view; first fix takes 5–15 minutes cold start.

**MQTT connection issues:**

```bash
mosquitto_sub -h <broker> -t '#' -v
```

**High CPU usage:** Increase `audio.buffer_size`, increase detection `hop_size`, disable unused detectors.

## License

MIT License — see [LICENSE](LICENSE)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). PRs welcome.
