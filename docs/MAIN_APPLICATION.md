# Main Application Guide

## Overview

`main.py` is the primary entry point for the gunshot detection system. It orchestrates all components and provides a simple command-line interface for running the system.

## Quick Start

### Run with Default Config

```bash
python main.py
```

This will:
1. Load `config.yaml`
2. Initialize all components
3. Start audio capture
4. Begin detection
5. Publish to MQTT (if configured)
6. Run until Ctrl+C

### Run with Custom Config

```bash
python main.py --config /path/to/my_config.yaml
```

### Test Mode (File Input)

```bash
# Process a single audio file
python main.py --test test_audio.wav

# Process file without MQTT
python main.py --test test_audio.wav --no-mqtt
```

### Disable Services

```bash
# Disable MQTT output
python main.py --no-mqtt

# Disable GPS
python main.py --no-gps

# Both
python main.py --no-mqtt --no-gps
```

## Configuration

Edit `config.yaml` to customize:

### Essential Settings

```yaml
system:
  node_id: "gunshot_001"  # MUST be unique per node

audio:
  source: "alsa"          # or "file"
  device: "default"       # ALSA device name
  sample_rate: 48000

detection:
  aubio:
    enabled: true
    threshold: 0.3        # Lower = more sensitive

output:
  mqtt:
    enabled: true
    broker: "192.168.1.100"  # Your MQTT broker IP
    node_id: "gunshot_001"

location:
  latitude: 37.7749       # Your node's position
  longitude: -122.4194
  altitude: 10.0
```

### Finding Your ALSA Device

```bash
# List all audio devices
arecord -L

# Common devices:
# - "default" - System default
# - "hw:0,0" - Hardware device 0, subdevice 0
# - "plughw:1,0" - Hardware device 1 with plugin layer
# - "sysdefault:CARD=seeed2micvoicec" - Named device
```

Test recording:
```bash
arecord -D default -f S32_LE -r 48000 -c 1 test.wav
# Press Ctrl+C after a few seconds
aplay test.wav
```

## System Startup Behavior

When you run `main.py`:

```
1. Load Configuration
   ├─ Read config.yaml
   ├─ Apply command-line overrides
   └─ Validate settings

2. Initialize Event Bus
   ├─ Start thread-safe pub/sub system
   └─ Subscribe to detection events

3. Initialize GPS (if enabled)
   ├─ Connect to gpsd
   ├─ Start position updates
   └─ Wait for fix (if configured)

4. Initialize MQTT (if enabled)
   ├─ Connect to broker
   ├─ Subscribe to topics
   └─ Auto-reconnect on failure

5. Build Processing Pipeline
   ├─ Create audio source (ALSA or file)
   ├─ Add processing nodes (filters, gain)
   ├─ Add detection nodes (Aubio, threshold)
   └─ Connect all nodes

6. Start Audio Capture
   ├─ Open audio device
   ├─ Start capture thread
   └─ Begin processing buffers

7. Run Until Stopped
   ├─ Process audio continuously
   ├─ Detect events
   ├─ Publish to MQTT
   └─ Monitor system health
```

## Output & Monitoring

### Console Output

```bash
[System] Initializing gunshot detection system
[System] Config: config.yaml
[System] Node ID: gunshot_001

[System] Loading configuration...
[System] Initializing event bus...
[System] Initializing GPS...
[System] GPS ready: (37.774900, -122.419400)
[System] Initializing MQTT output...
[System] MQTT output initialized for node 'gunshot_001'
[System] Building processing pipeline...
  Audio source: alsa
  + Mono conversion
  + High-pass filter (5000Hz)
  + Splitter (for parallel detection)
  + Aubio detector (complex)

[System] Pipeline built with 4 nodes
[System] Initialization complete!

============================================================
Starting Gunshot Detection System
============================================================
[System] Starting audio capture...
[ALSA] Started ALSA capture - 48000Hz, 1ch, 1024 samples
[System] Audio capture started

============================================================
System Running
============================================================
Node ID: gunshot_001
Audio source: alsa
GPS: (37.774900, -122.419400)
MQTT: Connected to localhost

Press Ctrl+C to stop
============================================================

[Detection] aubio_complex at 1707436789.123456s (confidence: 0.95)
[Detection] aubio_complex at 1707436791.234567s (confidence: 0.88)
```

### Detection Events

When a sound is detected:

```
[Detection] aubio_complex at 1707436789.123456s (confidence: 0.95)
```

This means:
- Detector: `aubio_complex` (Aubio onset detector with complex method)
- Time: `1707436789.123456` (Unix timestamp)
- Confidence: `0.95` (95% certain)

The detection is also:
- Published to event bus
- Sent via MQTT to broker
- Logged to file (if configured)

### MQTT Messages

Listen to MQTT to see all fleet activity:

```bash
# Subscribe to all detections
mosquitto_sub -h localhost -t 'gunshot/detections' -v

# Subscribe to specific node
mosquitto_sub -h localhost -t 'gunshot/gunshot_001/#' -v

# Subscribe to everything
mosquitto_sub -h localhost -t 'gunshot/#' -v
```

Sample message:
```json
{
  "node_id": "gunshot_001",
  "timestamp": 1707436789.123456,
  "location": {
    "latitude": 37.7749,
    "longitude": -122.4194,
    "altitude": 10.5
  },
  "detection": {
    "detector_type": "aubio_complex",
    "confidence": 0.95,
    "buffer_index": 12345
  }
}
```

## Graceful Shutdown

Press Ctrl+C to stop:

```
^C
[System] Received signal 2

============================================================
Stopping Gunshot Detection System
============================================================
[System] Stopping audio capture...
[ALSA] Stopped ALSA capture
[System] Stopping GPS...
[GPSReader] Stopped GPS updates
[System] Disconnecting MQTT...
[MQTTOutput] Disconnected (published 42 messages, 0 failed)
[System] Stopping event bus...

[System] Uptime: 125.3s
[System] Events published: 45
[System] Events dispatched: 45
[System] Shutdown complete
```

## Running as System Service

### Install Service

```bash
# Copy service file
sudo cp systemd/gunshot-detector.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable on boot
sudo systemctl enable gunshot-detector

# Start service
sudo systemctl start gunshot-detector
```

### Monitor Service

```bash
# Check status
sudo systemctl status gunshot-detector

# View logs (live)
sudo journalctl -u gunshot-detector -f

# View recent logs
sudo journalctl -u gunshot-detector -n 100
```

### Control Service

```bash
# Start
sudo systemctl start gunshot-detector

# Stop
sudo systemctl stop gunshot-detector

# Restart
sudo systemctl restart gunshot-detector

# Disable auto-start
sudo systemctl disable gunshot-detector
```

## Troubleshooting

### Audio Device Not Found

**Error:** `ALSA: Failed to start audio stream`

**Solutions:**
```bash
# List devices
arecord -L

# Test device
arecord -D default -f S32_LE -r 48000 -c 1 -d 3 test.wav

# Update config.yaml with working device
audio:
  device: "hw:1,0"  # Your working device
```

### MQTT Connection Failed

**Error:** `[MQTTOutput] Connection failed`

**Solutions:**
```bash
# Check broker is running
sudo systemctl status mosquitto

# Test connection
mosquitto_pub -h localhost -t test -m "hello"

# Update config with correct broker
output:
  mqtt:
    broker: "192.168.1.100"  # Your broker IP
```

### No GPS Fix

**Error:** `[GPSReader] Timeout waiting for GPS fix`

**Solutions:**
```bash
# Check gpsd is running
sudo systemctl status gpsd

# Test GPS
cgps -s

# If no fix after 5 minutes, use static location
sensors:
  gps:
    enabled: false

location:
  latitude: 37.7749  # Your surveyed position
  longitude: -122.4194
  altitude: 10.0
```

### Permission Denied

**Error:** `Permission denied: /dev/ttyAMA0`

**Solutions:**
```bash
# Add user to required groups
sudo usermod -a -G audio,dialout,gpio pi

# Log out and back in
logout
```

### No Detections

**Problem:** System running but not detecting claps/sounds

**Solutions:**

1. **Test audio is working:**
```bash
# Record a test
arecord -D default -f S32_LE -r 48000 test.wav
# Clap loudly
# Press Ctrl+C
aplay test.wav

# Should hear your clap
```

2. **Lower detection threshold:**
```yaml
detection:
  aubio:
    threshold: 0.1  # Lower = more sensitive
```

3. **Check for clipping:**
```bash
# Monitor audio levels
alsamixer
# Adjust microphone gain
```

4. **Test with file:**
```bash
# Create test signal
python -c "import numpy as np, soundfile as sf; sr=48000; t=np.arange(sr)/sr; s=np.zeros(sr*2); s[sr//2]=1.0; s[sr//2:sr//2+sr]*=np.exp(-np.arange(sr)/100); sf.write('impulse.wav', s, sr)"

# Test with file
python main.py --test impulse.wav

# Should detect the impulse
```

## Advanced Usage

### Multiple Detectors

Enable both Aubio and Threshold for validation:

```yaml
detection:
  aubio:
    enabled: true
    threshold: 0.3
  
  threshold:
    enabled: true
    threshold_db: -15.0
```

Both will trigger independently. Look for events from both detectors:

```
[Detection] aubio_complex at 1707436789.123456s (confidence: 0.95)
[Detection] threshold at 1707436789.123458s (confidence: 0.87)
```

### Custom Processing Chain

Add gain if microphone is too quiet:

```yaml
processing:
  gain:
    db: 12.0  # +12dB = 4x amplification
```

Disable high-pass filter for testing:

```yaml
processing:
  highpass:
    enabled: false
```

### File-Based Testing

Create a test script:

```bash
#!/bin/bash
# test_detection.sh

# Test with various files
for file in test_sounds/*.wav; do
    echo "Testing: $file"
    python main.py --test "$file" --no-mqtt
    echo "---"
done
```

## Performance Tuning

### Lower Latency

```yaml
audio:
  buffer_size: 512  # Smaller buffer = lower latency
  
detection:
  aubio:
    hop_size: 256   # Process more frequently
```

**Trade-off:** Higher CPU usage

### Lower CPU Usage

```yaml
audio:
  buffer_size: 2048  # Larger buffer

detection:
  aubio:
    hop_size: 1024   # Process less frequently
```

**Trade-off:** Higher latency

### Best Settings for Raspberry Pi 4

```yaml
audio:
  sample_rate: 48000
  buffer_size: 1024
  
detection:
  aubio:
    hop_size: 512
```

This balances latency (~21ms) with CPU usage (~10-15%).

## Integration with Trilateration Server

On your central server:

```bash
# Terminal 1: Start trilateration server
python trilateration_server.py \
    --broker localhost \
    --time-window 30.0 \
    --min-nodes 3
```

On each Raspberry Pi node:

```bash
# Node 1
python main.py --config config_node1.yaml

# Node 2
python main.py --config config_node2.yaml

# Node 3
python main.py --config config_node3.yaml
```

When a sound occurs, all nodes detect and report. The trilateration server calculates the location.

## Next Steps

1. ✅ Test locally with microphone
2. ✅ Verify MQTT connection
3. ✅ Deploy to first Pi
4. ✅ Test with real sounds
5. ✅ Deploy to fleet (3+ nodes)
6. ✅ Start trilateration server
7. ✅ Monitor and tune thresholds

**You now have a complete, working system!** 🎯
