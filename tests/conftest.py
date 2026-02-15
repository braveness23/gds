"""Pytest configuration and shared fixtures."""

import sys
from pathlib import Path

import numpy as np
import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.audio.audio_nodes import AudioBuffer
from src.config.config import Config
from src.core.event_bus import EventBus


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
    config.set("audio.sample_rate", 48000)
    config.set("audio.buffer_size", 1024)
    config.set("detection.aubio.enabled", True)
    config.set("output.mqtt.enabled", False)  # Disable for tests
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
        buffer_index=0,
    )


@pytest.fixture
def impulse_audio():
    """Generate impulse (gunshot-like) audio."""
    samples = np.zeros(1024, dtype=np.float32)
    # Sharp impulse at sample 512
    samples[512] = 1.0
    # Exponential decay
    decay = np.exp(-np.arange(512) / 50.0)
    samples[512:] = decay

    return AudioBuffer(
        samples=samples,
        timestamp=1234567890.123,
        sample_rate=48000,
        channels=1,
        buffer_index=0,
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
        buffer_index=0,
    )


@pytest.fixture
def sine_wave_audio(frequency=1000):
    """Generate sine wave audio buffer."""

    def _make_sine(freq=frequency):
        t = np.arange(1024) / 48000.0
        samples = np.sin(2 * np.pi * freq * t).astype(np.float32)
        return AudioBuffer(
            samples=samples,
            timestamp=1234567890.123,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

    return _make_sine


@pytest.fixture
def stereo_audio():
    """Generate stereo audio buffer."""
    # Left channel: 440 Hz (A4)
    # Right channel: 880 Hz (A5)
    t = np.arange(1024) / 48000.0
    left = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    right = np.sin(2 * np.pi * 880 * t).astype(np.float32)

    samples = np.column_stack([left, right])

    return AudioBuffer(
        samples=samples,
        timestamp=1234567890.123,
        sample_rate=48000,
        channels=2,
        buffer_index=0,
    )


@pytest.fixture
def test_data_dir():
    """Path to test data directory."""
    return Path(__file__).parent / "test_data"


@pytest.fixture(autouse=True)
def reset_global_state():
    """Reset global state between tests."""
    # Reset mock MQTT if used
    try:
        from tests.mocks.mock_mqtt import MockMQTTClient

        MockMQTTClient.reset_all()
    except ImportError:
        pass

    yield

    # Cleanup after test


@pytest.fixture
def mock_mqtt_client():
    """Provide a mock MQTT client instance."""
    from tests.mocks.mock_mqtt import MockMQTTClient

    client = MockMQTTClient()
    yield client
    client.reset()


@pytest.fixture
def mqtt_test_config(test_config):
    """Test configuration with localhost MQTT enabled."""
    config = test_config
    config.set("output.mqtt.enabled", True)
    config.set("output.mqtt.broker", "localhost")
    config.set("output.mqtt.port", 1883)
    config.set("output.mqtt.use_tls", False)
    config.set("output.mqtt.username", None)
    config.set("output.mqtt.password", None)
    return config


@pytest.fixture
def mock_paho_mqtt(monkeypatch):
    """Automatically patch paho.mqtt.client.Client for tests."""
    import sys
    from types import ModuleType

    from tests.mocks.mock_mqtt import MockMQTTClient

    def mock_client_factory(*args, **kwargs):
        return MockMQTTClient(client_id=kwargs.get("client_id", ""))

    # Create full module hierarchy: paho -> paho.mqtt -> paho.mqtt.client
    if "paho" not in sys.modules:
        fake_paho = ModuleType("paho")
        sys.modules["paho"] = fake_paho

    if "paho.mqtt" not in sys.modules:
        fake_mqtt_pkg = ModuleType("paho.mqtt")
        sys.modules["paho.mqtt"] = fake_mqtt_pkg
        sys.modules["paho"].mqtt = fake_mqtt_pkg

    if "paho.mqtt.client" not in sys.modules:
        fake_mqtt_client = ModuleType("paho.mqtt.client")
        fake_mqtt_client.Client = mock_client_factory
        sys.modules["paho.mqtt.client"] = fake_mqtt_client
        sys.modules["paho.mqtt"].client = fake_mqtt_client
    else:
        # Module already exists, just patch the Client class
        monkeypatch.setattr("paho.mqtt.client.Client", mock_client_factory)

    yield MockMQTTClient

    # Cleanup
    MockMQTTClient.reset_all()
