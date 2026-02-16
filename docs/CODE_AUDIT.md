# Code Quality Audit Report
**Gunshot Detection System (GDS)**

**Date:** February 15, 2026
**Auditor:** Automated Code Analysis + Manual Review
**Status:** Post-Cleanup (Incomplete Features Removed)

---

## Executive Summary

This Python gunshot detection system demonstrates **reasonable code structure** after cleanup, but contains several **critical security issues**, **architectural concerns**, and **code quality violations** that require immediate attention before production deployment.

**Overall Assessment:** 5.5/10 - Early-stage project with good bones but critical security gaps

---

## 🚨 1. CRITICAL SECURITY ISSUES

### 1.1 Hardcoded Credentials in Configuration File
**SEVERITY: CRITICAL** 🔴
**File:** [config.yaml:79-84](config.yaml#L79-L84)

```yaml
output:
  mqtt:
    broker: "mqtt.daveschwinn.com"
    port: 8883
    username: "gunshot_detector"
    password: "Clavicle-Barge-Hull2"    # ❌ HARDCODED CREDENTIAL
    use_tls: true
    tls_insecure: true                   # ❌ INSECURE TLS DEFAULT
```

**Impact:**
- Real MQTT credentials exposed in version control
- Anyone with repository access can compromise MQTT broker
- Password visible in entire git history

**Fix Required:**
```bash
# 1. Remove from config immediately
# 2. Add to .gitignore
echo "config.yaml" >> .gitignore

# 3. Use environment variables instead
export GDS_MQTT_PASSWORD="your-password-here"

# 4. Update code to read from environment
password: "${GDS_MQTT_PASSWORD}"

# 5. Rotate the exposed password
# 6. Purge from git history
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch config.yaml' \
  --prune-empty --tag-name-filter cat -- --all
```

---

### 1.2 TLS Certificate Verification Disabled
**SEVERITY: CRITICAL** 🔴
**File:** [src/output/mqtt_output.py:118-140](src/output/mqtt_output.py#L118-L140)

```python
elif self.tls_insecure:
    # Accept self-signed / insecure certs
    self.logger.warning(
        "TLS enabled with insecure mode: certificate verification disabled"
    )
    self.client.tls_set(cert_reqs=ssl.CERT_NONE)  # ❌ VULNERABLE TO MITM
    self.client.tls_insecure_set(True)
```

**Even worse - Silent Security Downgrade (Lines 133-140):**
```python
except Exception:
    self.logger.exception(
        "Failed to configure TLS, attempting insecure fallback"
    )
    # ❌ DANGEROUS: Fallback accepts ANY certificate
    try:
        self.client.tls_set(cert_reqs=ssl.CERT_NONE)
        self.client.tls_insecure_set(True)
```

**Problems:**
- Vulnerable to Man-in-the-Middle (MITM) attacks
- Fallback silently degrades security on ANY error
- Default config has `tls_insecure: true`
- No distinction between "configured insecure" vs "failed secure setup"

**Fix Required:**
```python
# Remove fallback, fail loudly instead
except Exception:
    self.logger.error("TLS configuration failed - refusing to connect insecurely")
    raise  # Don't degrade security silently

# Update default config
tls_insecure: false  # Change default to secure
tls_ca_cert: "/etc/ssl/certs/ca-certificates.crt"  # Use system CA store
```

---

### 1.3 Missing Input Validation - GPS Coordinates
**SEVERITY: HIGH** 🟠
**File:** [src/sensors/gps.py:558-560](src/sensors/gps.py#L558-L560)

```python
lat = location_config.get("latitude", 0.0)
lon = location_config.get("longitude", 0.0)
alt = location_config.get("altitude", 0.0)

if lat == 0.0 and lon == 0.0:
    logger.warning("Using default location (0, 0)")  # ❌ Gulf of Guinea, Africa!
```

**Issues:**
- No validation: latitude should be in [-90, 90]
- No validation: longitude should be in [-180, 180]
- Accepts 0,0 (middle of ocean) as "default"
- No type checking (could pass strings, None, lists)
- Altitude unbounded (could be negative infinity)

**Fix Required:**
```python
def validate_coordinates(lat, lon, alt):
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        raise ValueError("Latitude and longitude must be numeric")

    if not -90 <= lat <= 90:
        raise ValueError(f"Latitude {lat} out of range [-90, 90]")

    if not -180 <= lon <= 180:
        raise ValueError(f"Longitude {lon} out of range [-180, 180]")

    if alt is not None and (alt < -500 or alt > 9000):
        logger.warning(f"Altitude {alt}m seems unusual")

    return lat, lon, alt

lat, lon, alt = validate_coordinates(
    location_config.get("latitude"),
    location_config.get("longitude"),
    location_config.get("altitude")
)
```

---

### 1.4 No Authentication for MQTT Fleet Coordinator
**SEVERITY: HIGH** 🟠
**File:** [src/output/mqtt_output.py:367-533](src/output/mqtt_output.py#L367-L533)

**Issues:**
- MQTTFleetCoordinator subscribes to all fleet data without access control
- No verification of node identity
- No rate limiting on commands
- Anyone can publish fake detection messages
- No message signing or authentication

**Recommendation:**
- Implement message signing with shared secret or PKI
- Add node identity verification
- Rate limit incoming messages
- Add command authentication

---

## 🟡 2. CODE SMELLS & JANKY PATTERNS

### 2.1 Brittle String Parsing for ALSA Devices
**SEVERITY: MEDIUM** 🟡
**File:** [src/audio/audio_nodes.py:195-233](src/audio/audio_nodes.py#L195-L233)

```python
# Extract card number from "hw:X,Y" or "plughw:X,Y"
_, card_dev = self.device.split(":", 1)  # ❌ Fails if device is "hw:" alone
card_num = int(card_dev.split(",")[0])   # ❌ ValueError if "hw:abc,0"

# Parse /proc/asound/cards (Linux-specific!)
with open("/proc/asound/cards", "r") as f:  # ❌ Doesn't exist on macOS/Windows
    lines = f.readlines()

for i in range(0, len(lines), 2):
    header = lines[i].strip()
    if header.startswith(str(card_num) + " "):
        # Fragile string parsing with multiple splits
        parts = header.split("]")
        start = header.find("[")
        end = header.find("]")
```

**Issues:**
- No validation of device string format
- Hardcoded `/proc/asound/cards` path (Linux-only)
- Multiple string operations without bounds checking
- Will crash on malformed input

**Fix Required:**
```python
import re

def parse_alsa_device(device_str):
    """Parse ALSA device string with validation."""
    match = re.match(r'^(plug)?hw:(\d+),(\d+)$', device_str)
    if not match:
        raise ValueError(f"Invalid ALSA device format: {device_str}")

    card_num = int(match.group(2))
    device_num = int(match.group(3))
    return card_num, device_num
```

---

### 2.2 Error Suppression Pattern
**SEVERITY: MEDIUM** 🟡
**File:** [src/audio/audio_nodes.py:149-165](src/audio/audio_nodes.py#L149-L165)

```python
# Suppress ALSA warnings
def py_error_handler(filename, line, function, err, fmt):
    pass  # ❌ Suppress ALL ALSA error messages

c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
asound = cdll.LoadLibrary("libasound.so.2")  # ❌ Hardcoded path
asound.snd_lib_error_set_handler(c_error_handler)
```

**Issues:**
- Silent suppression of ALL ALSA errors (including critical ones)
- Hardcoded library path (not portable)
- Broad exception catching on setup failure
- No way to know when real errors occur

**Recommendation:**
- Log errors at DEBUG level instead of suppressing
- Make error handler configurable
- Document why suppression is needed

---

### 2.3 Inconsistent String Formatting
**SEVERITY: LOW** 🟡

Multiple patterns used throughout codebase:
```python
# Pattern 1: f-strings (modern)
logger.info(f"Config: {config_path}")

# Pattern 2: % formatting (old)
logger.debug("Failed: %s", error)

# Pattern 3: .format() (intermediate)
"Device: {}".format(device)
```

**Recommendation:** Standardize on f-strings

---

## 🔧 3. BEST PRACTICE VIOLATIONS

### 3.1 Broad Exception Catching — RESOLVED ✅
**SEVERITY: MEDIUM** 🟡
**Status:** RESOLVED - All 49 instances in core source files fixed

**What was fixed:**
- Narrowed overly broad `except Exception` to specific exception types based on context
- Documented intentionally broad exceptions (callbacks, abstract methods, message handlers)
- Fixed across 7 core source files

**Files fixed:**
- ✅ [src/config/config.py](src/config/config.py) - 3 instances (narrowed all)
- ✅ [src/core/event_bus.py](src/core/event_bus.py) - 3 instances (narrowed 1, documented 2 for callbacks)
- ✅ [src/audio/audio_nodes.py](src/audio/audio_nodes.py) - 7 instances (narrowed 5, documented 2 for callbacks/real-time)
- ✅ [src/sensors/base.py](src/sensors/base.py) - 4 instances (all documented for abstract methods/callbacks)
- ✅ [src/output/mqtt_output.py](src/output/mqtt_output.py) - 9 instances (narrowed 8, documented 1 for message handling)
- ✅ [src/sensors/gps.py](src/sensors/gps.py) - 18 instances (all narrowed)
- ✅ [src/sensors/environmental.py](src/sensors/environmental.py) - 5 instances (all narrowed)
- ✅ [src/detection/detection_nodes.py](src/detection/detection_nodes.py) - Fixed in commit 1b08273

**Note:** Test files, tool scripts, and setup.py still have broad exceptions, which is acceptable for those contexts.

---

### 3.2 Missing Type Hints
**SEVERITY: MEDIUM** 🟡

```python
# ❌ Missing return type and parameter type
def create_gps_reader(config: dict, event_bus=None):
    """Factory function to create GPS reader from config."""
    ...

# ✅ Should be:
def create_gps_reader(
    config: dict,
    event_bus: Optional[EventBus] = None
) -> Optional[GPSReader]:
```

**Files needing type hints:**
- [src/sensors/gps.py](src/sensors/gps.py) - Multiple functions
- [src/output/mqtt_output.py](src/output/mqtt_output.py) - Message builders
- [src/sensors/base.py](src/sensors/base.py) - Callback functions

---

### 3.3 Global Singleton Pattern
**SEVERITY: MEDIUM** 🟡
**File:** [src/core/event_bus.py:200-210](src/core/event_bus.py#L200-L210)

```python
# ❌ Global mutable state
_global_event_bus = None

def get_event_bus() -> EventBus:
    global _global_event_bus
    if _global_event_bus is None:  # ❌ Not thread-safe!
        _global_event_bus = EventBus()
        _global_event_bus.start()
    return _global_event_bus
```

**Problems:**
- Global mutable state (antipattern)
- Race condition in creation (not thread-safe)
- Makes testing difficult (state pollution)
- No way to reset for tests

**Better approach:**
```python
# Use dependency injection instead
class GunshotDetectionSystem:
    def __init__(self, event_bus: Optional[EventBus] = None):
        self.event_bus = event_bus or EventBus()
```

---

## 🏗️ 4. ARCHITECTURAL PROBLEMS

### 4.1 Event Queue Can Silently Drop Events
**SEVERITY: MEDIUM** 🟡
**File:** [src/core/event_bus.py:75-144](src/core/event_bus.py#L75-L144)

```python
def __init__(self, name: str = "EventBus", max_queue_size: int = 1000):
    self.event_queue = queue.Queue(maxsize=1000)  # ❌ Hardcoded limit

def publish(self, event: Event):
    try:
        self.event_queue.put_nowait(event)  # ❌ Raises queue.Full if full
        self.stats["events_published"] += 1
    except queue.Full:
        self.stats["events_dropped"] += 1
        self.logger.warning("Event queue full, dropping event")  # ❌ Silent loss
```

**Problem Scenario:**
1. Many gunshots detected simultaneously
2. Queue fills to 1000 events
3. New detections **silently dropped**
4. Only a warning log (easy to miss)
5. Critical data lost forever

**Recommendation:**
```python
# Option 1: Block and backpressure
self.event_queue.put(event, timeout=5.0)

# Option 2: Priority queue (keep detections, drop monitoring)
# Option 3: Alert when drop rate exceeds threshold
if self.stats["events_dropped"] > 100:
    # Send alert, increase queue size, etc.
```

---

### 4.2 Threading Model Issues
**SEVERITY: MEDIUM** 🟡
**File:** [src/core/event_bus.py:146-163](src/core/event_bus.py#L146-L163)

```python
self.dispatch_thread = threading.Thread(target=self._dispatch_loop)
self.dispatch_thread.daemon = True  # ❌ Daemon thread - may lose events on exit

def stop(self):
    self.running = False
    if self.dispatch_thread:
        self.dispatch_thread.join(timeout=2.0)  # ❌ Only 2 seconds!
```

**Issues:**
- Daemon thread won't block shutdown (events may be lost)
- 2-second timeout is aggressive
- `_dispatch_loop` sleeps 0.1s between polls (inefficient)
- No signal mechanism for clean exit

**Better approach:**
```python
# Use queue.get() with timeout instead of sleep polling
try:
    event = self.event_queue.get(timeout=1.0)
    # Process event
except queue.Empty:
    continue
```

---

### 4.3 Tight Coupling: GPS → MQTT
**SEVERITY: LOW** 🟡
**File:** [main.py:117-130](main.py#L117-L130)

```python
self.mqtt_output = MQTTOutputNode(
    broker=mqtt_config.get("broker", "localhost"),
    ...
    gps_reader=self.gps_reader,  # ❌ Tight coupling
)
```

**Issues:**
- MQTT requires GPS reader instance
- Cannot test MQTT independently
- GPS failures affect MQTT silently

**Recommendation:**
- Make GPS optional in MQTT
- Use adapter pattern if needed

---

## 📝 5. ERROR HANDLING ISSUES

### 5.1 Exception Swallowing Without Recovery
**SEVERITY: MEDIUM** 🟡
**File:** [src/config/config.py:191-208](src/config/config.py#L191-L208)

```python
def save(self, path: Optional[str] = None):
    """Save configuration to file"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self.data, f, default_flow_style=False)
        logger.info(f"Saved configuration to {path}")
    except Exception as e:
        logger.error(f"Error saving config: {e}")  # ❌ Swallowed - no re-raise
        # Caller has no idea save failed!
```

**Impact:** Configuration changes are silently lost

**Fix:** Re-raise or return status
```python
except Exception as e:
    logger.error(f"Error saving config: {e}")
    raise  # ✅ Let caller handle
```

---

## ⚙️ 6. CONFIGURATION & DEPENDENCIES

### 6.1 Optional Dependencies Confusion
**SEVERITY: MEDIUM** 🟡
**Files:** [requirements.txt](requirements.txt), [setup.py](setup.py)

**Inconsistency:**
```txt
# requirements.txt
gps>=3.19  # Listed here (installed by default)

# setup.py
extras_require={
    "sensors": [
        "gps>=3.19",  # ❌ Also here! Duplicated
```

**Issues:**
- GPS listed as both required and optional
- Unclear which deps are truly required
- `adafruit-circuitpython-bme280` commented out but code tries to import

**Fix:**
- Move optional deps to setup.py extras_require only
- Remove from requirements.txt
- Document clearly

---

### 6.2 Loose Version Constraints
**SEVERITY: LOW** 🟡
**File:** [requirements.txt](requirements.txt)

```txt
numpy>=1.21.0  # ❌ Could pull numpy 3.0.0 with breaking changes
scipy>=1.7.0   # ❌ Similarly loose
```

**Recommendation:**
```txt
numpy>=1.21.0,<2.0.0  # ✅ Safe range
scipy>=1.7.0,<2.0.0
```

---

## 🎯 7. MISSING VALIDATION

### 7.1 MQTT Topic Validation — RESOLVED
**SEVERITY: RESOLVED** ✅
**File:** [src/output/mqtt_output.py](src/output/mqtt_output.py)

MQTT topic validation has been implemented in the `MQTTOutputNode` constructor to ensure the base topic is a non-empty string and does not contain MQTT wildcards (`+` or `#`). Related tests ran in the repository venv and passed.

---

### 7.2 No Validation of Audio Device Strings
**SEVERITY: MEDIUM** 🟡
**File:** [src/audio/audio_nodes.py:182-236](src/audio/audio_nodes.py#L182-L236)

```python
# ❌ self.device used directly from config without validation
if self.device != "default":
    for i in range(self.pa.get_device_count()):
        if self.device in info["name"] or info["name"] in self.device:
```

**Issues:**
- Could be None, empty string, very long string
- No type checking
- Substring matching could be exploited

---

## 📊 SUMMARY STATISTICS

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| Security Issues | 2 | 2 | 0 | 0 | **4** |
| Code Smells | 0 | 0 | 2 | 1 | **3** |
| Best Practices | 0 | 0 | 3 | 0 | **3** |
| Architecture | 0 | 0 | 2 | 1 | **3** |
| Error Handling | 0 | 0 | 1 | 0 | **1** |
| Config/Dependencies | 0 | 0 | 2 | 1 | **3** |
| Validation | 0 | 0 | 1 | 0 | **1** |
| **TOTAL** | **2** | **2** | **11** | **3** | **18** |

---

## ✅ IMMEDIATE ACTION ITEMS

### 🔴 CRITICAL (Fix Before Any Deployment)

1. **Remove hardcoded MQTT password from config.yaml**
   - Add to .gitignore
   - Use environment variables
   - Rotate exposed password
   - Purge from git history

2. **Fix TLS insecure defaults and fallback**
   - Change `tls_insecure: false` in default config
   - Remove silent downgrade on TLS failure
   - Require explicit certificate validation
   - Fail loudly if TLS cannot be configured securely

### 🟠 HIGH (Fix This Week)

3. **Add GPS coordinate validation**
   - Validate lat ∈ [-90, 90], lon ∈ [-180, 180]
   - Type checking for numeric values
   - Remove 0,0 as default

4. **Fix exception handling**
   - Replace `except Exception` with specific exceptions
   - Stop swallowing exceptions in config.save()
   - Re-raise after logging where appropriate

### 🟡 MEDIUM (Fix This Month)

6. **Add input validation**
    - MQTT topic names — DONE (validated in `src/output/mqtt_output.py`)
    - Audio device strings
    - Configuration values

7. **Fix event queue overflow handling**
   - Make queue size configurable
   - Implement backpressure or priority
   - Alert on high drop rates

8. **Add type hints**
   - GPS factory function
   - MQTT message builders
   - Callback functions

---

## 🎓 RECOMMENDATIONS FOR IMPROVEMENT

### Security Hardening
- [ ] Implement message signing for MQTT
- [ ] Add node authentication
- [ ] Use secrets management system (HashiCorp Vault, AWS Secrets Manager)
- [ ] Regular security audits
- [ ] Penetration testing

### Code Quality
- [ ] Add pre-commit hooks (black, flake8, mypy)
- [ ] Increase test coverage to >80%
- [ ] Add integration tests for security features
- [ ] Document all security assumptions

### Architecture
- [ ] Implement dependency injection for EventBus
- [ ] Add circuit breaker pattern for MQTT
- [ ] Use proper thread synchronization primitives
- [ ] Add health check endpoints

---

## 📈 PROGRESS TRACKING

**Audit Date:** 2026-02-15
**Next Review:** 2026-03-01

**Blockers for Production:**
- ❌ Security issues not resolved
- ❌ No secrets management
- ❌ TLS validation disabled

**Ready for Production When:**
- ✅ All CRITICAL issues resolved
- ✅ All HIGH issues resolved
- ✅ Test coverage >70%
- ✅ Security review passed
- ✅ Documentation complete

---

**END OF AUDIT REPORT**
