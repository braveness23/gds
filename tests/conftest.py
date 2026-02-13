"""Pytest configuration and shared fixtures."""

import pytest
import numpy as np
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from core.event_bus import EventBus, Event, EventType
from config.config import Config
from audio.audio_nodes import AudioBuffer


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
    config.set('output.mqtt.enabled', False)  # Disable for tests
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
    decay = np.exp(-np.arange(512) / 50.0)
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
            buffer_index=0
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
        buffer_index=0
    )


@pytest.fixture
def test_data_dir():
    """Path to test data directory."""
    return Path(__file__).parent / 'test_data'


@pytest.fixture(autouse=True)
def reset_global_state():
    """Reset global state between tests."""
    # Reset mock MQTT if used
    try:
        from tests.mocks.mock_mqtt import MockMQTTClient
        MockMQTTClient.reset()
    except ImportError:
        pass
    
    yield
    
    # Cleanup after test
