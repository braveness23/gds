# Project Status & Roadmap

> **Last updated:** 2026-03-16 | **Overall completeness:** ~92–95%

---

## Component Status

| Component | Status | Notes |
| --------- | ------ | ----- |
| **Core architecture** | ✅ 95% | Event bus, event types, pub/sub — production quality |
| **Configuration** | ✅ 90% | YAML/JSON, dot-notation, deep merge, defaults |
| **Audio pipeline** | ✅ 80% | ALSA source, file source, HPF, gain, mono, splitter |
| **Detection — Aubio** | ✅ Working | Onset detection, rate limiting, event bus integration |
| **Detection — Threshold** | ✅ Working | Simple amplitude threshold, min duration filtering |
| **Detection — ML** | ❌ 0% | Not implemented; `AcousticClassifier` plugin interface added |
| **MQTT output** | ✅ 95% | TLS/SSL, QoS, reconnect with backoff, event bus integration |
| **GPS integration** | ✅ 90% | gpsd, serial NMEA, static fallback; hardware validated (17ns) |
| **Environmental sensors** | ✅ 70% | BME280 + DHT22 implemented; needs hardware test |
| **Trilateration** | ✅ 98% | Extracted to `src/trilateration/`; engine + server + models |
| **Classification interface** | ✅ Done | `AcousticClassifier` plugin base class in `src/classification/` |
| **Main application** | ✅ 85% | Orchestrator, CLI, pipeline builder, signal handlers |
| **System monitoring** | ✅ 85% | CPU, memory, disk, temperature via psutil |
| **Remote configuration** | ✅ 80% | MQTT-based client/server with safety checks, HMAC auth |
| **Timing/synchronization** | ✅ 80% | `NTPClock` NTP offset monitor; GPS PPS handled via chrony |
| **File logger output** | ✅ 90% | Rotating JSONL, 16 unit tests |
| **Buffer saver output** | ✅ 85% | WAV+JSON capture with pre/post window, 18 unit tests |
| **Public API** | ✅ Done | `__all__` on all packages; `strix` namespace; `src/__init__.py` |
| **Tests** | ✅ 78%+ | 459+ unit tests passing, comprehensive suite |
| **Simulation framework** | ✅ Done | Multi-node, 7 scenarios, 26 integration tests |

---

## What shipped this weekend

- ✅ GPS/PPS hardware validation — 17ns clock offset on Pi 3B+ (see `GPS_PPS_VALIDATION_REPORT.md`)
- ✅ Multi-node acoustic simulation framework — 7 scenarios, 26 integration tests
- ✅ Framework extraction — `src/trilateration/` proper module; `scripts/trilateration_server.py` thin wrapper
- ✅ Public API cleanup — `__all__` on all packages, `strix` namespace, `src/__init__.py` v0.2.0
- ✅ Classifier plugin interface — `AcousticClassifier` base in `src/classification/`
- ✅ Docs rewrite — ARCHITECTURE, SETUP (3-path), QUICKSTART (new), CONTRIBUTING additions, STATUS update

---

## Critical gaps

### 1. ML classifier — not implemented

The `AcousticClassifier` interface is defined (`src/classification/base.py`). No trained model exists yet. Aubio onset detection handles the primary detection use case. ML would reduce false positives and add subtype classification (gunshot vs. car backfire, muzzle blast vs. ballistic crack).

### 2. Hardware end-to-end validation

Need: 3+ physical nodes with GPS PPS, MQTT broker, trilateration server — verify actual location accuracy matches simulation predictions.

### 3. Environmental sensor integration in trilateration

`TrilaterationEngine.update_speed_of_sound()` exists but the server doesn't yet pull live temperature from the fleet. This adds ~1m/°C temperature error at km ranges.

---

## Completion roadmap

### Phase 1 — Make It Work ✅ Complete

- ✅ `FileLoggerNode`, `BufferSaverNode`
- ✅ Core detection pipeline
- ✅ GPS integration (gpsd, PPS, static fallback)

### Phase 2 — Make It Observable ✅ Complete

- ✅ `SystemMonitorNode` (CPU, memory, disk, temperature)
- ✅ Health metrics publishing

### Phase 3 — Make It Manageable ✅ Complete

- ✅ Remote configuration (MQTT client/server, HMAC, safety checks)

### Phase 4 — Make It Accurate ✅ Mostly complete

- ✅ `NTPClock` — NTP offset monitoring with TIMING events
- ✅ GPS/PPS validated at 17ns offset (3 weeks of field data)
- 🔄 Integrate environmental sensors into trilateration server live

### Phase 5 — Make It Robust ✅ Complete

- ✅ Unit tests to > 70% (currently 78%+)
- ✅ Integration test suite (simulation framework)
- ✅ Hardware test procedures
- ✅ Security hardening (GPS validation, MQTT HMAC auth, rate limiting)

### Phase 6 — Classification Layer (next major milestone)

- [ ] Implement first `AcousticClassifier` — rule-based (spectral shape + attack envelope)
- [ ] Integrate classifier into detection pipeline
- [ ] Build training data pipeline using `BufferSaverNode` captures
- [ ] Evaluate ML options (TensorFlow Lite, Edge Impulse, ONNX)

### Phase 7 — Future features (deferred)

- Meshtastic / LoRa output
- Web dashboard with map overlay
- Docker containerization
- OTA updates
- Kalman filtering for moving sources
- Time-series database integration (InfluxDB/TimescaleDB)

---

## Deferred / future features

See below sections for full detail on each.

### Machine Learning Detection

**Priority:** Medium | **Complexity:** High

ML-based gunshot classifier with learned pattern recognition. Requires: training data (use `BufferSaverNode` captures), model architecture, MFCC/mel-spectrogram features, inference optimized for Raspberry Pi (TF Lite / Edge Impulse).

Config keys: `detection.ml.enabled`, `detection.ml.model_path`

### Meshtastic Output

**Priority:** Medium | **Complexity:** Medium

Mesh networking via LoRa radios for off-grid deployments. Requires: `MeshtasticOutputNode`, serial/USB comms.

Config keys: `output.meshtastic.*`

### Advanced Filtering

Only a HPF exists today. Future additions: low-pass, band-pass, notch filter, dynamic compression (AGC), noise gate. All would follow the `HighPassFilterNode` pattern.

### Trilateration Enhancements

- Kalman filtering for moving sources
- Bayesian position estimation
- Trajectory estimation
- Environmental sensor live integration
