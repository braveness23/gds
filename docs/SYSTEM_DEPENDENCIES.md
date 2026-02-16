# System Dependencies by Platform

This document details platform-specific system packages required for the Gunshot Detection System.

## TL;DR - Quick Reference

| Platform | Key Packages |
|----------|--------------|
| **Raspberry Pi / Debian / Ubuntu** | `portaudio19-dev aubio-tools libsndfile1-dev gpsd` |
| **macOS** | `brew install portaudio aubio libsndfile` |
| **Windows** | Pre-compiled wheels (PyAudio, Aubio) or conda |

---

## Raspberry Pi / Debian / Ubuntu Linux

### Required Packages (Core Functionality)

```bash
sudo apt-get update
sudo apt-get install -y \
    python3-dev \
    python3-pip \
    python3-venv \
    build-essential
```

### Audio Processing Dependencies

```bash
sudo apt-get install -y \
    portaudio19-dev \
    libportaudio2 \
    libasound2-dev \
    libsndfile1-dev \
    aubio-tools \
    libaubio-dev
```

**What these do:**
- `portaudio19-dev` - Cross-platform audio I/O library (required for PyAudio)
- `libasound2-dev` - ALSA library for direct audio device access
- `libsndfile1-dev` - Library for reading/writing audio files
- `aubio-tools` & `libaubio-dev` - Audio onset detection (gunshot detection)

### GPS Dependencies (Optional - Production Pi only)

```bash
sudo apt-get install -y \
    gpsd \
    gpsd-clients \
    python3-gps
```

**What these do:**
- `gpsd` - GPS daemon for interfacing with GPS hardware
- `gpsd-clients` - Testing tools (cgps, gpsmon)
- `python3-gps` - System Python GPS library (note: also in pip requirements)

### Sensor Dependencies (Optional - If using GPIO sensors)

```bash
sudo apt-get install -y \
    libgpiod2
```

**What this does:**
- `libgpiod2` - GPIO access library for DHT22/DHT11 temperature/humidity sensors

### All-in-One Installation

```bash
# Complete Raspberry Pi setup
sudo apt-get update && sudo apt-get install -y \
    python3-dev python3-pip python3-venv build-essential \
    portaudio19-dev libportaudio2 libasound2-dev libsndfile1-dev \
    aubio-tools libaubio-dev \
    gpsd gpsd-clients python3-gps \
    libgpiod2 \
    git
```

---

## macOS

### Using Homebrew (Recommended)

```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install audio processing libraries
brew install portaudio aubio libsndfile

# Python (if not using system Python)
brew install python@3.11
```

### Notes for macOS
- GPS functionality is typically not used on macOS development machines
- GPIO sensors (BME280, DHT22) won't work on macOS (Raspberry Pi specific)
- macOS has CoreAudio built-in, but PyAudio still needs portaudio

---

## Windows

### Option 1: Pre-compiled Wheels (Recommended)

**PyAudio:**
- Official wheels available for recent Python versions
- Install with: `pip install pyaudio`
- If pip install fails, download from [Christoph Gohlke's repository](https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio)

**Aubio:**
- Limited Windows support
- May require unofficial wheel or conda
- File-based detection mode recommended on Windows

### Option 2: Conda (Alternative)

```powershell
# Install Miniconda/Anaconda, then:
conda create -n gds python=3.11
conda activate gds
conda install -c conda-forge pyaudio aubio
```

### Notes for Windows
- GPS functionality not typically used on Windows
- Hardware sensors (BME280, DHT22) won't work on Windows
- For full hardware testing, use Windows Subsystem for Linux (WSL 2)
- Audio recording works but may have different device naming

---

## Validation

### Check System Dependencies

```bash
# After installing system packages, validate:
python scripts/check_dependencies.py
```

This script checks:
- Python version (>=3.7)
- All pip packages installed
- System libraries accessible (aubio, pyaudio)
- Virtual environment status

### Manual Verification

**Test PyAudio:**
```python
python -c "import pyaudio; print(pyaudio.get_portaudio_version())"
```

**Test Aubio:**
```python
python -c "import aubio; print(aubio.__version__)"
```

**Test GPS (if installed):**
```bash
cgps  # Should show GPS status (requires GPS hardware)
```

---

## Troubleshooting

### Raspberry Pi: Audio Device Not Found

```bash
# List audio devices
arecord -l

# Test recording
arecord -D plughw:2,0 -f cd test.wav -d 5

# If device not found, check /proc/asound/cards
cat /proc/asound/cards
```

### Linux: PyAudio Installation Fails

```
error: portaudio.h: No such file or directory
```

**Solution:**
```bash
sudo apt-get install portaudio19-dev
pip install --upgrade pip
pip install pyaudio
```

### macOS: aubio Installation Fails

```bash
# Ensure Xcode Command Line Tools installed
xcode-select --install

# Reinstall aubio
brew reinstall aubio
pip install aubio
```

### Windows: PyAudio Binary Not Found

Download wheel from https://www.lfd.uci.edu/~gohlke/pythonlibs/ then:
```powershell
pip install pyaudio‑0.2.11‑cp311‑cp311‑win_amd64.whl
```

---

## Platform-Specific Notes

### Raspberry Pi Specific

**Enable UART for GPS:**
Add to `/boot/firmware/config.txt`:
```
enable_uart=1
dtoverlay=pps-gpio,gpiopin=18
```

**Enable I2C for BME280:**
```bash
sudo raspi-config
# Interface Options → I2C → Enable
```

**Configure gpsd:**
Edit `/etc/default/gpsd`:
```
DEVICES="/dev/ttyAMA0"
GPSD_OPTIONS="-n"
START_DAEMON="true"
```

### Cross-Platform Development

**Primary Development:**
- Windows/macOS for code development (no hardware required)
- Unit tests and integration tests work cross-platform

**Hardware Testing:**
- Raspberry Pi or Linux machine required for:
  - Audio capture testing
  - GPS integration testing
  - Environmental sensor testing

---

## See Also

- [README.md](README.md) - General setup instructions
- [scripts/setup_dev.py](scripts/setup_dev.py) - Automated dev setup script
- [scripts/check_dependencies.py](scripts/check_dependencies.py) - Dependency validator
