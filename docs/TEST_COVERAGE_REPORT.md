# Test Coverage Report

**Generated:** 2026-02-27
**Overall coverage:** 75% (2817 stmts, 691 missed)
**Test suite:** 385 collected, 357 passed, 10 skipped, **18 failed**

---

## 🔴 Critical: 18 Failing Tests

Fix these before improving coverage — red tests erode suite confidence.

| Failing Tests | Count | Root Cause |
|---|---|---|
| `test_mqtt_real.py` | 7 | Require live MQTT broker — should be mocked or marked `@pytest.mark.skip` |
| `test_remote_config_integration.py` | 7 | Same — live broker dependency |
| `test_permission_error` (config + logging) | 2 | Running as root, so `PermissionError` never raised |
| `test_risk_order` (remote_config_safety) | 1 | Apparent logic regression in `RiskLevel` ordering |
| `test_cpu_temperature_raspberry_pi` | 1 | Pi-specific `/sys/class/thermal` path — should be skipped on non-Pi |

---

## 📊 Coverage by Module

| Module | Coverage | Missed Lines | Priority |
|---|---|---|---|
| `audio/audio_nodes.py` | **51%** | 116 | 🔴 High |
| `sensors/gps.py` | **58%** | 108 | 🔴 High |
| `output/mqtt_output.py` | **60%** | 133 | 🔴 High |
| `remote_config/client.py` | 71% | 80 | 🟡 Medium |
| `remote_config/manager.py` | 75% | 74 | 🟡 Medium |
| `remote_config/server.py` | 76% | 62 | 🟡 Medium |
| `core/logging_utils.py` | 78% | 2 | 🟢 Low (tiny file) |
| `config/config.py` | 81% | 18 | 🟢 Low |
| `monitoring/system_monitor.py` | 85% | 22 | 🟢 Low |
| `sensors/environmental.py` | 85% | 22 | 🟢 Low |
| `core/event_bus.py` | 88% | 14 | 🟢 Low |
| `processing/processing_nodes.py` | 89% | 14 | 🟢 Low |
| `detection/detection_nodes.py` | **99%** | 1 | ✅ Excellent |

---

## 🎯 Proposed Improvements (Priority Order)

### 1. Fix failing tests (18 failures)

- Mock the MQTT broker in `test_mqtt_real.py` and `test_remote_config_integration.py`, or mark them `@pytest.mark.integration` and exclude from default run
- Skip permission tests when running as root: `if os.geteuid() == 0: pytest.skip(...)`
- Skip Pi temperature test with `pytest.mark.hardware` or check `/sys/class/thermal` existence

### 2. `audio/audio_nodes.py` — 51% (116 lines missed)

Nearly all uncovered code is in `ALSASourceNode` and `FileSourceNode`. Key targets:

- **`_audio_callback()`** — unit-testable by calling directly with mock `in_data` bytes. Cover 16-bit, 24-bit, 32-bit conversion; stereo reshape; status flag warning path
- **`stop()`** — mock `pyaudio.PyAudio`, verify stream closed and `self.running = False`
- **`FileSourceNode.process()`** — mock `soundfile.read()` to test read loop, EOF handling, looping
- **`ImportError` path** — patch `builtins.__import__` to simulate missing `pyaudio`

### 3. `sensors/gps.py` — 58% (108 lines missed, primarily lines 376–561)

- **`_reconnect()`** — mock `gps.gps()` to test reconnect + backoff logic
- **PPS timestamp integration** (lines 409–486) — testable with a mock serial port
- **Stats accumulation** (`no_fix_count`, `last_fix_time`) — exercise no-fix branch in `_parse_tpv_report`
- **`_parse_tpv_report()` error branches** — pass malformed dicts

### 4. `output/mqtt_output.py` — 60% (133 lines missed)

- **TLS setup branches** — mock `ssl` and `mqtt.Client.tls_set()` for: custom CA cert, insecure mode, system CA, and TLS failure
- **Callbacks** — call `_on_connect` / `_on_disconnect` / `_on_publish` directly with mock args (rc=0, rc!=0, etc.)
- **`publish_detection()` and `publish_health()`** — mock `self.client.publish()`, verify message format and topic structure
- **`_start_reconnect_thread()` + reconnect loop** — mock `connect()` to succeed on the Nth attempt

### 5. `remote_config/` modules — 71–76%

Shared pattern: error-handling branches and server-to-client protocol paths.

- **`client.py` lines 209–298** — config request/response error paths
- **`manager.py` lines 332–565** — rollback failure paths, concurrent change handling
- **`server.py` lines 197–228** — broadcast to multiple nodes, version conflict handling

---

## 💡 Structural Suggestions

- **Add `.coveragerc`** with `omit = tests/*, setup.py` and `exclude_lines` for `pragma: no cover` / `if TYPE_CHECKING:` for a cleaner baseline number
- **Mark `test_mqtt_real.py`** as `@pytest.mark.mqtt` and exclude from default run with `addopts = -m "not mqtt"` so `pytest` is always green locally
- **Coverage gate** — add `--cov-fail-under=75` to `pytest.ini` `addopts` to prevent regressions
