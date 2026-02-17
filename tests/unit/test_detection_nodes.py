"""Comprehensive unit tests for detection nodes.

Tests ThresholdDetectorNode and AubioOnsetNode behaviour including:
- Threshold crossing detection and state machine
- Event bus publishing and debounce
- Stereo-to-mono conversion
- Residual sample accumulation (aubio)
- Graceful degradation when aubio is unavailable
"""

import time
import threading
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.audio.audio_nodes import AudioBuffer
from src.core.event_bus import EventBus, EventType
from src.detection.detection_nodes import AubioOnsetNode, ThresholdDetectorNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_buffer(samples, *, sample_rate=48000, timestamp=1000.0, channels=1, buffer_index=0):
    return AudioBuffer(
        samples=np.asarray(samples, dtype=np.float32),
        timestamp=timestamp,
        sample_rate=sample_rate,
        channels=channels,
        buffer_index=buffer_index,
    )


def wait_for_dispatch(bus: EventBus, timeout: float = 0.5):
    """Poll until the event bus queue is empty, then add a small buffer."""
    deadline = time.monotonic() + timeout
    while not bus.event_queue.empty() and time.monotonic() < deadline:
        time.sleep(0.01)
    time.sleep(0.05)  # Extra time for the dispatch thread to call callbacks


# ---------------------------------------------------------------------------
# ThresholdDetectorNode
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestThresholdDetectorNode:

    # --- Basic detection ---

    def test_silent_audio_no_detection(self, event_bus):
        received = []
        event_bus.subscribe(EventType.DETECTION, received.append)

        node = ThresholdDetectorNode(threshold_db=-20.0, event_bus=event_bus)
        node.process(make_buffer(np.zeros(1024)))

        wait_for_dispatch(event_bus)
        assert received == []

    def test_detects_signal_above_threshold(self, event_bus):
        received = []
        event_bus.subscribe(EventType.DETECTION, received.append)

        # -20 dB ≈ 0.1 linear; use 0.5 to be safely above
        node = ThresholdDetectorNode(threshold_db=-20.0, event_bus=event_bus)
        samples = np.zeros(1024, dtype=np.float32)
        samples[100:200] = 0.5
        node.process(make_buffer(samples))

        wait_for_dispatch(event_bus)
        assert len(received) >= 1

    def test_no_detection_below_threshold(self, event_bus):
        received = []
        event_bus.subscribe(EventType.DETECTION, received.append)

        node = ThresholdDetectorNode(threshold_db=-20.0, event_bus=event_bus)
        samples = np.full(1024, 0.05, dtype=np.float32)  # Below 0.1 linear
        node.process(make_buffer(samples))

        wait_for_dispatch(event_bus)
        assert received == []

    # --- State machine ---

    def test_event_start_sets_in_event(self):
        node = ThresholdDetectorNode(threshold_db=-20.0)
        samples = np.zeros(1024, dtype=np.float32)
        samples[100:] = 0.5  # Stays above threshold through end of buffer
        node.process(make_buffer(samples))
        assert node.in_event is True

    def test_event_ends_when_signal_drops(self):
        node = ThresholdDetectorNode(threshold_db=-20.0)
        samples = np.zeros(1024, dtype=np.float32)
        samples[100:200] = 0.5  # Above threshold then drops
        node.process(make_buffer(samples))
        assert node.in_event is False

    def test_event_start_sample_resets_for_multi_buffer(self):
        """When an event spans buffers, event_start_sample resets to 0."""
        node = ThresholdDetectorNode(threshold_db=-20.0)
        # First buffer: signal throughout → event starts, doesn't end
        node.process(make_buffer(np.full(1024, 0.5)))
        assert node.in_event is True
        assert node.event_start_sample == 0  # Reset at end of first buffer

    # --- Peak tracking ---

    def test_peak_amplitude_tracked(self):
        # Keep all samples above threshold so the event never ends and peak is preserved.
        node = ThresholdDetectorNode(threshold_db=-20.0)  # 0.1 linear threshold
        samples = np.full(1024, 0.3, dtype=np.float32)
        samples[512] = 0.8  # Clear peak mid-buffer
        node.process(make_buffer(samples))

        assert node.in_event is True  # Event still ongoing
        assert node.event_peak >= 0.8

    def test_confidence_capped_at_one(self, event_bus):
        received = []
        event_bus.subscribe(EventType.DETECTION, received.append)

        node = ThresholdDetectorNode(threshold_db=-60.0, event_bus=event_bus)
        # Amplitude of 2.0 exceeds 1.0 limit
        node.process(make_buffer(np.full(1024, 2.0)))

        wait_for_dispatch(event_bus)
        assert len(received) >= 1
        assert received[0].data["confidence"] <= 1.0

    # --- Event data ---

    def test_published_event_has_correct_fields(self, event_bus):
        received = []
        event_bus.subscribe(EventType.DETECTION, received.append)

        node = ThresholdDetectorNode(threshold_db=-20.0, event_bus=event_bus)
        samples = np.zeros(1024, dtype=np.float32)
        samples[100:300] = 0.5
        node.process(make_buffer(samples))

        wait_for_dispatch(event_bus)
        assert len(received) >= 1
        evt = received[0]
        assert evt.event_type == EventType.DETECTION
        assert evt.data["detector_type"] == "threshold"
        assert 0.0 <= evt.data["confidence"] <= 1.0
        assert "buffer_index" in evt.data

    # --- Stereo audio ---

    def test_stereo_audio_mixed_to_mono(self, event_bus):
        received = []
        event_bus.subscribe(EventType.DETECTION, received.append)

        node = ThresholdDetectorNode(threshold_db=-20.0, event_bus=event_bus)

        left = np.zeros(512, dtype=np.float32)
        right = np.zeros(512, dtype=np.float32)
        left[100:200] = 0.5
        right[100:200] = 0.5
        stereo = np.column_stack([left, right])

        buf = AudioBuffer(
            samples=stereo, timestamp=1000.0, sample_rate=48000, channels=2, buffer_index=0
        )
        node.process(buf)

        wait_for_dispatch(event_bus)
        assert len(received) >= 1

    # --- Return value ---

    def test_process_always_returns_buffer(self):
        node = ThresholdDetectorNode()
        buf = make_buffer(np.zeros(1024))
        assert node.process(buf) is buf

    def test_process_returns_buffer_with_signal(self):
        node = ThresholdDetectorNode(threshold_db=-20.0)
        buf = make_buffer(np.full(1024, 0.5))
        assert node.process(buf) is buf

    # --- Threshold clamping ---

    def test_threshold_db_clamped_high(self):
        node = ThresholdDetectorNode(threshold_db=1e9)
        assert node.threshold_db == 100.0

    def test_threshold_db_clamped_low(self):
        node = ThresholdDetectorNode(threshold_db=-1e9)
        assert node.threshold_db == -100.0

    # --- min_duration_samples initialisation ---

    def test_min_duration_samples_zero_before_first_process(self):
        node = ThresholdDetectorNode(min_duration_ms=10.0)
        assert node.min_duration_samples == 0

    def test_min_duration_samples_set_on_first_process(self):
        node = ThresholdDetectorNode(min_duration_ms=10.0)
        node.process(make_buffer(np.zeros(1024), sample_rate=48000))
        assert node.min_duration_samples == int(0.010 * 48000)  # 480

    # --- Debouncing ---

    def test_debouncing_suppresses_second_detection(self, event_bus):
        """Event start publishes once; event end within debounce window is dropped."""
        received = []
        event_bus.subscribe(EventType.DETECTION, received.append)

        # 500 ms debounce; both event-start and event-end happen in the same
        # process() call so the interval is essentially zero.
        node = ThresholdDetectorNode(
            threshold_db=-20.0,
            min_duration_ms=0.0,  # Any duration is valid
            publish_min_interval_ms=500.0,
            event_bus=event_bus,
        )
        samples = np.zeros(1024, dtype=np.float32)
        # Short pulse: event starts and ends within same buffer
        samples[100:200] = 0.5

        node.process(make_buffer(samples))

        wait_for_dispatch(event_bus)
        # Event-start always publishes. Event-end is debounced (same call).
        assert len(received) == 1

    # --- Multi-buffer event ---

    def test_multi_buffer_event_start_and_end(self, event_bus):
        received = []
        event_bus.subscribe(EventType.DETECTION, received.append)

        node = ThresholdDetectorNode(threshold_db=-20.0, event_bus=event_bus)

        # Buffer 1: signal throughout → event starts, no end
        node.process(make_buffer(np.full(1024, 0.5), buffer_index=0))
        assert node.in_event is True

        # Buffer 2: silence → event ends
        node.process(make_buffer(np.zeros(1024), buffer_index=1))
        assert node.in_event is False

        wait_for_dispatch(event_bus)
        # At least the event-start detection was published
        assert len(received) >= 1

    # --- No event bus ---

    def test_no_event_bus_no_crash(self):
        node = ThresholdDetectorNode(threshold_db=-20.0, event_bus=None)
        result = node.process(make_buffer(np.full(1024, 0.5)))
        assert result is not None


# ---------------------------------------------------------------------------
# AubioOnsetNode – mock aubio
# ---------------------------------------------------------------------------


class _MockOnsetDetector:
    """Minimal stand-in for an aubio.onset instance."""

    def __init__(self, method, buf_size, hop_size, samplerate):
        self.method = method
        self.hop_size = hop_size
        self._queue: list = []

    def set_threshold(self, v):
        pass

    def set_silence(self, v):
        pass

    def __call__(self, chunk):
        if self._queue:
            return self._queue.pop(0)
        return 0  # no onset


class _MockAubio:
    """Minimal stand-in for the aubio module."""

    def __init__(self):
        self.created: list = []

    def onset(self, method, buf_size, hop_size, samplerate):
        inst = _MockOnsetDetector(method, buf_size, hop_size, samplerate)
        self.created.append(inst)
        return inst


@pytest.mark.unit
class TestAubioOnsetNode:

    @pytest.fixture
    def mock_aubio(self, monkeypatch):
        mock = _MockAubio()
        monkeypatch.setattr("src.detection.detection_nodes._aubio", mock)
        return mock

    # --- Unavailable aubio ---

    def test_aubio_unavailable_returns_buffer(self, monkeypatch, event_bus):
        monkeypatch.setattr("src.detection.detection_nodes._aubio", None)
        node = AubioOnsetNode(event_bus=event_bus)
        buf = make_buffer(np.ones(1024))
        result = node.process(buf)
        assert result is buf

    def test_aubio_unavailable_no_events_published(self, monkeypatch, event_bus):
        monkeypatch.setattr("src.detection.detection_nodes._aubio", None)
        received = []
        event_bus.subscribe(EventType.DETECTION, received.append)

        node = AubioOnsetNode(event_bus=event_bus)
        node.process(make_buffer(np.ones(1024)))

        wait_for_dispatch(event_bus)
        assert received == []

    def test_aubio_unavailable_records_sample_rate(self, monkeypatch):
        monkeypatch.setattr("src.detection.detection_nodes._aubio", None)
        node = AubioOnsetNode()
        node.process(make_buffer(np.ones(1024), sample_rate=48000))
        assert node.sample_rate == 48000

    # --- Detector initialisation ---

    def test_detector_initialised_on_first_buffer(self, mock_aubio):
        node = AubioOnsetNode(hop_size=512)
        assert node.onset_detector is None

        node.process(make_buffer(np.zeros(1024), sample_rate=48000))

        assert node.onset_detector is not None
        assert len(mock_aubio.created) == 1

    def test_no_reinit_same_sample_rate(self, mock_aubio):
        node = AubioOnsetNode(hop_size=512)
        buf = make_buffer(np.zeros(1024), sample_rate=48000)
        node.process(buf)
        node.process(buf)

        assert len(mock_aubio.created) == 1

    def test_detector_uses_configured_method(self, mock_aubio):
        node = AubioOnsetNode(method="hfc", hop_size=512)
        node.process(make_buffer(np.zeros(1024), sample_rate=48000))
        assert mock_aubio.created[0].method == "hfc"

    # --- Onset detection → event publishing ---

    def test_onset_publishes_detection_event(self, mock_aubio, event_bus):
        received = []
        event_bus.subscribe(EventType.DETECTION, received.append)

        node = AubioOnsetNode(hop_size=512, event_bus=event_bus)
        node.process(make_buffer(np.zeros(1024), sample_rate=48000))

        # Prime: next hop returns onset
        mock_aubio.created[0]._queue = [1]
        node.process(make_buffer(np.zeros(1024), sample_rate=48000, buffer_index=1))

        wait_for_dispatch(event_bus)
        assert len(received) >= 1

    def test_onset_event_has_correct_detector_type(self, mock_aubio, event_bus):
        received = []
        event_bus.subscribe(EventType.DETECTION, received.append)

        node = AubioOnsetNode(method="complex", hop_size=512, event_bus=event_bus)
        node.process(make_buffer(np.zeros(1024), sample_rate=48000))
        mock_aubio.created[0]._queue = [1]
        node.process(make_buffer(np.zeros(1024), sample_rate=48000, buffer_index=1))

        wait_for_dispatch(event_bus)
        assert len(received) >= 1
        assert received[0].data["detector_type"] == "aubio_complex"

    def test_no_onset_no_event(self, mock_aubio, event_bus):
        received = []
        event_bus.subscribe(EventType.DETECTION, received.append)

        node = AubioOnsetNode(hop_size=512, event_bus=event_bus)
        node.process(make_buffer(np.zeros(1024), sample_rate=48000))
        # No priming → mock returns 0 for every hop
        node.process(make_buffer(np.zeros(1024), sample_rate=48000, buffer_index=1))

        wait_for_dispatch(event_bus)
        assert received == []

    def test_onset_returns_none(self, mock_aubio, event_bus):
        """AubioOnsetNode.process() always returns None when aubio is active."""
        node = AubioOnsetNode(hop_size=512, event_bus=event_bus)
        result = node.process(make_buffer(np.zeros(1024), sample_rate=48000))
        assert result is None

    # --- Residual samples ---

    def test_residual_samples_accumulated_across_buffers(self, mock_aubio):
        """Samples that don't fill a complete hop are carried to the next buffer."""
        node = AubioOnsetNode(hop_size=512)
        # 700 samples: one full hop (512) processed, 188 leftover
        node.process(make_buffer(np.zeros(700), sample_rate=48000))
        assert len(node.residual_samples) == 700 - 512

    def test_residual_samples_zero_when_buffer_divisible(self, mock_aubio):
        node = AubioOnsetNode(hop_size=512)
        # 1024 = 2 × 512 → no residual
        node.process(make_buffer(np.zeros(1024), sample_rate=48000))
        assert len(node.residual_samples) == 0

    def test_residual_prepended_next_buffer(self, mock_aubio):
        """Residual from buffer N is prepended to buffer N+1."""
        node = AubioOnsetNode(hop_size=512)
        # First buffer leaves 188 residual
        node.process(make_buffer(np.zeros(700), sample_rate=48000))
        residual_before = len(node.residual_samples)  # 188

        # Second buffer: 700 + 188 = 888 samples → 1 hop (512), 376 residual
        node.process(make_buffer(np.zeros(700), sample_rate=48000, buffer_index=1))
        assert len(node.residual_samples) == residual_before + 700 - 512

    # --- Stereo audio ---

    def test_stereo_buffer_processed_without_error(self, mock_aubio):
        node = AubioOnsetNode(hop_size=512)
        left = np.ones(1024, dtype=np.float32)
        right = np.ones(1024, dtype=np.float32) * 0.5
        stereo = np.column_stack([left, right])
        buf = AudioBuffer(
            samples=stereo, timestamp=1000.0, sample_rate=48000, channels=2, buffer_index=0
        )
        # Should not raise
        node.process(buf)

    # --- Debouncing ---

    def test_debouncing_suppresses_rapid_onsets(self, mock_aubio, event_bus):
        received = []
        event_bus.subscribe(EventType.DETECTION, received.append)

        node = AubioOnsetNode(
            hop_size=512,
            publish_min_interval_ms=500.0,  # 500 ms window
            event_bus=event_bus,
        )
        node.process(make_buffer(np.zeros(1024), sample_rate=48000))

        # Two onsets in rapid succession
        mock_aubio.created[0]._queue = [1, 1]
        node.process(make_buffer(np.zeros(1024), sample_rate=48000, buffer_index=1))

        wait_for_dispatch(event_bus)
        assert len(received) == 1  # Second onset debounced

    # --- No event bus ---

    def test_no_event_bus_no_crash_on_onset(self, mock_aubio):
        node = AubioOnsetNode(hop_size=512, event_bus=None)
        node.process(make_buffer(np.zeros(1024), sample_rate=48000))
        mock_aubio.created[0]._queue = [1]
        # Should not raise even without event_bus
        node.process(make_buffer(np.zeros(1024), sample_rate=48000, buffer_index=1))
