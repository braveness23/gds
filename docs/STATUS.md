# Project Status & Roadmap

> **Last updated:** 2026-02-20 | **Overall completeness:** ~60–70%

---

## Component Status

| Component | Status | Notes |
| --------- | ------ | ----- |
| **Core architecture** | ✅ 95% | Event bus, event types, pub/sub — production quality |
| **Configuration** | ✅ 90% | YAML/JSON, dot-notation, deep merge, defaults |
| **Audio pipeline** | ✅ 80% | ALSA source, file source, HPF, gain, mono, splitter |
| **Detection — Aubio** | ✅ Working | Onset detection, rate limiting, event bus integration |
| **Detection — Threshold** | ✅ Working | Simple amplitude threshold, min duration filtering |
| **Detection — ML** | ❌ 0% | Not implemented; Aubio onset detection is primary detector |
| **MQTT output** | ✅ 95% | TLS/SSL, QoS, reconnect with backoff, event bus integration |
| **GPS integration** | ✅ 90% | gpsd, serial NMEA, static fallback; needs hardware test |
| **Environmental sensors** | ✅ 70% | BME280 + DHT22 implemented; needs hardware test |
| **Trilateration server** | ✅ 95% | 800+ line standalone server; TDOA, geometry scoring |
| **Main application** | ✅ 85% | Orchestrator, CLI, pipeline builder, signal handlers |
| **System monitoring** | ❌ 0% | `src/monitoring/` contains only `__init__.py` |
| **Remote configuration** | ❌ 0% | No MQTT/HTTP remote config implemented |
| **Timing/synchronization** | ❌ 0% | NTP/PPS clock classes not implemented |
| **File logger output** | ❌ 0% | No `src/output/file_logger.py` |
| **Buffer saver output** | ❌ 0% | No `src/output/buffer_saver.py` |
| **Tests** | ✅ 72% | Comprehensive unit + integration + hardware test suite (2900+ lines) |

---

## Critical Gaps

### 1. Timing/Synchronization — Trilateration Accuracy at Risk

No active time synchronization is implemented beyond the OS system clock. The GPS PPS integration in `docs/SETUP.md` disciplines the *system clock* — Python code just calls `time.time()` and benefits automatically.

**Impact:** 1ms timing error = 0.34m position error. Without PPS-disciplined clocks, nodes may have 10–100ms skew, producing location errors of hundreds of meters.

**What's needed:**

- `NTPClock` class for periodic sync + offset monitoring
- Verify PPS integration works end-to-end with actual hardware

### 2. System Monitoring — Zero Visibility

`src/monitoring/` has only an `__init__.py`. There is no CPU/memory/disk/temperature monitoring or health status publishing.

**What's needed:** `src/monitoring/system_monitor.py` using `psutil` to publish health metrics via MQTT.

### 3. Remote Configuration — Physical Access Required

All configuration requires physical access to each node. `examples/config.example.yaml` has a `remote_config` section but no code implements it.

### 4. Test Coverage — Approaching Production Readiness

72% coverage (target: >70%). Comprehensive test suite includes unit, integration, and hardware tests. Core components (event bus, config, GPS, sensors, MQTT) have >90% coverage. Remaining gaps in system monitoring and remote config (not yet implemented).

### 5. ML Detection — Not Implemented

No ML detector class exists yet. Aubio onset detection works well as the primary detector and handles most gunshot events reliably.

---

## Completion Roadmap

### Phase 1 — Make It Work (2–3 days)

1. Implement `FileLoggerNode` (JSONL format, local fallback when MQTT down)
2. Implement `BufferSaverNode` (WAV + metadata around detections)
3. Deploy to real Raspberry Pi hardware; fix runtime issues
4. Test trilateration with 3+ nodes

### Phase 2 — Make It Observable (1–2 days)

1. Implement `src/monitoring/system_monitor.py` (CPU, memory, disk, temperature)
2. Publish health metrics via MQTT

### Phase 3 — Make It Manageable (2–3 days)

1. Implement `src/config/remote_config.py`
2. Implement MQTT config bridge (get/set/confirm per node and broadcast)

### Phase 4 — Make It Accurate (2–3 days)

1. Implement and test NTP sync monitoring
2. Validate PPS hardware integration end-to-end
3. Integrate environmental sensor data into trilateration server

### Phase 5 — Make It Robust (3–5 days) ✅ 90% Complete

1. ✅ Unit tests to > 70% coverage (currently 72%)
2. ✅ Integration test suite (with mock services)
3. ✅ Hardware test procedures (GPS, sensors, audio)
4. ⚠️ Error recovery and circuit breakers (partially implemented)

### Phase 6 — Future Features (deferred)

- Meshtastic / LoRa outputs
- ML gunshot classifier
- Web dashboard
- Mobile app
- OTA updates

---

## Deferred / Future Features

These were removed or never implemented. All are in git history or documented below.

### Machine Learning Detection

**Priority:** Medium | **Complexity:** High

ML-based gunshot classifier (PyTorch/TensorFlow/ONNX) with learned pattern recognition. Requires: training data, model architecture selection, feature extraction (MFCC/mel-spectrogram), inference pipeline optimized for Raspberry Pi.

Config keys: `detection.ml.enabled`, `detection.ml.model_path`

Consider Edge Impulse or TensorFlow Lite for embedded optimization.

### Meshtastic Output

**Priority:** Medium | **Complexity:** Medium

Mesh networking via Meshtastic LoRa radios for off-grid deployments without WiFi/cellular. Requires: `MeshtasticOutputNode`, serial/USB communication, channel configuration.

Config keys: `output.meshtastic.*`

Hardware: T-Beam, Heltec LoRa32. Python library: `meshtastic` (pip).

### LoRa Output

**Priority:** Low | **Complexity:** High

Direct LoRa radio with custom protocol. Consider Meshtastic instead unless custom protocol is required.

### Buffer Saver Output

**Priority:** High | **Complexity:** Low

Saves audio buffers around detections as WAV files with JSON metadata. Critical for debugging false positives and building ML training datasets.

Config keys: `output.buffer_saver.*`
Format: `{timestamp}_{node_id}_{event_id}.wav` + JSON sidecar

### I2S Raw Source

**Priority:** Medium | **Complexity:** Medium

Direct I2S interface audio capture bypassing ALSA for lower latency. A complete implementation existed (`src/audio/i2s_raw_source.py`) but was not wired to `main.py`. Code is preserved in git history.

Requires: config option `audio.source_type: "i2s"`, platform abstraction (Linux only), integration testing.

---

## Future Ideas

### Advanced Detection

- Multi-stage detection (fast trigger → ML confirmation)
- Direction-of-arrival estimation (microphone array)
- Sound classification (gunshot vs fireworks vs car backfire)
- Muzzle blast vs ballistic crack separation
- Experiment with audio buffer size and its effect on detection latency and CPU performance

### Trilateration & Positioning

- Kalman filtering for moving sources
- Bayesian position estimation
- Visual map overlay (web dashboard)
- Trajectory estimation

### Networking

- LoRaWAN (TTN integration)
- Satellite backup (Iridium)
- Multi-hop mesh routing optimization

### Data & Analytics

- Time-series database (InfluxDB/TimescaleDB)
- Shot pattern heatmaps
- GeoJSON/KML export
- API for third-party integration
- Metrics and telemetry (node health, detection rates, pipeline throughput via Prometheus/Grafana)

### Power Management

- Solar panel integration
- Wake-on-sound triggering
- Dynamic power management

### Operations

- Docker containerization
- Ansible fleet provisioning
- OTA firmware updates
- Automatic node discovery
- Hooks for node-based config GUI (expose config/event hooks for a visual Node-RED-style editor)

### Security

- Certificate-based node authentication
- Message signing with shared secret
- Audit logging
- RBAC for remote configuration

### Developer Experience

- Documentation as code (e.g., Sphinx + autodoc to generate API docs from docstrings)
- IDE debugging configuration (VSCode `launch.json` for stepping through nodes, mocking hardware)
