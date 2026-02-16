# Gunshot Detection System

[![CI](https://github.com/braveness23/gds/actions/workflows/ci.yml/badge.svg)](https://github.com/braveness23/gds/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.7%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

A distributed acoustic gunshot detection and trilateration system designed for Raspberry Pi fleets with GPS/PPS timing, environmental sensors, and mesh networking capabilities.

## Features

- **High-Precision Timing**: GPS PPS and NTP synchronization for microsecond-level timestamp accuracy
- **Multiple Detection Methods**:
  - Aubio onset detection (fast, low-latency)
  - ML-based classification (high accuracy)
  - Simple threshold detection (fallback)
- **Environmental Sensors**: Temperature, humidity, and pressure monitoring
- **GPS Location**: Real-time position tracking
- **Mesh Networking**: MQTT, Meshtastic, and LoRa support
- **Remote Configuration**: Manage fleet configuration via MQTT or HTTP API
- **System Monitoring**: CPU, memory, disk, network, and audio buffer health
- **Modular Pipeline**: Plug-and-play audio processing nodes

## Hardware Requirements

### Minimum Setup
- Raspberry Pi 3B+ or later
- I2S MEMS microphone (or USB audio interface)
- MicroSD card (16GB+)

### Recommended Setup
- Raspberry Pi 4/5
- I2S MEMS microphone
- GPS module with PPS output
- BME280 or DHT22 temperature/humidity sensor
- Meshtastic radio or LoRa module (optional)

## Software Requirements

- Raspberry Pi OS (64-bit recommended)
- Python 3.7+
- gpsd (for GPS)
- ALSA audio drivers

## Installation

### 1. System Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install system packages
sudo apt install -y python3-pip python3-dev python3-venv \
    libasound2-dev portaudio19-dev libportaudio2 \
    gpsd gpsd-clients python3-gps \
    git

# Install aubio
sudo apt install -y aubio-tools libaubio-dev libaubio-doc
```

### 2. Python Environment

```bash
# Clone repository
git clone https://github.com/yourusername/gunshot-detection-system.git
cd gunshot-detection-system

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install package
pip install -e .
```

### 3. Optional: Sensor Dependencies

For environmental sensors (BME280/DHT22):
```bash
pip install -r requirements.txt adafruit-circuitpython-bme280 adafruit-circuitpython-dht
```

For Meshtastic:
```bash
pip install meshtastic
```

## Configuration

### 1. Create Configuration File

Copy the example config:
```bash
cp examples/config.example.yaml config.yaml
```

Edit `config.yaml` with your settings:
```yaml
system:
  node_id: "pi_gunshot_001"  # Unique ID for this node

audio:
  source_type: "alsa"
  device: "hw:0,0"  # Your audio device
  sample_rate: 48000

sensors:
  gps:
    enabled: true
  environment:
    enabled: true
    sensor_type: "BME280"  # or "DHT22", "DHT11"

output:
  mqtt:
    enabled: true
    broker: "192.168.1.100"  # Your MQTT broker
    topic: "gunshot/detections"
```

### 2. Test Audio Device

Find your audio device:
```bash
arecord -l
```

Test recording:
```bash
arecord -D hw:0,0 -f S32_LE -r 48000 -c 1 -d 5 test.wav
aplay test.wav
```

### 3. Configure GPS (if using)

Edit `/etc/default/gpsd`:
```
DEVICES="/dev/ttyAMA0"  # Or your GPS serial device
GPSD_OPTIONS="-n"
START_DAEMON="true"
```

Restart gpsd:
```bash
sudo systemctl restart gpsd
sudo systemctl enable gpsd
```

Test GPS:
```bash
cgps -s
```

## Usage

### Command Line

Run the detector:
```bash
python src/main.py --config config.yaml
```

### Systemd Service

Install as a system service:
```bash
sudo cp systemd/gunshot-detector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable gunshot-detector
sudo systemctl start gunshot-detector
```

Check status:
```bash
sudo systemctl status gunshot-detector
```

View logs:
```bash
sudo journalctl -u gunshot-detector -f
```

## Remote Configuration

### MQTT Configuration

Set a config value:
```bash
mosquitto_pub -h <broker> -t "gunshot/config/<node_id>/set/detection/aubio/threshold" -m "0.7"
```

Get current config:
```bash
mosquitto_pub -h <broker> -t "gunshot/config/<node_id>/get" -m ""
mosquitto_sub -h <broker> -t "gunshot/config/<node_id>/current"
```

### HTTP API

Get config:
```bash
curl http://<node_ip>:8080/config
```

Set value:
```bash
curl -X POST http://<node_ip>:8080/config/set \
  -H "Content-Type: application/json" \
  -d '{"path": "detection.aubio.threshold", "value": 0.7}'
```

## Architecture

```
┌─────────────────┐
│  Audio Source   │ (I2S/ALSA)
│  + GPS/PPS      │
│  + Sensors      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Processing    │
│  - HPF Filter   │
│  - Mono Conv    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Detectors     │
│  - Aubio        │
│  - ML Model     │
│  - Threshold    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Event Bus     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Outputs      │
│  - MQTT         │
│  - Meshtastic   │
│  - LoRa         │
│  - File Logger  │
└─────────────────┘
```

## Trilateration

For accurate gunshot localization:

1. **Synchronize Clocks**: All nodes must use GPS PPS or NTP
2. **Deploy Grid**: Position nodes in a grid covering your area
3. **Collect Data**: Each node timestamps detections with microsecond precision
4. **Calculate Position**: Central server uses time-of-arrival differences

Example trilateration server (separate repository recommended):
```python
# Simplified example - see docs for full implementation
from scipy.optimize import least_squares

def trilaterate(detections):
    """
    detections: [(lat, lon, alt, timestamp), ...]
    Returns: (lat, lon, alt) of gunshot origin
    """
    # Implement multilateration algorithm
    pass
```

## Monitoring

Subscribe to health events:
```bash
mosquitto_sub -h <broker> -t "gunshot/+/health"
```

System metrics are published every 5 seconds including:
- CPU temperature and usage
- Memory usage
- Disk space
- Audio buffer health
- Detection statistics

## Development

### Project Structure

```
gunshot-detection-system/
├── src/
│   ├── core/           # Event bus, base classes
│   ├── audio/          # Audio sources
│   ├── processing/     # Signal processing nodes
│   ├── detection/      # Detection algorithms
│   ├── output/         # Output nodes (MQTT, etc)
│   ├── sensors/        # GPS, environmental sensors
│   ├── monitoring/     # System monitoring
│   └── config/         # Configuration management
├── examples/           # Example configs
├── systemd/            # Service files
├── tests/              # Unit tests
└── docs/               # Documentation
```

### Running Tests

```bash
pytest tests/
```

### Code Formatting

```bash
black src/
flake8 src/
```

## Troubleshooting

### Audio Issues

Check ALSA configuration:
```bash
arecord -l
cat /proc/asound/cards
```

Increase buffer size if getting underruns.

### GPS Issues

Check gpsd is running:
```bash
sudo systemctl status gpsd
cgps -s
```

Ensure antenna has clear sky view.

### High CPU Usage

- Reduce `audio.buffer_size`
- Increase detection `hop_size`
- Disable unused detectors

### Network Issues

Check MQTT broker connectivity:
```bash
mosquitto_sub -h <broker> -t '#' -v
```

## License

MIT License - see LICENSE file

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

## Support

- GitHub Issues: https://github.com/yourusername/gunshot-detection-system/issues
- Documentation: https://github.com/yourusername/gunshot-detection-system/wiki

## Acknowledgments

- Aubio library for onset detection
- Meshtastic for mesh networking
- The open source community
