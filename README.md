# strix

[![CI](https://github.com/braveness23/gds/actions/workflows/ci.yml/badge.svg)](https://github.com/braveness23/gds/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.7%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**A distributed acoustic intelligence platform.** Named for *Strix* — the genus of owls that locate prey entirely by sound, using two precisely offset ears to triangulate position in three dimensions. That's exactly what this does.

*A single node is a strix. A network is a parliament.*

> *Sound travels at 343 meters per second. With precise enough clocks and enough ears,*
> *you can know exactly where it came from.*

📖 **[Read the full vision →](docs/VISION.md)** | 🚀 **[Quickstart — zero to simulation in 10 minutes →](docs/QUICKSTART.md)** | 🏗️ **[Architecture →](docs/ARCHITECTURE.md)**

---

strix turns any network of audio-capable devices into a real-time acoustic intelligence system. Nodes detect acoustic events, timestamp them with GPS-disciplined nanosecond precision, and publish to a shared broker. A central fusion server correlates arrivals across nodes using Time Difference of Arrival (TDOA) trilateration and calculates the source location — to within centimeters.

Nodes can be static or moving. They can run on a Raspberry Pi, an Android device, a ruggedized field tablet, a buoy, or any hardware with a microphone and GPS. The network can span a courtyard or a country.

**Use cases:** gunshot detection, battlefield acoustic awareness, drone and missile tracking, anti-poaching, disaster response survivor location, infrastructure monitoring, wildlife research.

**Current status: ~92–95% complete.** Core detection, MQTT pipeline, GPS/PPS timing (validated to 17ns), TDOA trilateration server (extracted to proper module), acoustic classifier plugin interface, environmental sensors, system monitoring, and remote configuration all work. Comprehensive test suite (78%+ coverage, 459+ tests). See [docs/STATUS.md](docs/STATUS.md).

## Hardware

strix runs on anything with a microphone and GPS. Tested on:

- Raspberry Pi 3B+ / 4 / 5 with GPS HAT (Adafruit Ultimate GPS HAT #2324 validated)
- Any Linux system with USB audio and serial/USB GPS
- Android and embedded targets: *in roadmap*

**For full timing accuracy** (required for trilateration):
- GPS module with PPS output
- GPS-disciplined clock via chrony (17ns achieved on Pi 3B+)
- BME280 temperature/humidity sensor (speed-of-sound correction)

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
├── main.py                      # entry point
├── src/
│   ├── core/                    # event bus, event types
│   ├── audio/                   # audio sources and pipeline nodes
│   ├── processing/              # signal processing (HPF, gain, splitter, etc.)
│   ├── detection/               # detection algorithms (Aubio, threshold)
│   ├── output/                  # MQTT, file logger, buffer saver
│   ├── sensors/                 # GPS, environmental sensors
│   ├── monitoring/              # system health (CPU, memory, disk, temperature)
│   ├── timing/                  # NTP clock monitoring
│   ├── remote_config/           # MQTT-based remote configuration
│   ├── trilateration/           # TDOA engine, fusion server, models
│   ├── classification/          # AcousticClassifier plugin interface
│   └── config/                  # configuration management
├── scripts/
│   ├── setup_dev.py             # one-command dev setup
│   ├── trilateration_server.py  # CLI wrapper for TrilaterationServer
│   └── update_requirements.py  # regenerate requirements files
├── tests/
│   ├── unit/                    # unit tests (459+ passing)
│   ├── integration/             # simulation + pipeline integration tests
│   ├── hardware/                # hardware-specific tests (Pi only)
│   └── simulation/              # acoustic simulation framework
├── tools/                       # diagnostic tools (gps_test.py, env_test.py)
├── examples/                    # config.example.yaml
└── docs/                        # documentation
```

## Documentation

| Doc | Contents |
| --- | -------- |
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | **Start here** — zero to simulation in 10 minutes, no hardware needed |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, strix/parliament vocabulary, TDOA algorithm, extension points |
| [docs/SETUP.md](docs/SETUP.md) | Three setup paths: Raspberry Pi, generic Linux, simulation-only |
| [docs/GPS_PPS_TIMING.md](docs/GPS_PPS_TIMING.md) | GPS PPS timing deep-dive — accuracy, chrony setup, verification |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Testing guide, platform abstraction, security audit |
| [docs/STATUS.md](docs/STATUS.md) | Component status, roadmap, future features |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute — classifiers, scenarios, output nodes, hardware testing |
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
