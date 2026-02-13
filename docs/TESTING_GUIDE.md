# Testing Guide - Gunshot Detection System

## Testing Philosophy

This system has unique testing challenges:
- **Real-time audio** - Can't pause or replay easily
- **Hardware dependencies** - GPS, sensors, I2S mics
- **Timing critical** - Microsecond precision matters
- **Distributed** - Fleet coordination
- **Event-driven** - Async communication

Our testing strategy:
1. **Unit tests** - Individual components in isolation (mocked dependencies)
2. **Integration tests** - Components working together (mocked hardware)
3. **Hardware tests** - Real hardware validation (CI/CD skips these)
4. **System tests** - Full pipeline with recorded data
5. **Fleet tests** - Multi-node coordination (manual)

## Testing Stack

```python
# Core testing
pytest>=7.0.0           # Test framework
pytest-cov>=3.0.0       # Coverage reporting
pytest-mock>=3.6.0      # Mocking utilities

# Async testing
pytest-asyncio>=0.18.0  # For async event bus tests

# Test data
numpy>=1.21.0           # Generate test audio
scipy>=1.7.0            # Signal generation

# Performance testing
pytest-benchmark>=3.4.1 # Benchmark critical paths
```

## Directory Structure

```
tests/
├── __init__.py
├── conftest.py                 # Pytest fixtures (shared)
├── test_data/                  # Test audio files, configs
│   ├── test_gunshot.wav
│   ├── test_silence.wav
│   ├── test_noise.wav
│   └── test_config.yaml
├── unit/                       # Unit tests (fast)
│   ├── test_event_bus.py
│   ├── test_config.py
│   ├── test_audio_buffer.py
│   ├── test_filters.py
│   └── test_detectors.py
├── integration/                # Integration tests (slower)
│   ├── test_audio_pipeline.py
│   ├── test_mqtt_integration.py
│   └── test_detection_flow.py
├── hardware/                   # Hardware tests (manual)
│   ├── test_gps_reader.py
│   ├── test_i2s_audio.py
│   └── test_sensors.py
└── mocks/                      # Mock implementations
    ├── mock_audio.py
    ├── mock_gps.py
    ├── mock_sensors.py
    └── mock_mqtt.py
```

## Test Categories

### 1. Unit Tests (Fast, No I/O)

Run on every commit. Should complete in <5 seconds.

**What to test:**
- Pure functions (filters, conversions)
- Data structures (AudioBuffer, Event)
- Configuration parsing
- Business logic (detection algorithms with known data)

**What to mock:**
- All I/O (files, network, hardware)
- Time (for timing tests)
- Random values (for deterministic tests)

### 2. Integration Tests (Medium, Mocked I/O)

Run before merging. Should complete in <30 seconds.

**What to test:**
- Event bus with multiple subscribers
- Audio pipeline (source → processing → detection)
- MQTT publish/subscribe
- Configuration updates

**What to mock:**
- Hardware (GPS, sensors)
- Network (MQTT broker)
- Keep: Event bus, processing logic

### 3. Hardware Tests (Slow, Real Hardware)

Run manually or in CI with hardware attached.

**What to test:**
- GPS provides valid data
- I2S audio captures sound
- Sensors return reasonable values
- PPS timing works

**No mocking** - These validate hardware integration

### 4. System Tests (End-to-End)

Full system with recorded data.

**What to test:**
- Load recording → Process → Verify detections
- Simulate fleet (multiple instances)
- Configuration changes propagate
- Monitoring data collected

---

## Test Fixtures (conftest.py)

```python
# tests/conftest.py
"""Shared pytest fixtures for all tests."""

import pytest
import numpy as np
from pathlib import Path
from src.core.event_bus import EventBus, Event, EventType
from src.config.config import Config
from src.audio.audio_nodes import AudioBuffer


@pytest.fixture
def event_bus():
    """Provide a fresh event bus for each test."""
    bus = EventBus()
    bus.start()
    yield bus
    bus.stop()


@pytest.fixture
def test_config():
    """Provide test configuration."""
    config = Config()
    # Override with test-specific values
    config.set('audio.sample_rate', 48000)
    config.set('audio.buffer_size', 1024)
    config.set('detection.aubio.enabled', True)
    return config


@pytest.fixture
def silent_audio():
    """Generate silent audio buffer."""
    samples = np.zeros(1024, dtype=np.float32)
    return AudioBuffer(
        samples=samples,
        timestamp=1234567890.123,
        sample_rate=48000,
        channels=1,
        buffer_index=0
    )


@pytest.fixture
def impulse_audio():
    """Generate impulse (gunshot-like) audio."""
    samples = np.zeros(1024, dtype=np.float32)
    # Sharp impulse at sample 512
    samples[512] = 1.0
    # Exponential decay
    decay = np.exp(-np.arange(512) / 50)
    samples[512:] = decay
    
    return AudioBuffer(
        samples=samples,
        timestamp=1234567890.123,
        sample_rate=48000,
        channels=1,
        buffer_index=0
    )


@pytest.fixture
def noise_audio():
    """Generate noise audio buffer."""
    samples = np.random.randn(1024).astype(np.float32) * 0.1
    return AudioBuffer(
        samples=samples,
        timestamp=1234567890.123,
        sample_rate=48000,
        channels=1,
        buffer_index=0
    )


@pytest.fixture
def test_data_dir():
    """Path to test data directory."""
    return Path(__file__).parent / 'test_data'


@pytest.fixture
def mock_gps_data():
    """Provide mock GPS data."""
    from tests.mocks.mock_gps import MockGPSData
    return MockGPSData(
        latitude=37.7749,
        longitude=-122.4194,
        altitude=10.0,
        fix_quality=2,
        satellites=8
    )
```

---

## Mock Implementations

### Mock Audio Source

```python
# tests/mocks/mock_audio.py
"""Mock audio source for testing."""

from src.audio.audio_nodes import AudioSourceNode, AudioBuffer
import numpy as np
import threading
import time


class MockAudioSource(AudioSourceNode):
    """Mock audio source that generates test signals."""
    
    def __init__(self, 
                 name: str = "MockAudio",
                 sample_rate: int = 48000,
                 channels: int = 1,
                 buffer_size: int = 1024,
                 signal_type: str = "silence"):
        super().__init__(name, sample_rate, channels, buffer_size)
        self.signal_type = signal_type
        self.generate_thread = None
        self._stop_event = threading.Event()
    
    def start(self):
        """Start generating audio."""
        self.running = True
        self._stop_event.clear()
        self.generate_thread = threading.Thread(target=self._generate_loop)
        self.generate_thread.daemon = True
        self.generate_thread.start()
    
    def stop(self):
        """Stop generating audio."""
        self.running = False
        self._stop_event.set()
        if self.generate_thread:
            self.generate_thread.join(timeout=1.0)
    
    def _generate_loop(self):
        """Generate audio buffers."""
        while not self._stop_event.is_set():
            samples = self._generate_samples()
            buffer = self._create_buffer(samples)
            self.emit(buffer)
            
            # Simulate real-time (sleep for buffer duration)
            sleep_time = self.buffer_size / self.sample_rate
            time.sleep(sleep_time)
    
    def _generate_samples(self) -> np.ndarray:
        """Generate samples based on signal type."""
        if self.signal_type == "silence":
            return np.zeros(self.buffer_size, dtype=np.float32)
        
        elif self.signal_type == "noise":
            return np.random.randn(self.buffer_size).astype(np.float32) * 0.1
        
        elif self.signal_type == "sine":
            # 1kHz sine wave
            t = np.arange(self.buffer_size) / self.sample_rate
            t += self.buffer_index * self.buffer_size / self.sample_rate
            return np.sin(2 * np.pi * 1000 * t).astype(np.float32)
        
        elif self.signal_type == "impulse":
            # Generate impulse every 2 seconds
            samples = np.zeros(self.buffer_size, dtype=np.float32)
            samples_since_start = self.buffer_index * self.buffer_size
            
            # Impulse every 96000 samples (2 sec at 48kHz)
            if samples_since_start % 96000 < self.buffer_size:
                impulse_pos = self.buffer_size // 2
                samples[impulse_pos] = 1.0
                # Add decay
                decay_len = self.buffer_size - impulse_pos
                decay = np.exp(-np.arange(decay_len) / 50)
                samples[impulse_pos:] = decay
            
            return samples
        
        else:
            return np.zeros(self.buffer_size, dtype=np.float32)
    
    def process(self, buffer):
        """Source nodes don't process incoming buffers."""
        return None


# Convenience functions
def create_mock_source(signal_type="silence", **kwargs):
    """Create and configure mock audio source."""
    return MockAudioSource(signal_type=signal_type, **kwargs)
```

### Mock GPS

```python
# tests/mocks/mock_gps.py
"""Mock GPS reader for testing."""

from dataclasses import dataclass
import time


@dataclass
class MockGPSData:
    """Mock GPS position data."""
    latitude: float
    longitude: float
    altitude: float
    timestamp: float = None
    fix_quality: int = 2
    satellites: int = 8
    hdop: float = 1.0
    speed: float = 0.0
    track: float = 0.0
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class MockGPSReader:
    """Mock GPS reader that provides fake position data."""
    
    def __init__(self, 
                 latitude: float = 37.7749,
                 longitude: float = -122.4194,
                 altitude: float = 10.0,
                 **kwargs):
        self.current_position = MockGPSData(
            latitude=latitude,
            longitude=longitude,
            altitude=altitude
        )
        self.callbacks = []
    
    def add_callback(self, callback):
        """Add callback for GPS updates."""
        self.callbacks.append(callback)
    
    def connect(self):
        """Mock connection."""
        pass
    
    def start(self):
        """Mock start."""
        pass
    
    def stop(self):
        """Mock stop."""
        pass
    
    def get_position(self):
        """Return current position."""
        # Update timestamp
        self.current_position.timestamp = time.time()
        return self.current_position
    
    def set_position(self, lat, lon, alt=None):
        """Update position (for testing position changes)."""
        self.current_position.latitude = lat
        self.current_position.longitude = lon
        if alt is not None:
            self.current_position.altitude = alt
        self.current_position.timestamp = time.time()
```

### Mock Sensors

```python
# tests/mocks/mock_sensors.py
"""Mock environmental sensors."""

from dataclasses import dataclass
import time


@dataclass
class MockEnvironmentData:
    """Mock environmental sensor data."""
    temperature: float = 20.0
    humidity: float = 50.0
    pressure: float = 1013.25
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class MockBME280Sensor:
    """Mock BME280 sensor."""
    
    def __init__(self, 
                 temperature: float = 20.0,
                 humidity: float = 50.0,
                 pressure: float = 1013.25,
                 **kwargs):
        self.current_data = MockEnvironmentData(
            temperature=temperature,
            humidity=humidity,
            pressure=pressure
        )
        self.callbacks = []
    
    def add_callback(self, callback):
        """Add callback for sensor updates."""
        self.callbacks.append(callback)
    
    def connect(self):
        """Mock connection."""
        pass
    
    def start(self):
        """Mock start."""
        pass
    
    def stop(self):
        """Mock stop."""
        pass
    
    def get_data(self):
        """Return current sensor data."""
        self.current_data.timestamp = time.time()
        return self.current_data
    
    def set_data(self, temperature=None, humidity=None, pressure=None):
        """Update sensor data (for testing)."""
        if temperature is not None:
            self.current_data.temperature = temperature
        if humidity is not None:
            self.current_data.humidity = humidity
        if pressure is not None:
            self.current_data.pressure = pressure
        self.current_data.timestamp = time.time()
```

### Mock MQTT

```python
# tests/mocks/mock_mqtt.py
"""Mock MQTT client for testing."""

from typing import Dict, List, Callable
from collections import defaultdict


class MockMQTTMessage:
    """Mock MQTT message."""
    
    def __init__(self, topic: str, payload: bytes, qos: int = 0):
        self.topic = topic
        self.payload = payload
        self.qos = qos


class MockMQTTClient:
    """Mock MQTT client that simulates broker locally."""
    
    # Shared message bus across all mock clients
    _global_messages = defaultdict(list)
    _global_subscribers = defaultdict(list)
    
    def __init__(self, client_id=None):
        self.client_id = client_id or "mock_client"
        self.connected = False
        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None
        self.on_publish = None
        self._subscriptions = []
    
    def username_pw_set(self, username, password):
        """Mock username/password setting."""
        self.username = username
        self.password = password
    
    def connect(self, host, port, keepalive=60):
        """Mock connection."""
        self.connected = True
        if self.on_connect:
            self.on_connect(self, None, None, 0)  # rc=0 for success
    
    def disconnect(self):
        """Mock disconnection."""
        self.connected = False
        if self.on_disconnect:
            self.on_disconnect(self, None, 0)
    
    def subscribe(self, topic, qos=0):
        """Mock subscription."""
        self._subscriptions.append(topic)
        MockMQTTClient._global_subscribers[topic].append(self)
    
    def publish(self, topic, payload, qos=0, retain=False):
        """Mock publish - distribute to subscribers."""
        message = MockMQTTMessage(topic, payload if isinstance(payload, bytes) else payload.encode(), qos)
        
        # Store message
        MockMQTTClient._global_messages[topic].append(message)
        
        # Notify subscribers
        for subscriber_topic, clients in MockMQTTClient._global_subscribers.items():
            if self._topic_matches(topic, subscriber_topic):
                for client in clients:
                    if client.on_message:
                        client.on_message(client, None, message)
        
        if self.on_publish:
            self.on_publish(self, None, 0)
        
        return type('obj', (object,), {'rc': 0})()  # Mock successful publish
    
    def loop_start(self):
        """Mock loop start."""
        pass
    
    def loop_stop(self):
        """Mock loop stop."""
        pass
    
    @staticmethod
    def _topic_matches(published_topic: str, subscribed_topic: str) -> bool:
        """Check if published topic matches subscription (support wildcards)."""
        # Simple implementation - could be extended for +/# wildcards
        if subscribed_topic == '#':
            return True
        if subscribed_topic.endswith('/#'):
            prefix = subscribed_topic[:-2]
            return published_topic.startswith(prefix)
        return published_topic == subscribed_topic
    
    @classmethod
    def reset(cls):
        """Clear all messages and subscribers (for test isolation)."""
        cls._global_messages.clear()
        cls._global_subscribers.clear()
    
    @classmethod
    def get_messages(cls, topic: str) -> List[MockMQTTMessage]:
        """Get all messages published to a topic."""
        return cls._global_messages[topic]
```

---

## Example Unit Tests

### Test Event Bus

```python
# tests/unit/test_event_bus.py
"""Unit tests for event bus."""

import pytest
from src.core.event_bus import EventBus, Event, EventType


def test_event_bus_publish_subscribe(event_bus):
    """Test basic publish/subscribe."""
    received_events = []
    
    def handler(event):
        received_events.append(event)
    
    # Subscribe
    event_bus.subscribe(EventType.DETECTION, handler)
    
    # Publish
    event = Event(
        event_type=EventType.DETECTION,
        timestamp=123.456,
        source="test",
        data={'confidence': 0.9}
    )
    event_bus.publish(event)
    
    # Wait briefly for dispatch
    import time
    time.sleep(0.1)
    
    # Verify
    assert len(received_events) == 1
    assert received_events[0].event_type == EventType.DETECTION
    assert received_events[0].data['confidence'] == 0.9


def test_event_bus_multiple_subscribers(event_bus):
    """Test multiple subscribers receive same event."""
    received_1 = []
    received_2 = []
    
    event_bus.subscribe(EventType.SYSTEM, lambda e: received_1.append(e))
    event_bus.subscribe(EventType.SYSTEM, lambda e: received_2.append(e))
    
    event = Event(EventType.SYSTEM, 123.0, "test")
    event_bus.publish(event)
    
    import time
    time.sleep(0.1)
    
    assert len(received_1) == 1
    assert len(received_2) == 1


def test_event_bus_type_filtering(event_bus):
    """Test events only go to correct type subscribers."""
    detection_events = []
    system_events = []
    
    event_bus.subscribe(EventType.DETECTION, lambda e: detection_events.append(e))
    event_bus.subscribe(EventType.SYSTEM, lambda e: system_events.append(e))
    
    event_bus.publish(Event(EventType.DETECTION, 123.0, "test"))
    event_bus.publish(Event(EventType.SYSTEM, 124.0, "test"))
    
    import time
    time.sleep(0.1)
    
    assert len(detection_events) == 1
    assert len(system_events) == 1


def test_event_bus_all_events_subscriber(event_bus):
    """Test subscribing to all event types."""
    all_events = []
    
    event_bus.subscribe(None, lambda e: all_events.append(e))  # None = all types
    
    event_bus.publish(Event(EventType.DETECTION, 123.0, "test"))
    event_bus.publish(Event(EventType.SYSTEM, 124.0, "test"))
    event_bus.publish(Event(EventType.HEALTH, 125.0, "test"))
    
    import time
    time.sleep(0.1)
    
    assert len(all_events) == 3


def test_event_bus_stats(event_bus):
    """Test event bus statistics."""
    event_bus.publish(Event(EventType.DETECTION, 123.0, "test"))
    
    import time
    time.sleep(0.1)
    
    stats = event_bus.get_stats()
    assert stats['events_published'] >= 1
    assert stats['events_dispatched'] >= 1
```

### Test Audio Buffer

```python
# tests/unit/test_audio_buffer.py
"""Unit tests for AudioBuffer."""

import pytest
import numpy as np
from src.audio.audio_nodes import AudioBuffer


def test_audio_buffer_creation():
    """Test creating an audio buffer."""
    samples = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    buffer = AudioBuffer(
        samples=samples,
        timestamp=123.456,
        sample_rate=48000,
        channels=1,
        buffer_index=0
    )
    
    assert buffer.timestamp == 123.456
    assert buffer.sample_rate == 48000
    assert buffer.channels == 1
    assert buffer.is_mono
    assert np.array_equal(buffer.samples, samples)


def test_audio_buffer_duration():
    """Test buffer duration calculation."""
    samples = np.zeros(48000, dtype=np.float32)  # 1 second at 48kHz
    buffer = AudioBuffer(
        samples=samples,
        timestamp=0.0,
        sample_rate=48000,
        channels=1,
        buffer_index=0
    )
    
    assert buffer.duration == pytest.approx(1.0, abs=0.001)


def test_audio_buffer_mono_conversion():
    """Test stereo to mono conversion."""
    # Stereo buffer: [[L1, R1], [L2, R2], ...]
    stereo_samples = np.array([
        [0.5, 0.3],
        [0.6, 0.4],
        [0.7, 0.5]
    ], dtype=np.float32)
    
    buffer = AudioBuffer(
        samples=stereo_samples,
        timestamp=123.0,
        sample_rate=48000,
        channels=2,
        buffer_index=0
    )
    
    assert not buffer.is_mono
    
    mono_buffer = buffer.to_mono()
    
    assert mono_buffer.is_mono
    assert mono_buffer.channels == 1
    # Check averaging: (0.5+0.3)/2 = 0.4
    assert mono_buffer.samples[0] == pytest.approx(0.4, abs=0.01)
```

### Test Filters

```python
# tests/unit/test_filters.py
"""Unit tests for signal processing filters."""

import pytest
import numpy as np
from src.processing.processing_nodes import HighPassFilterNode
from src.audio.audio_nodes import AudioBuffer


def test_highpass_filter_initialization():
    """Test filter initialization."""
    hpf = HighPassFilterNode(
        name="TestHPF",
        cutoff_freq=5000,
        order=4
    )
    
    assert hpf.cutoff_freq == 5000
    assert hpf.order == 4


def test_highpass_filter_removes_dc():
    """Test that HPF removes DC offset."""
    hpf = HighPassFilterNode(cutoff_freq=100, order=4)
    
    # Create signal with DC offset
    samples = np.ones(1024, dtype=np.float32) * 0.5  # Pure DC
    buffer = AudioBuffer(
        samples=samples,
        timestamp=0.0,
        sample_rate=48000,
        channels=1,
        buffer_index=0
    )
    
    # Filter
    filtered = hpf.process(buffer)
    
    # DC should be removed (near zero)
    assert np.abs(np.mean(filtered.samples)) < 0.01


def test_highpass_filter_passes_high_freq():
    """Test that HPF passes high frequencies."""
    hpf = HighPassFilterNode(cutoff_freq=1000, order=4)
    
    # Create 10kHz sine wave (well above cutoff)
    t = np.arange(1024) / 48000
    samples = np.sin(2 * np.pi * 10000 * t).astype(np.float32)
    
    buffer = AudioBuffer(
        samples=samples,
        timestamp=0.0,
        sample_rate=48000,
        channels=1,
        buffer_index=0
    )
    
    filtered = hpf.process(buffer)
    
    # High frequency should pass through (RMS should be similar)
    original_rms = np.sqrt(np.mean(samples**2))
    filtered_rms = np.sqrt(np.mean(filtered.samples**2))
    
    # Should be within 10% (some attenuation expected)
    assert filtered_rms > original_rms * 0.9


def test_highpass_filter_attenuates_low_freq():
    """Test that HPF attenuates low frequencies."""
    hpf = HighPassFilterNode(cutoff_freq=5000, order=4)
    
    # Create 100Hz sine wave (well below cutoff)
    t = np.arange(1024) / 48000
    samples = np.sin(2 * np.pi * 100 * t).astype(np.float32)
    
    buffer = AudioBuffer(
        samples=samples,
        timestamp=0.0,
        sample_rate=48000,
        channels=1,
        buffer_index=0
    )
    
    filtered = hpf.process(buffer)
    
    # Low frequency should be heavily attenuated
    original_rms = np.sqrt(np.mean(samples**2))
    filtered_rms = np.sqrt(np.mean(filtered.samples**2))
    
    assert filtered_rms < original_rms * 0.1  # >90% attenuation
```

---

## Example Integration Tests

### Test Audio Pipeline

```python
# tests/integration/test_audio_pipeline.py
"""Integration tests for audio processing pipeline."""

import pytest
import time
from tests.mocks.mock_audio import MockAudioSource
from src.processing.processing_nodes import HighPassFilterNode, MonoConversionNode


def test_source_to_filter_pipeline(event_bus):
    """Test audio flowing from source through filter."""
    received_buffers = []
    
    # Create pipeline
    source = MockAudioSource(signal_type="impulse", buffer_size=1024)
    hpf = HighPassFilterNode(cutoff_freq=5000)
    
    # Connect
    source.connect(hpf.receive)
    hpf.connect(lambda buf: received_buffers.append(buf))
    
    # Run for brief time
    source.start()
    time.sleep(0.5)  # ~24 buffers at 48kHz/1024
    source.stop()
    
    # Verify buffers flowed through
    assert len(received_buffers) > 10
    assert all(buf.sample_rate == 48000 for buf in received_buffers)


def test_parallel_processing_with_splitter(event_bus):
    """Test buffer splitter sends to multiple outputs."""
    from src.processing.processing_nodes import BufferSplitterNode
    
    output_1 = []
    output_2 = []
    output_3 = []
    
    source = MockAudioSource(signal_type="noise")
    splitter = BufferSplitterNode()
    
    source.connect(splitter.receive)
    splitter.connect(lambda buf: output_1.append(buf))
    splitter.connect(lambda buf: output_2.append(buf))
    splitter.connect(lambda buf: output_3.append(buf))
    
    source.start()
    time.sleep(0.2)
    source.stop()
    
    # All outputs should receive same number of buffers
    assert len(output_1) == len(output_2) == len(output_3)
    assert len(output_1) > 5
    
    # Buffers should be identical (same object)
    for i in range(len(output_1)):
        assert output_1[i] is output_2[i] is output_3[i]
```

### Test Detection Flow

```python
# tests/integration/test_detection_flow.py
"""Integration tests for detection pipeline."""

import pytest
import time
from tests.mocks.mock_audio import MockAudioSource
from src.detection.detection_nodes import AubioOnsetNode


def test_aubio_detects_impulses(event_bus):
    """Test Aubio detector finds impulses."""
    detections = []
    
    def capture_detection(event):
        detections.append(event)
    
    # Subscribe to detection events
    event_bus.subscribe(EventType.DETECTION, capture_detection)
    
    # Create pipeline
    source = MockAudioSource(signal_type="impulse")  # Impulse every 2 sec
    detector = AubioOnsetNode(
        event_bus=event_bus,
        hop_size=512,
        threshold=0.3
    )
    
    source.connect(detector.receive)
    
    # Run for 5 seconds (should get 2-3 impulses)
    source.start()
    time.sleep(5.0)
    source.stop()
    
    # Verify detections occurred
    assert len(detections) >= 2
    assert all(d.event_type == EventType.DETECTION for d in detections)


def test_aubio_ignores_silence(event_bus):
    """Test Aubio doesn't false-trigger on silence."""
    detections = []
    
    event_bus.subscribe(EventType.DETECTION, lambda e: detections.append(e))
    
    source = MockAudioSource(signal_type="silence")
    detector = AubioOnsetNode(event_bus=event_bus)
    
    source.connect(detector.receive)
    
    source.start()
    time.sleep(2.0)
    source.stop()
    
    # Should have no detections on silence
    assert len(detections) == 0
```

### Test MQTT Integration

```python
# tests/integration/test_mqtt_integration.py
"""Integration tests for MQTT output."""

import pytest
import json
import time
from tests.mocks.mock_mqtt import MockMQTTClient
from src.output.mqtt_output import MQTTOutputNode
from src.core.event_bus import Event, EventType


def test_mqtt_publishes_detections(event_bus):
    """Test MQTT node publishes detection events."""
    # Reset mock MQTT
    MockMQTTClient.reset()
    
    # Patch paho.mqtt.client
    import src.output.mqtt_output as mqtt_module
    original_client = mqtt_module.mqtt.Client
    mqtt_module.mqtt.Client = MockMQTTClient
    
    try:
        mqtt_node = MQTTOutputNode(
            broker="localhost",
            port=1883,
            topic="test/detections",
            node_id="test_node",
            event_bus=event_bus
        )
        mqtt_node.connect()
        
        # Publish detection event
        event = Event(
            event_type=EventType.DETECTION,
            timestamp=123.456,
            source="test_detector",
            data={
                'confidence': 0.95,
                'detector_type': 'aubio'
            }
        )
        event_bus.publish(event)
        
        time.sleep(0.2)  # Allow processing
        
        # Verify message published
        messages = MockMQTTClient.get_messages("test/detections")
        assert len(messages) >= 1
        
        # Verify message content
        payload = json.loads(messages[0].payload)
        assert payload['node_id'] == "test_node"
        assert payload['data']['confidence'] == 0.95
        
    finally:
        mqtt_module.mqtt.Client = original_client
```

---

## Running Tests

### Basic Usage

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run only unit tests (fast)
pytest tests/unit/

# Run only integration tests
pytest tests/integration/

# Run specific test file
pytest tests/unit/test_event_bus.py

# Run specific test
pytest tests/unit/test_event_bus.py::test_event_bus_publish_subscribe

# Run with verbose output
pytest -v

# Run and show print statements
pytest -s
```

### Continuous Integration

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.9'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install pytest pytest-cov pytest-mock
    
    - name: Run unit tests
      run: pytest tests/unit/ --cov=src
    
    - name: Run integration tests
      run: pytest tests/integration/
    
    - name: Upload coverage
      uses: codecov/codecov-action@v2
```

### Pre-commit Hook

```bash
# .git/hooks/pre-commit
#!/bin/bash

echo "Running tests..."
pytest tests/unit/ -q

if [ $? -ne 0 ]; then
    echo "Tests failed. Commit aborted."
    exit 1
fi

echo "Tests passed!"
```

---

## Test-Driven Development Workflow

### 1. Write Test First
```python
# tests/unit/test_new_feature.py
def test_gunshot_classifier():
    """Test ML gunshot classifier."""
    classifier = MLGunShotDetector(model_path="test_model.pth")
    
    # Should detect gunshot
    gunshot_audio = load_test_audio("gunshot.wav")
    result = classifier.classify(gunshot_audio)
    assert result['class'] == 'gunshot'
    assert result['confidence'] > 0.8
    
    # Should reject noise
    noise_audio = load_test_audio("noise.wav")
    result = classifier.classify(noise_audio)
    assert result['class'] != 'gunshot'
```

### 2. Run Test (It Fails)
```bash
$ pytest tests/unit/test_new_feature.py
FAILED - MLGunShotDetector not implemented
```

### 3. Implement Feature
```python
# src/detection/ml_detector.py
class MLGunShotDetector:
    def classify(self, audio):
        # Implementation here
        ...
```

### 4. Run Test (It Passes)
```bash
$ pytest tests/unit/test_new_feature.py
PASSED
```

---

## Testing Best Practices

### 1. Test Isolation
Each test should be independent:
```python
@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state between tests."""
    MockMQTTClient.reset()
    # Reset any other global state
    yield
```

### 2. Descriptive Test Names
```python
# Bad
def test_1():
    ...

# Good
def test_highpass_filter_removes_dc_offset():
    ...
```

### 3. Arrange-Act-Assert Pattern
```python
def test_example():
    # Arrange - Set up test data
    buffer = create_test_buffer()
    filter = HighPassFilter(cutoff=5000)
    
    # Act - Perform action
    result = filter.process(buffer)
    
    # Assert - Verify outcome
    assert result.samples.mean() < 0.01
```

### 4. Test Edge Cases
```python
def test_filter_with_empty_buffer():
    """Test filter handles empty buffer gracefully."""
    ...

def test_filter_with_nan_values():
    """Test filter handles NaN values."""
    ...
```

### 5. Use Parameterized Tests
```python
@pytest.mark.parametrize("cutoff,expected_attenuation", [
    (1000, 0.9),
    (5000, 0.5),
    (10000, 0.1),
])
def test_filter_attenuation(cutoff, expected_attenuation):
    """Test filter attenuation at different cutoffs."""
    ...
```

---

## Coverage Goals

- **Unit tests**: >90% coverage
- **Integration tests**: Cover all critical paths
- **Hardware tests**: Manual verification

```bash
# Generate coverage report
pytest --cov=src --cov-report=html

# View report
open htmlcov/index.html
```

---

## Next Steps

1. Implement mock classes
2. Write unit tests for core components
3. Write integration tests for pipelines
4. Set up CI/CD with GitHub Actions
5. Add hardware tests for manual validation
6. Aim for >90% coverage before deployment
