# Platform Abstraction for Audio Nodes - Implementation Plan

## Context

The gunshot detection system currently has Linux-specific code that prevents it from running on Windows and macOS. This plan implements platform abstraction to enable cross-platform support.

**Current Problem:**
- Code unconditionally tries to load `libasound.so.2` (Linux-only library) on all platforms
- `/proc/asound/cards` filesystem parsing (Linux-only) runs without platform checks
- I2S raw source assumes Linux `/dev/i2s` device availability
- Config defaults use Linux-specific paths (`/dev/pps0`, `/dev/serial0`)

**Good News:**
- PyAudio (the core audio library) is ALREADY cross-platform - it handles ALSA (Linux), WASAPI (Windows), and CoreAudio (macOS) internally
- The Linux-specific code is OPTIONAL enhancements (error suppression, device name mapping)
- Both enhancements are already wrapped in try-except and fail gracefully
- The main fix is adding platform detection before running Linux-specific code

**Approach:**
- Add platform detection utilities module (follows existing patterns)
- Wrap Linux-specific code in platform checks
- Create audio source factory function (mirrors GPS factory pattern at `gps.py:483`)
- Add platform-specific config defaults
- Mark I2S source as Linux-only with clear errors
- BONUS: Fix discovered bug in SerialGPSReader (missing `__init__`)

---

## Critical Files to Modify

### New Files
1. **`src/audio/platform_utils.py`** - Platform detection utilities
2. **`tests/unit/test_audio_platform.py`** - Platform-specific tests

### Modified Files
3. **`src/audio/audio_nodes.py`** (lines 149-165, 191-233, 121) - Add platform guards
4. **`src/audio/__init__.py`** - Add factory function
5. **`src/audio/i2s_raw_source.py`** (lines 26-37) - Platform check in start()
6. **`src/config/config.py`** (lines 27-64) - Platform-specific defaults
7. **`main.py`** (lines 19, 136-165) - Use factory function
8. **`src/sensors/gps.py`** (line 369+) - Fix SerialGPSReader.__init__ bug

---

## Implementation Steps

### Step 1: Create Platform Detection Utilities

**File: `src/audio/platform_utils.py` (NEW)**

Create platform detection module with these functions:
- `is_linux()`, `is_windows()`, `is_macos()` - Platform checks
- `supports_alsa_enhancements()` - Returns True on Linux only
- `supports_proc_asound()` - Checks if /proc/asound/cards exists
- `supports_i2s_raw()` - Returns True on Linux only
- `get_default_audio_device()` - Returns platform-appropriate default

**Key Code:**
```python
import sys
import logging

def is_linux():
    return sys.platform.startswith("linux")

def supports_alsa_enhancements():
    """Check if ALSA-specific enhancements are available."""
    return is_linux()

def supports_proc_asound():
    """Check if /proc/asound/cards is available."""
    if not is_linux():
        return False
    try:
        with open("/proc/asound/cards", "r") as f:
            return True
    except Exception:
        return False
```

**Reference Pattern:** GPS optional imports at `gps.py:17-23`

---

### Step 2: Add Platform Guards to ALSASourceNode

**File: `src/audio/audio_nodes.py`**

**Change 1: ALSA error suppression (lines 149-165)**

Add import at top:
```python
from .platform_utils import supports_alsa_enhancements
```

Wrap existing code:
```python
# Suppress ALSA warnings about missing PCM devices (Linux only)
if supports_alsa_enhancements():
    try:
        # ... existing ctypes/cdll code ...
    except Exception as e:
        self.logger.debug(
            "Failed to set ALSA error handler (platform-specific enhancement): %s",
            e, exc_info=True
        )
else:
    self.logger.debug(
        "ALSA error suppression not available on %s platform",
        sys.platform
    )
```

**Change 2: /proc/asound/cards parsing (lines 191-233)**

Add import:
```python
from .platform_utils import supports_proc_asound
```

Wrap existing code:
```python
if device_index is None and (
    self.device.startswith("hw:") or self.device.startswith("plughw:")
):
    if supports_proc_asound():
        try:
            # ... existing /proc parsing code ...
        except Exception as e:
            self.logger.debug(
                "Failed parsing /proc/asound/cards (platform-specific): %s",
                e, exc_info=True
            )
    else:
        self.logger.debug(
            "hw:X,Y device resolution not available on %s (using PyAudio defaults)",
            sys.platform
        )
```

**Change 3: Update class docstring (line 121)**
```python
class ALSASourceNode(AudioSourceNode):
    """Capture audio from audio device (cross-platform via PyAudio).

    Cross-Platform Support:
    - Linux: ALSA via PyAudio (with optional Linux-specific enhancements)
    - Windows: WASAPI via PyAudio
    - macOS: CoreAudio via PyAudio

    The Linux-specific enhancements are optional and the node will work
    on all platforms using PyAudio's default behavior if unavailable.
    """
```

**Rationale:** Maintains backward compatibility while enabling Windows/macOS

---

### Step 3: Handle I2S Raw Source (Linux-Only)

**File: `src/audio/i2s_raw_source.py`**

**Change: Add platform check in start() method (line 26)**

Add imports:
```python
import sys
from .platform_utils import supports_i2s_raw
```

Update start() method:
```python
def start(self):
    logger = logging.getLogger(self.__class__.__name__)

    if not supports_i2s_raw():
        error_msg = (
            f"I2S raw device access is not supported on {sys.platform}. "
            f"I2S raw source is only available on Linux. "
            f"Please use 'alsa' source type instead (works on all platforms)."
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    try:
        self.file = open(self.device, "rb")
        # ... rest of existing code ...
```

Update class docstring:
```python
class I2SRawSourceNode(AudioSourceNode):
    """Capture audio directly from I2S interface (Linux only).

    PLATFORM RESTRICTION: Linux only

    For cross-platform audio capture, use ALSASourceNode instead.
    """
```

**Rationale:** Clear error message prevents confusion on Windows/macOS

---

### Step 4: Create Audio Source Factory Function

**File: `src/audio/__init__.py`**

Replace entire file with factory function (follows `gps.py:483` pattern):

```python
"""Audio nodes for gunshot detection system."""

import logging
from typing import Optional

from .audio_nodes import (
    AudioBuffer,
    AudioNode,
    AudioSourceNode,
    ALSASourceNode,
    FileSourceNode,
)
from .platform_utils import is_linux, get_default_audio_device

logger = logging.getLogger(__name__)

def create_audio_source(config: dict) -> Optional[AudioSourceNode]:
    """Factory function to create audio source from config.

    Handles platform-specific source creation and graceful fallback.

    Supported source types:
        - 'alsa': Cross-platform PyAudio (Linux/Windows/macOS)
        - 'file': File-based replay (cross-platform)
        - 'i2s_raw': Direct I2S access (Linux only)
    """
    audio_config = config.get("audio", {})
    source_type = audio_config.get("source") or audio_config.get("source_type", "alsa")

    if source_type == "alsa":
        device = audio_config.get("device", get_default_audio_device())
        return ALSASourceNode(
            name="ALSASource",
            device=device,
            sample_rate=audio_config.get("sample_rate", 48000),
            channels=audio_config.get("channels", 1),
            buffer_size=audio_config.get("buffer_size", 1024),
            format_bits=audio_config.get("format_bits", 32),
        )

    elif source_type == "file":
        filepath = audio_config.get("filepath")
        if not filepath:
            logger.error("File source requested but 'filepath' not specified")
            return None
        return FileSourceNode(
            name="FileSource",
            filepath=filepath,
            buffer_size=audio_config.get("buffer_size", 1024),
            realtime=audio_config.get("realtime", True),
            loop=audio_config.get("loop", False),
        )

    elif source_type == "i2s_raw":
        if not is_linux():
            logger.error(
                f"I2S raw source not supported on {sys.platform}. Use 'alsa' instead."
            )
            return None

        from .i2s_raw_source import I2SRawSourceNode
        device = audio_config.get("device", "/dev/i2s")
        return I2SRawSourceNode(
            name="I2SRaw",
            device=device,
            sample_rate=audio_config.get("sample_rate", 48000),
            channels=audio_config.get("channels", 1),
            buffer_size=audio_config.get("buffer_size", 1024),
            format_bits=audio_config.get("format_bits", 32),
        )

    else:
        logger.error(f"Unsupported audio source type: {source_type}")
        return None

__all__ = [
    "AudioBuffer",
    "AudioNode",
    "AudioSourceNode",
    "ALSASourceNode",
    "FileSourceNode",
    "I2SRawSourceNode",
    "create_audio_source",
]
```

**Reference:** GPS factory at `gps.py:483-540`

---

### Step 5: Add Platform-Specific Config Defaults

**File: `src/config/config.py`**

**Change: Update _default_config() method (lines 27-64)**

Add import at top:
```python
import sys
```

Replace `_default_config()` method:
```python
def _default_config(self) -> Dict[str, Any]:
    """Default configuration with platform-specific defaults."""

    # Platform-specific defaults
    if sys.platform.startswith("linux"):
        default_audio_device = "hw:0,0"
        default_pps_device = "/dev/pps0"
        default_serial_device = "/dev/serial0"
        pps_enabled = True
    elif sys.platform == "win32":
        default_audio_device = "default"
        default_pps_device = None
        default_serial_device = "COM1"
        pps_enabled = False
    elif sys.platform == "darwin":
        default_audio_device = "default"
        default_pps_device = None
        default_serial_device = "/dev/tty.usbserial"
        pps_enabled = False
    else:
        default_audio_device = "default"
        default_pps_device = None
        default_serial_device = None
        pps_enabled = False

    return {
        "system": {
            "node_id": "gunshot_detector_001",
            "log_level": "INFO",
            "log_path": "/var/log/gunshot_detector.log",
        },
        "timing": {
            "use_pps": pps_enabled,
            "pps_device": default_pps_device,
            "use_ntp": True,
            "ntp_server": "localhost",
            "ntp_sync_interval": 300,
        },
        "audio": {
            "source_type": "alsa",
            "device": default_audio_device,
            "sample_rate": 48000,
            "channels": 1,
            "buffer_size": 1024,
            "format": "S32_LE",
        },
        # ... rest unchanged ...
    }
```

**Rationale:** Each platform gets sensible defaults; users can override

---

### Step 6: Update main.py to Use Factory

**File: `main.py`**

**Change 1: Update import (line 19)**
```python
from src.audio import create_audio_source
from src.audio.audio_nodes import FileSourceNode  # For test mode override
```

**Change 2: Replace manual instantiation (lines 136-165)**
```python
# 5. Initialize audio source
audio_config = self.config.get("audio", {})

# Command-line test mode override
if hasattr(self, '_test_mode_filepath'):
    self.audio_source = FileSourceNode(
        name="FileSource",
        filepath=self._test_mode_filepath,
        buffer_size=audio_config.get("buffer_size", 1024),
        realtime=audio_config.get("realtime", True),
        loop=audio_config.get("loop", False),
    )
    logger.info("  ✓ File audio source initialized (test mode)")
else:
    # Use factory function for platform-aware creation
    self.audio_source = create_audio_source(self.config.data)
    if not self.audio_source:
        logger.error("  ! Failed to create audio source")
        return False

    source_type = audio_config.get("source_type", "alsa")
    logger.info(f"  ✓ Audio source initialized ({source_type})")
```

**Rationale:** Simplifies main.py, delegates platform logic to factory

---

### Step 7: Fix SerialGPSReader Bug (BONUS)

**File: `src/sensors/gps.py`**

**Change: Add missing __init__ method after line 369**

```python
class SerialGPSReader(BaseGPSDevice[GPSData]):
    """GPS reader using direct serial/NMEA parsing."""

    def __init__(
        self,
        device: str = "/dev/serial0",
        baudrate: int = 9600,
        update_interval: float = 1.0,
        event_bus=None,
    ):
        """Initialize serial GPS reader."""
        super().__init__(
            update_interval=update_interval,
            event_bus=event_bus,
            event_type=EventType.SYSTEM,
            sensor_name="SerialGPSReader",
        )
        self.device = device
        self.baudrate = baudrate
        self.serial = None

    def _connect(self):
        # ... existing code ...
```

**Reference:** GPSReader.__init__ at `gps.py:91-125`

**Rationale:** Fixes bug preventing SerialGPSReader instantiation

---

### Step 8: Add Platform-Specific Tests

**File: `tests/unit/test_audio_platform.py` (NEW)**

Create tests covering:
- Platform detection functions
- Factory function behavior on each platform
- Graceful degradation (I2S rejection on Windows/macOS)
- Default device selection

Key tests:
```python
import pytest
import sys
from src.audio.platform_utils import is_linux, supports_alsa_enhancements
from src.audio import create_audio_source

def test_platform_detection():
    """Test platform detection works."""
    platform_checks = [is_linux(), is_windows(), is_macos()]
    assert sum(platform_checks) == 1

@pytest.mark.skipif(not is_linux(), reason="Linux-specific")
def test_linux_alsa_support():
    assert supports_alsa_enhancements()

def test_factory_creates_alsa_source():
    config = {"audio": {"source": "alsa", "device": "default"}}
    source = create_audio_source(config)
    assert source is not None

@pytest.mark.skipif(is_linux(), reason="Non-Linux platforms only")
def test_factory_rejects_i2s_on_non_linux():
    config = {"audio": {"source": "i2s_raw"}}
    source = create_audio_source(config)
    assert source is None  # Should fail gracefully
```

**Reference:** Platform skip pattern at `test_config_edge.py:31`

---

## Verification Steps

### Automated Tests
```bash
# Run all tests to ensure nothing broke
python -m pytest tests/ -v

# Run new platform tests specifically
python -m pytest tests/unit/test_audio_platform.py -v

# Check code coverage
python -m pytest tests/ --cov=src/audio --cov-report=term-missing
```

### Manual Testing - Linux
```bash
# Test ALSA device with platform enhancements
python main.py --config config.yaml

# Verify ALSA error suppression works
# Verify /proc/asound/cards parsing works for hw:X,Y devices
# Test I2S raw source (if hardware available)
```

### Manual Testing - Windows (if available)
```bash
# Test with default audio device (should use WASAPI)
python main.py --config config.yaml

# Verify no ALSA errors/warnings
# Verify PyAudio uses WASAPI backend
# Test with file source
```

### Manual Testing - macOS (if available)
```bash
# Test with default audio device (should use CoreAudio)
python main.py --config config.yaml

# Verify no ALSA errors/warnings
# Verify PyAudio uses CoreAudio backend
# Test with file source
```

### Verification Checklist
- [ ] All existing tests pass (107 passing, 5 skipped, 0 failed)
- [ ] New platform tests pass
- [ ] Linux: ALSA enhancements work, hw:X,Y resolution works
- [ ] Windows: No ALSA errors, PyAudio uses WASAPI
- [ ] macOS: No ALSA errors, PyAudio uses CoreAudio
- [ ] I2S source fails gracefully on non-Linux with clear error
- [ ] Factory function creates correct source type
- [ ] Config defaults appropriate for each platform
- [ ] SerialGPSReader instantiates without errors

---

## Backward Compatibility

**✅ Fully Compatible:**
- Existing Linux configs work unchanged
- ALSASourceNode behavior identical on Linux
- All existing tests continue to pass
- Config file format unchanged

**⚠️ User-Visible Changes:**
- I2S on non-Linux now shows clear error (previously cryptic file error)
- Platform-appropriate defaults used (can be overridden in config)

**Migration:** None required for existing deployments

---

## Success Criteria

1. ✅ Code runs on Linux, Windows, and macOS
2. ✅ Platform-specific code guarded with platform checks
3. ✅ Clear errors for unsupported features (I2S on Windows/macOS)
4. ✅ All existing tests pass
5. ✅ New platform tests added and passing
6. ✅ Factory pattern implemented (mirrors GPS pattern)
7. ✅ SerialGPSReader bug fixed
8. ✅ CODE_QUALITY_REVIEW.md can mark platform abstraction as COMPLETED

---

## Implementation Time Estimate

- Step 1 (platform_utils.py): 30 min
- Step 2 (audio_nodes.py guards): 30 min
- Step 3 (i2s_raw_source.py): 15 min
- Step 4 (factory function): 45 min
- Step 5 (config defaults): 20 min
- Step 6 (main.py update): 15 min
- Step 7 (SerialGPSReader fix): 15 min
- Step 8 (tests): 45 min
- Verification: 30 min

**Total: ~4 hours** (matches CODE_QUALITY_REVIEW estimate of 3-4 hours)
