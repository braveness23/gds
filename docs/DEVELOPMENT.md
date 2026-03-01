# Development Guide

> **TL;DR:** Run `python scripts/setup_dev.py` for one-command setup. Tests live in `tests/` with unit, integration, and hardware tiers (72% coverage). Key open items: platform abstraction (partially complete), security hardening (all critical/high-priority issues resolved).

---

## Development Setup

### One-Command Setup (Recommended)

```bash
python scripts/setup_dev.py
```

This creates `.venv/`, installs all dependencies, configures pre-commit hooks, and validates the setup.

### Manual Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .[dev]
pre-commit install
pytest                       # validate setup
```

Always use `./.venv/bin/python` explicitly in scripts/automation rather than relying on shell activation.

### Dependency Management

`setup.py` is the single source of truth for all Python dependencies. **Never edit `requirements*.txt` directly.**

```bash
# Add a dependency: edit setup.py, then:
python scripts/update_requirements.py
pip install -e .[dev]
```

Pre-commit will fail if `requirements*.txt` is out of sync with `setup.py`.

---

## Testing

### Philosophy

This system has unique challenges: real-time audio, hardware dependencies, microsecond timing, distributed coordination. The strategy:

1. **Unit tests** — individual components, all dependencies mocked
2. **Integration tests** — components together, hardware mocked
3. **Hardware tests** — real hardware, run manually
4. **System tests** — full pipeline with recorded audio files

### Running Tests

```bash
pytest                              # all tests
pytest tests/unit/                  # fast unit tests only
pytest tests/integration/           # integration tests
pytest --cov=src --cov-report=html  # with coverage (view htmlcov/index.html)
pytest -v                           # verbose output
pytest -s                           # show print statements
pytest -x                           # stop on first failure
```

### Test Markers

```bash
pytest -m unit          # unit tests only
pytest -m integration   # integration tests only
pytest -m hardware      # hardware tests (requires physical hardware)
pytest -m "not hardware"  # skip hardware tests
```

### Directory Structure

```text
tests/
├── conftest.py            # shared fixtures (event_bus, audio buffers, mock GPS)
├── unit/                  # fast tests, no I/O
│   ├── test_config.py
│   ├── test_event_bus.py
│   ├── test_sensors.py
│   └── ...
├── integration/           # slower, use mock services
│   ├── test_audio_pipeline.py
│   ├── test_mqtt_integration.py
│   └── ...
├── hardware/              # requires physical hardware
│   └── (empty — needs test procedures written)
└── mocks/
    ├── mock_mqtt.py       # MockMQTTClient with in-process pub/sub
    └── ...
```

### Shared Fixtures (`conftest.py`)

```python
# Available in all tests:
event_bus       # fresh EventBus per test
test_config     # Config with MQTT disabled
silent_audio    # np.zeros(1024) AudioBuffer
impulse_audio   # sharp impulse + exponential decay (gunshot-like)
noise_audio     # np.random.randn * 0.1 AudioBuffer
mock_paho_mqtt  # patches paho.mqtt.client.Client
```

### Mock Implementations

**`tests/mocks/mock_mqtt.py` — MockMQTTClient**

- Simulates broker in-process
- Shared message bus across all instances
- `MockMQTTClient.get_messages(topic)` — inspect published messages
- `MockMQTTClient.reset()` — clear between tests

**Mock GPS:**

```python
from sensors.mock_gps import MockGPSDevice
gps = MockGPSDevice(latitude=37.7749, longitude=-122.4194, altitude=10.0)
```

**Mock audio source:** See `tests/mocks/` for `MockAudioSource` with configurable signal types: `silence`, `noise`, `sine`, `impulse`.

### Test Patterns

```python
# Unit test (fast, isolated)
def test_highpass_filter_attenuates_low_freq():
    hpf = HighPassFilterNode(cutoff_freq=5000, order=4)
    t = np.arange(1024) / 48000
    samples = np.sin(2 * np.pi * 100 * t).astype(np.float32)
    buffer = AudioBuffer(samples=samples, timestamp=0.0, sample_rate=48000, ...)
    filtered = hpf.process(buffer)
    assert np.sqrt(np.mean(filtered.samples**2)) < np.sqrt(np.mean(samples**2)) * 0.1

# Integration test (uses mock services)
def test_mqtt_publishes_detections(event_bus):
    MockMQTTClient.reset()
    with patch("src.output.mqtt_output.mqtt.Client", MockMQTTClient):
        mqtt_node = MQTTOutputNode(broker="localhost", ...)
        mqtt_node.connect()
        event_bus.publish(Event(EventType.DETECTION, ...))
        time.sleep(0.2)
        assert len(MockMQTTClient.get_messages("gunshot/detections")) >= 1
```

### Coverage Goals

| Tier | Target | Current |
| ---- | ------ | ------- |
| Unit tests | > 80% coverage | 72% overall |
| Integration tests | All critical paths | ✅ Complete |
| Hardware tests | Manual validation before deployment | ✅ Procedures documented |

**Current state:** 72% coverage (2900+ lines of tests added 2026-02-20). Core components >90% coverage. See [STATUS.md](STATUS.md).

---

## Platform Abstraction

> **Status:** Partially planned, not yet implemented.

**Problem:** Some code is Linux-specific and prevents running on Windows/macOS.

### Known Linux-Only Code

| File | Issue | Status |
| ---- | ----- | ------ |
| `src/audio/audio_nodes.py:149–165` | Loads `libasound.so.2` via ctypes | 🔴 Not guarded |
| `src/audio/audio_nodes.py:191–233` | Parses `/proc/asound/cards` | 🔴 Not guarded |
| `src/config/config.py` | Defaults use `/dev/pps0`, `/dev/serial0` | 🟡 Works but confusing on Windows |

### Good News

PyAudio (the core audio library) is already cross-platform — it handles ALSA (Linux), WASAPI (Windows), and CoreAudio (macOS) internally. The Linux-specific code is only for optional enhancements (ALSA error suppression, device name mapping). Both are already wrapped in `try/except` and fail gracefully.

### Planned Changes (see plan in git history)

1. Create `src/audio/platform_utils.py` with `is_linux()`, `supports_alsa_enhancements()`, etc.
2. Wrap ALSA-specific code in `if supports_alsa_enhancements():`
3. Create audio source factory function (mirrors GPS factory pattern)
4. Add platform-specific config defaults

---

## Security Audit

> **Audit date:** 2026-02-15 | **Updated:** 2026-02-20 | **Status:** ✅ All critical and high-priority issues resolved

### ~~🔴 Critical — Fix Before Any Deployment~~ ✅ All Resolved

#### ~~1. Hardcoded MQTT credentials in `config.yaml`~~ ✅ Fixed

`config.yaml` removed from version control. Credentials now supplied via environment variables (`GDS_MQTT_PASSWORD` and 8 others). See resolved section below.

#### ~~2. TLS certificate verification disabled~~ ✅ Fixed

`MQTTOutputNode` no longer falls back to `ssl.CERT_NONE` on TLS setup failure — it logs and raises.
`MQTTFleetCoordinator` now accepts `tls_ca_cert` / `tls_insecure` and uses the same verified-by-default TLS logic.

### ~~🟠 High — Fix This Sprint~~ ✅ All Resolved

#### ~~3. No GPS coordinate validation~~ ✅ Fixed

Added `validate_coordinates()` function with type and range validation. Validates latitude (-90 to 90), longitude (-180 to 180), and altitude. Rejects default (0,0) coordinates — requires explicit configuration. Validation enforced in both factory function and `StaticGPSDevice.__init__()` for defense-in-depth. 14 unit tests added. (Commit 3cfbcd5, 2026-02-20)

#### ~~4. MQTT Fleet Coordinator has no node identity verification~~ ✅ Fixed

Added multi-layered security to `MQTTFleetCoordinator`: (1) Node allowlist - only accept messages from authorized node_ids, (2) HMAC-SHA256 message authentication with shared secret, (3) Per-node rate limiting (configurable window and max messages). All security checks enforced in `_on_message()` before processing. 18 unit tests added. (Commit 00a2ef6, 2026-02-20)

### 🟡 Medium — Fix This Month

| Issue | File | Notes |
| ----- | ---- | ----- |
| Brittle ALSA device string parsing | `audio_nodes.py:195–233` | No regex validation; crashes on malformed `hw:abc,0` |
| Global EventBus singleton not thread-safe | `event_bus.py:200–210` | Race condition in `get_event_bus()` creation |
| Event queue silently drops events when full | `event_bus.py:75–144` | Queue size 1000 hardcoded; detection events lost |
| Config.save() swallows exceptions | `config.py:191–208` | Caller can't know save failed |
| Missing type hints | `gps.py`, `mqtt_output.py` | Factory functions lack return type annotations |

### ✅ Resolved

- **GPS coordinate validation** — `validate_coordinates()` with type/range checks; rejects default (0,0) (commit 3cfbcd5, 2026-02-20)
- **MQTT Fleet Coordinator authentication** — node allowlist, HMAC-SHA256, rate limiting (commit 00a2ef6, 2026-02-20)
- MQTT topic validation — validated in `MQTTOutputNode.__init__`
- Broad exception handling — narrowed across 7 core source files (commit 1b08273)
- TLS cert verification — removed insecure fallback; `MQTTFleetCoordinator` now has proper TLS options
- Credential injection — `GDS_MQTT_PASSWORD` and 8 other env vars override config at startup
- Hardcoded credentials — `config.yaml` removed from version control; credentials via env vars only

### Progress Tracking

**Blockers for production:**

- ✅ Hardcoded credentials — `config.yaml` removed; env vars in use
- ✅ TLS validation — no insecure fallback
- ✅ Secrets management — env var injection at startup
- ✅ GPS coordinate validation — rejects invalid coordinates and dangerous defaults
- ✅ MQTT authentication — node allowlist, HMAC signing, rate limiting

**Production-ready when:**

- ✅ All CRITICAL issues resolved
- ✅ All HIGH-priority security issues resolved (as of 2026-02-20)
- ✅ Test coverage > 70% (currently 72% as of 2026-02-20)
- 🟡 Security review — medium-priority issues remain (brittle ALSA parsing, EventBus thread safety, etc.)

---

## Code Quality

### Style Tools

| Tool | Purpose | Config |
| ---- | ------- | ------ |
| Black | Formatting | `pyproject.toml` (line length 100) |
| Ruff | Linting + imports | `pyproject.toml` |
| mypy | Type checking | `pyproject.toml` (Python 3.7+) |
| pre-commit | Run all on commit | `.pre-commit-config.yaml` |

```bash
black src/              # format
ruff check src/         # lint
mypy src/               # type check
pre-commit run --all-files  # run all checks
```

### Pre-commit Hooks

`.pre-commit-config.yaml` runs: end-of-file-fixer, trailing-whitespace, check-yaml, ruff (with `--fix`, including import sorting), black, and a custom `sync-requirements` hook.

---

## CI/CD

A GitHub Actions workflow (`.github/workflows/ci.yml`) runs on push/PR:

- Unit tests on Ubuntu
- Integration tests
- Coverage reporting

Hardware tests are excluded from CI (require physical hardware).
