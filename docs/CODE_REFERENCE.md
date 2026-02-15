# Code Reference - From Initial Conversation

This document contains all the Python code designed in the initial conversation.
Copy these implementations into the corresponding files in the project.

## Table of Contents

1. [Audio Nodes](#audio-nodes)
2. [Processing Nodes](#processing-nodes)
3. [Detection Nodes](#detection-nodes)
4. [Output Nodes](#output-nodes)
5. [Sensors](#sensors)
6. [Monitoring](#monitoring)
7. [Timing](#timing)
8. [Remote Configuration](#remote-configuration)
9. [Main Application](#main-application)

---

## Audio Nodes

### File: `src/audio/audio_nodes.py`

**Key Classes:**
- `AudioBuffer` - Timestamped audio data with metadata
- `AudioNode` - Base class for all audio processing nodes
- `AudioSourceNode` - Base class for audio sources
- `ALSASourceNode` - Capture from ALSA devices (I2S mics via ALSA)
- `I2SDirectSourceNode` - Direct I2S device reading for maximum timing control
- `FileSourceNode` - Read from audio files for testing/replay

**Implementation Notes:**
- All timestamps captured immediately at buffer arrival for trilateration accuracy
- PPS clock offset support for microsecond-level precision
- Thread-safe callback architecture
- Buffer metadata includes sample_rate, channels, timestamp, buffer_index

**Key Design Decision:**
We chose to timestamp at the earliest possible moment (in the audio callback) 
rather than later in processing, because trilateration accuracy depends on 
knowing exactly when the sound arrived at the microphone.

**Status:** Code provided in conversation, needs to be copied to file

---

## Processing Nodes

### File: `src/processing/processing_nodes.py`

**Key Classes:**
- `MonoConversionNode` - Convert stereo to mono
- `HighPassFilterNode` - Remove low-frequency noise (configurable cutoff, default 5kHz)
- `GainNode` - Apply gain/attenuation
- `BufferSplitterNode` - Split audio to multiple outputs (parallel processing)
- `RMSCalculatorNode` - Calculate RMS levels

**Implementation Notes:**
- HighPassFilter uses scipy second-order sections (SOS) for numerical stability
- Filter maintains state (zi) for continuous processing across buffers
- Supports both Butterworth and Chebyshev filter types
- All nodes pass through AudioBuffer objects unchanged (immutable pattern)

**Key Design Decision:**
We use 5kHz high-pass by default because gunshots have most energy above 5kHz,
and this removes environmental noise (wind, traffic, voices) below that frequency.

**Status:** Code provided in conversation, needs to be copied to file

---

## Detection Nodes

### File: `src/detection/detection_nodes.py`

**Key Classes:**
- `AubioOnsetNode` - Fast onset detection using aubio library
  - Methods: complex, energy, hfc, mkl, phase, specdiff, specflux, kl, wphase
  - Default: 'complex' (best for transient detection)
  - Configurable hop_size (smaller = lower latency, higher CPU)
  
- `MLGunShotDetectorNode` - Machine learning based classifier
  - Stub implementation ready for PyTorch/TensorFlow models
  - Sliding window processing
  - Confidence thresholding
  
- `ThresholdDetectorNode` - Simple amplitude threshold detector
  - Fast, low-complexity fallback
  - Minimum duration filtering

**Implementation Notes:**
- All detectors publish DetectionEvent to event bus
- Each event includes: timestamp, confidence, detector_type, metadata
- Detectors can run in parallel via BufferSplitterNode
- GPS and environmental data automatically attached to events

**Key Design Decision:**
Multiple detectors running in parallel allow us to use fast, sensitive detection
(Aubio) for triggering, with ML confirmation reducing false positives.

**Status:** Code provided in conversation, needs to be copied to file

---

## Output Nodes

### MQTT Output

**File:** `src/output/mqtt_output.py`

**Key Class:** `MQTTOutputNode`
- Subscribes to DetectionEvent on event bus
- Publishes to configured MQTT topic
- Includes node_id, location, environmental data
- QoS configurable (0=fast, 1=reliable, 2=guaranteed)

**Topic Structure:**
```
gunshot/detections           - All detection events
gunshot/<node_id>/health     - Health/monitoring
gunshot/config/<node_id>/*   - Remote configuration
```

### Meshtastic Output

**File:** `src/output/meshtastic_output.py`

**Key Class:** `MeshtasticOutputNode`
- Compact JSON messages for bandwidth-limited mesh
- Periodic position updates (every 5 min default)
- Periodic telemetry (every 10 min default)
- 237 byte message limit

**Implementation Notes:**
- Uses meshtastic Python library
- Supports both serial and TCP interfaces
- Message format optimized for size

### LoRa Output

**File:** `src/output/lora_output.py`

**Key Class:** `LoRaOutputNode`
- Stub implementation for LoRa radios
- Configurable frequency, bandwidth, spreading factor
- Compact message encoding

**Status:** All output nodes code provided in conversation

---

## Sensors

but both are supported for flexibility.

### File: `src/sensors/`

**Key Classes:**

1. **BaseGPSDevice**
   - Abstract base for all GPS devices (shared logic, interface)

2. **GPSReader**
   - Connects to gpsd for GPS data
   - Returns GPSData: lat, lon, alt, timestamp, fix_quality, satellites, hdop
   - Automatic PPS offset handling
   - Callbacks for position updates

3. **SerialGPSReader**
   - Reads NMEA sentences from serial GPS modules
   - Uses pyserial and pynmea2
   - Returns GPSData

4. **StaticGPSDevice**
   - Provides a fixed/static GPS position (for testing or surveyed nodes)

5. **MockGPSDevice**
   - Simulates GPS data for unit testing
   - Can simulate movement or static positions

6. **BME280Sensor**
   - I2C temperature, humidity, pressure sensor
   - Uses Adafruit CircuitPython library
   - Periodic reading thread
   - Returns EnvironmentData

7. **DHTSensor**
   - GPIO temperature and humidity sensor
   - Supports DHT22 and DHT11
   - Cheaper alternative to BME280
   - More susceptible to read errors (handled gracefully)

**Implementation Notes:**
- All sensors publish to event bus
- Rate-limited updates to avoid spam
- Graceful degradation if sensors unavailable
- Data automatically attached to detection events

**Key Design Decision:**
We chose BME280 as default because it's more reliable than DHT sensors,
but both are supported for flexibility.

**Status:** Code provided in conversation, needs to be copied to file

---

## Monitoring

### File: `src/monitoring/system_monitor.py`

**Key Classes:**

1. **SystemMonitor**
   - CPU usage, temperature, frequency
   - Memory and swap usage
   - Disk usage and I/O
   - Network traffic
   - Battery status (if available)
   - Process-specific metrics
   - Configurable alert thresholds
   - Alert cooldown to prevent spam

2. **AudioBufferMonitor**
   - Tracks buffers processed/dropped
   - Calculates drop rate percentage
   - Measures buffer timing jitter
   - Reports performance metrics

3. **DetectionMonitor**
   - Tracks detections per detector type
   - Average confidence scores
   - Detection rate (per minute, per hour)
   - Uptime statistics

**Implementation Notes:**
- All monitoring publishes to EventType.HEALTH
- CPU temperature reading tries multiple methods (Pi-specific)
- Metrics published every 5 seconds (configurable)
- Rolling statistics for network/disk I/O

**Key Design Decision:**
System monitoring is crucial for fleet management - you need to know if a node
is malfunctioning before it fails completely.

**Status:** Code provided in conversation, needs to be copied to file

---

## Timing

### File: `src/core/timing.py`

**Key Classes:**

1. **NTPClock**
   - Synchronizes with NTP server
   - Calculates and maintains time offset
   - Periodic re-sync (every 5 min default)
   - Publishes timing events to event bus
   - Falls back gracefully if NTP unavailable

2. **PPSClock**
   - Reads GPS PPS (pulse-per-second) signal
   - Provides microsecond-accurate timing
   - Can be calibrated against NTP
   - Essential for trilateration accuracy

**Implementation Notes:**
- NTP provides ~10ms accuracy (good enough for many applications)
- PPS provides <1μs accuracy (critical for trilateration)
- Both can run simultaneously (PPS for precision, NTP for absolute time)
- Offset applied to all timestamps

**Key Design Decision:**
For accurate trilateration, you need <1ms timing accuracy across the fleet.
PPS is the only realistic way to achieve this with Raspberry Pi.

**Status:** Code provided in conversation, needs to be copied to file

---

## Remote Configuration

### Files:
- `src/config/remote_config.py` - Core config management
- `src/config/mqtt_config_bridge.py` - MQTT interface
- `src/config/meshtastic_config_bridge.py` - Meshtastic interface
- `src/config/config_web_api.py` - HTTP API

**Key Classes:**

1. **RemoteConfigManager**
   - Validates configuration changes
   - Protected paths (can't change node_id remotely)
   - Optional confirmation workflow
   - Auto-save to file
   - Callback system for live updates

2. **MQTTConfigBridge**
   - MQTT topics for getting/setting config
   - Broadcast updates to all nodes ("all" topic)
   - Per-node specific updates
   - Confirmation/rejection workflow

3. **ConfigWebAPI**
   - Simple HTTP REST API
   - GET /config - retrieve config
   - POST /config/set - update value
   - POST /config/confirm - confirm pending change

**Topic Structure:**
```
gunshot/config/<node_id>/set/<path>      - Set config value
gunshot/config/<node_id>/get             - Get full config
gunshot/config/<node_id>/confirm         - Confirm pending
gunshot/config/<node_id>/current         - Current config (published)
gunshot/config/all/set/<path>            - Broadcast to all nodes
```

**Implementation Notes:**
- Validation prevents invalid values
- Confirmation mode requires approval before applying
- Callbacks allow hot-reload of running components
- Some changes (like audio config) require restart

**Key Design Decision:**
Fleet management requires remote config. MQTT provides publish-subscribe
for one-to-many updates. Confirmation prevents accidental misconfiguration.

**Status:** Code provided in conversation, needs to be copied to file

---

## Main Application

### File: `src/main.py`

**Key Class:** `GunshotDetectionSystem`

**Responsibilities:**
1. Load configuration
2. Initialize event bus
3. Set up timing (NTP/PPS)
4. Initialize sensors (GPS, environmental)
5. Build audio pipeline
6. Connect all nodes
7. Start monitoring
8. Handle shutdown gracefully

**Pipeline Construction:**
```
Audio Source (ALSA/I2S)
    ↓
Mono Conversion
    ↓
High-Pass Filter
    ↓
Splitter → Aubio Detector ──┐
        → ML Detector     ──┼→ Event Bus → MQTT
        → Threshold Det   ──┘           → Meshtastic
                                        → File Logger
```

**Callback System:**
- Config changes trigger callbacks
- Callbacks can update running components
- Example: Changing aubio threshold updates detector in real-time

**Signal Handlers:**
- SIGINT (Ctrl+C) - Graceful shutdown
- SIGTERM - Systemd stop

**Implementation Notes:**
- All component initialization wrapped in try/except
- Graceful degradation if optional components fail (GPS, sensors)
- Comprehensive logging at startup
- System startup event published to event bus

**Key Design Decision:**
The main app is just orchestration - all logic lives in nodes.
This makes testing individual components easy.

**Status:** Code provided in conversation, needs to be copied to file

---

## Architecture Principles from Conversation

### 1. Event-Driven Design
All components communicate via event bus. No direct dependencies between nodes.
This enables:
- Easy testing of individual components
- Runtime reconfiguration
- Parallel processing
- Monitoring/logging without code changes

### 2. Immutable Data Flow
AudioBuffer objects are never modified in-place. Each node returns new objects.
This prevents race conditions and makes reasoning about the code easier.

### 3. Timing First
Timestamps captured at the earliest possible moment and carried through pipeline.
GPS PPS support built in from the start. Trilateration accuracy is primary goal.

### 4. Graceful Degradation
System works without GPS, without environmental sensors, without remote config.
Each feature is optional and can be disabled. No hard dependencies.

### 5. Observable Everything
Event bus makes entire system observable. Every detection, every config change,
every health metric flows through the bus and can be logged/monitored/transmitted.

### 6. Fleet-Optimized
Remote configuration, MQTT coordination, unique node IDs, position tracking -
all designed for managing 10+ nodes from a central location.

---

## Conversation Context

### Original Question
You asked about using aubio for detecting non-musical onsets (gunshots).

### Key Decisions Made
1. Use aubio for fast detection
2. Add ML option for higher accuracy
3. Use GPS PPS for timing precision
4. Deploy on Raspberry Pi fleet
5. Use MQTT for coordination
6. Add Meshtastic for mesh networking
7. Include environmental sensors
8. Build modular node-based architecture
9. Add comprehensive monitoring
10. Support remote configuration

### Why This Architecture
- Needed microsecond timing → GPS PPS
- Needed fleet coordination → MQTT + event bus
- Needed field deployment → Meshtastic/LoRa
- Needed reliability → monitoring + graceful degradation
- Needed maintainability → modular nodes + documentation
- Needed scalability → remote config + deployment automation

---

## Implementation Checklist

- [ ] Copy audio_nodes.py code
- [ ] Copy processing_nodes.py code
- [ ] Copy detection_nodes.py code
- [ ] Copy mqtt_output.py code
- [ ] Copy meshtastic_output.py code
- [ ] Copy lora_output.py code
- [ ] Copy sensors.py code
- [ ] Copy system_monitor.py code
- [ ] Copy timing.py code
- [ ] Copy remote_config.py code
- [ ] Copy mqtt_config_bridge.py code
- [ ] Copy config_web_api.py code
- [ ] Copy main.py code
- [ ] Test imports: `python -c "import src.audio.audio_nodes"`
- [ ] Test basic run with file source
- [ ] Test with real microphone
- [ ] Deploy to first Pi
- [ ] Test GPS/PPS integration
- [ ] Test sensors
- [ ] Deploy to fleet

---

## Getting Help from Claude Code

When you start working in VS Code with Claude Code, you can reference this document
and say things like:

"I'm implementing the AudioSourceNode class. The design from our conversation 
specified that timestamps should be captured in the audio callback. Can you help 
me implement the _audio_callback method with proper PPS offset handling?"

Or:

"Looking at the HighPassFilterNode design, we decided to use second-order sections
for stability. Can you implement the scipy.signal.sosfilt approach with state 
management across buffers?"

The key is to reference specific design decisions from this document so Claude Code
understands the context and constraints.
