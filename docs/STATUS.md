# Project Status & Roadmap

> **Last updated:** 2026-03-10 | **Overall completeness:** ~85–90%

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
| **System monitoring** | ✅ 85% | CPU, memory, disk, temperature via psutil (314 lines, 86% test coverage) |
| **Remote configuration** | ✅ 80% | MQTT-based client/server with safety checks, HMAC auth (2490 lines, 75-91% test coverage) |
| **Timing/synchronization** | ✅ 80% | `NTPClock` in `src/timing/ntp_clock.py` — NTP offset monitor with TIMING events; GPS PPS handled at OS level via chrony |
| **File logger output** | ✅ 90% | `FileLoggerNode` in `src/output/file_logger.py` — rotating JSONL, 16 unit tests |
| **Buffer saver output** | ✅ 85% | `BufferSaverNode` in `src/output/buffer_saver.py` — WAV+JSON capture with pre/post window, 18 unit tests |
| **Tests** | ✅ 78%+ | 396+ unit tests passing, comprehensive unit + integration suite |

---

## Critical Gaps

### ~~1. Timing/Synchronization~~ ✅ Implemented

`src/timing/ntp_clock.py` — NTPClock monitors offset against an NTP server and publishes TIMING events when drift exceeds `max_offset_ms` (default 10ms = 3.4m trilateration error). GPS PPS timing is handled at the OS level via chrony. See [GPS_PPS_TIMING.md](GPS_PPS_TIMING.md).

**Remaining:** Validate PPS hardware integration end-to-end on real Pi hardware.

### ~~2. System Monitoring~~ ✅ Implemented

`src/monitoring/system_monitor.py` — CPU, memory, disk, temperature monitoring via psutil. 314 lines, 86% test coverage.

### ~~3. Remote Configuration~~ ✅ Implemented

`src/remote_config/` — MQTT-based remote configuration with client/server architecture, safety checks (blocked paths, risk assessment), and HMAC-SHA256 message authentication. 2490 lines across 4 modules, 75-91% test coverage.

### 4. Test Coverage — ✅ Target Met

78%+ coverage (target: >70%). 396+ unit tests passing. Core components (event bus, config, detection, sensors) have >85% coverage.

### 5. ML Detection — Not Implemented

No ML detector class exists yet. Aubio onset detection works well as the primary detector and handles most gunshot events reliably.

---

## Completion Roadmap

### Phase 1 — Make It Work ✅ Complete

1. ✅ `FileLoggerNode` — JSONL rotating log, local fallback when MQTT down
2. ✅ `BufferSaverNode` — WAV + JSON sidecar capture around detections
3. Deploy to real Raspberry Pi hardware; fix runtime issues
4. Test trilateration with 3+ nodes

### Phase 2 — Make It Observable ✅ Complete

1. ✅ `src/monitoring/system_monitor.py` (CPU, memory, disk, temperature via psutil)
2. ✅ Health metrics publishing

### Phase 3 — Make It Manageable ✅ Complete

1. ✅ `src/remote_config/` — MQTT-based client/server architecture
2. ✅ Safety checks, risk assessment, HMAC authentication

### Phase 4 — Make It Accurate (partial ✅)

1. ✅ NTP offset monitoring — `NTPClock` implemented with TIMING events
2. Validate PPS hardware integration end-to-end on real Pi hardware
3. Integrate environmental sensor data into trilateration server

### Phase 5 — Make It Robust ✅ Complete

1. ✅ Unit tests to > 70% coverage (currently 77%)
2. ✅ Integration test suite (with mock services)
3. ✅ Hardware test procedures (GPS, sensors, audio)
4. ✅ Security hardening (GPS validation, MQTT auth with HMAC, rate limiting)
5. ⚠️ Error recovery and circuit breakers (partially implemented)

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
