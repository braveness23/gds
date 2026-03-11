"""Unit tests for BufferSaverNode."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.audio.audio_nodes import AudioBuffer
from src.core.event_bus import DetectionEvent, Event, EventBus, EventType
from src.output.buffer_saver import BufferSaverNode


def _make_buffer(timestamp: float, sr: int = 48000, n: int = 1024) -> AudioBuffer:
    return AudioBuffer(
        samples=np.zeros(n, dtype=np.float32),
        timestamp=timestamp,
        sample_rate=sr,
        channels=1,
        buffer_index=0,
    )


def _make_detection(ts: float = None) -> DetectionEvent:
    return DetectionEvent(
        timestamp=ts or time.time(),
        source="TestSource",
        confidence=0.9,
        detector_type="aubio_complex",
        buffer_index=1,
    )


@pytest.fixture
def save_dir(tmp_path):
    return str(tmp_path / "captures")


@pytest.fixture
def saver(save_dir):
    node = BufferSaverNode(
        path=save_dir,
        pre_seconds=0.5,
        post_seconds=0.1,
        node_id="test_node",
        sample_rate=48000,
        buffer_size=1024,
    )
    yield node
    if node.running:
        node.stop()


class TestBufferSaverNodeInit:
    def test_defaults(self, save_dir):
        node = BufferSaverNode(path=save_dir)
        assert node.pre_seconds == 1.0
        assert node.post_seconds == 2.0
        assert node.node_id == "unknown"
        assert node.running is False

    def test_ring_buffer_sized_correctly(self, save_dir):
        import math

        node = BufferSaverNode(
            path=save_dir, pre_seconds=1.0, post_seconds=2.0, sample_rate=48000, buffer_size=1024
        )
        # window = 1 + 2 + 1 margin = 4s; 4 * 48000 / 1024 ~ 188 buffers
        expected = math.ceil((1.0 + 2.0 + 1.0) * 48000 / 1024)
        assert node._ring.maxlen == expected


class TestBufferSaverNodeLifecycle:
    def test_start_sets_running(self, saver, save_dir):
        saver.start()
        assert saver.running is True
        assert Path(save_dir).exists()

    def test_start_idempotent(self, saver):
        saver.start()
        thread1 = saver._save_thread
        saver.start()
        assert saver._save_thread is thread1

    def test_stop_clears_running(self, saver):
        saver.start()
        saver.stop()
        assert saver.running is False

    def test_stop_before_start_is_safe(self, saver):
        saver.stop()  # should not raise

    def test_context_manager(self, save_dir):
        with BufferSaverNode(path=save_dir, post_seconds=0.05) as node:
            assert node.running is True
        assert node.running is False

    def test_subscribes_to_event_bus(self, save_dir):
        mock_bus = MagicMock()
        node = BufferSaverNode(path=save_dir, event_bus=mock_bus, post_seconds=0.05)
        node.start()
        mock_bus.subscribe.assert_called_once_with(EventType.DETECTION, node._on_detection_event)
        node.stop()

    def test_unsubscribes_on_stop(self, save_dir):
        mock_bus = MagicMock()
        node = BufferSaverNode(path=save_dir, event_bus=mock_bus, post_seconds=0.05)
        node.start()
        node.stop()
        mock_bus.unsubscribe.assert_called_once_with(
            EventType.DETECTION, node._on_detection_event
        )


class TestBufferSaverNodeBuffering:
    def test_process_returns_none(self, saver):
        """BufferSaverNode is a terminal node — process() returns None."""
        saver.start()
        buf = _make_buffer(time.time())
        result = saver.process(buf)
        assert result is None

    def test_process_accumulates_in_ring(self, saver):
        saver.start()
        now = time.time()
        for i in range(5):
            saver.process(_make_buffer(now + i * 0.02))
        assert len(saver._ring) == 5

    def test_process_when_not_running_does_not_accumulate(self, saver):
        buf = _make_buffer(time.time())
        saver.process(buf)
        assert len(saver._ring) == 0

    def test_detection_event_increments_stat(self, saver):
        saver.start()
        saver._on_detection_event(_make_detection())
        assert saver.get_stats()["detections_seen"] == 1

    def test_detection_when_not_running_ignored(self, saver):
        saver._on_detection_event(_make_detection())
        assert saver.get_stats()["detections_seen"] == 0


class TestBufferSaverNodeSave:
    def _fill_ring(self, saver, detection_time: float, n_buffers: int = 30):
        """Pre-fill the ring with buffers centered around detection_time."""
        sr = saver.sample_rate
        buf_dur = saver.buffer_size / sr
        start_ts = detection_time - saver.pre_seconds - 0.1
        for i in range(n_buffers):
            saver.process(_make_buffer(start_ts + i * buf_dur, sr=sr, n=saver.buffer_size))

    def test_save_creates_wav_and_json(self, save_dir):
        """Saving should create .wav and .json sidecar files."""
        mock_sf = MagicMock()
        with patch.dict("sys.modules", {"soundfile": mock_sf}):
            node = BufferSaverNode(
                path=save_dir,
                pre_seconds=0.2,
                post_seconds=0.05,
                node_id="saver_test",
                sample_rate=48000,
                buffer_size=1024,
            )
            node.start()

            detection_time = time.time()
            self._fill_ring(node, detection_time, n_buffers=20)

            pending = {
                "event": _make_detection(detection_time),
                "detection_time": detection_time,
                "save_after": 0,  # already ready
                "buffer_index": 99,
            }
            node._do_save(pending)
            node.stop()

        assert node.get_stats()["files_saved"] == 1
        # JSON sidecar should be written
        json_files = list(Path(save_dir).glob("*.json"))
        assert len(json_files) == 1
        sidecar = json.loads(json_files[0].read_text())
        assert sidecar["node_id"] == "saver_test"
        assert sidecar["pre_seconds"] == 0.2
        assert sidecar["post_seconds"] == 0.05

    def test_save_error_increments_stat(self, save_dir):
        """A save that raises should increment save_errors without crashing."""
        mock_sf = MagicMock()
        mock_sf.write.side_effect = RuntimeError("disk full")

        node = BufferSaverNode(
            path=save_dir, pre_seconds=0.1, post_seconds=0.05, sample_rate=48000, buffer_size=1024
        )
        node.start()
        detection_time = time.time()
        self._fill_ring(node, detection_time, n_buffers=10)

        with patch.dict("sys.modules", {"soundfile": mock_sf}):
            pending = {
                "event": _make_detection(detection_time),
                "detection_time": detection_time,
                "save_after": 0,
                "buffer_index": 1,
            }
            node._do_save(pending)
        node.stop()

        assert node.get_stats()["save_errors"] == 1

    def test_no_buffers_in_window_logs_warning(self, save_dir, caplog):
        """If no buffers cover the window, log a warning instead of crashing."""
        import logging

        mock_sf = MagicMock()
        with patch.dict("sys.modules", {"soundfile": mock_sf}):
            node = BufferSaverNode(path=save_dir, pre_seconds=0.1, post_seconds=0.05)
            node.start()
            pending = {
                "event": _make_detection(0.0),  # timestamp far in past, no buffers
                "detection_time": 0.0,
                "save_after": 0,
                "buffer_index": 1,
            }
            with caplog.at_level(logging.WARNING, logger="BufferSaverNode"):
                node._do_save(pending)
            node.stop()

        assert "no audio buffers in window" in caplog.text
        assert node.get_stats()["files_saved"] == 0

    def test_get_stats_returns_copy(self, saver):
        stats = saver.get_stats()
        stats["files_saved"] = 999
        assert saver.get_stats()["files_saved"] == 0
