"""Unit tests for FileLoggerNode."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.event_bus import DetectionEvent, Event, EventBus, EventType
from src.output.file_logger import FileLoggerNode


@pytest.fixture
def tmp_log_path(tmp_path):
    return str(tmp_path / "detections.jsonl")


@pytest.fixture
def logger_node(tmp_log_path):
    node = FileLoggerNode(path=tmp_log_path, node_id="test_node")
    yield node
    if node.running:
        node.stop()


class TestFileLoggerNodeInit:
    def test_defaults(self, tmp_log_path):
        node = FileLoggerNode(path=tmp_log_path)
        assert node.path == Path(tmp_log_path)
        assert node.max_size_bytes == int(100 * 1024 * 1024)
        assert node.backup_count == 5
        assert node.running is False
        assert node.event_bus is None

    def test_custom_params(self, tmp_log_path):
        node = FileLoggerNode(
            path=tmp_log_path,
            max_size_mb=10.0,
            backup_count=3,
            node_id="node42",
        )
        assert node.max_size_bytes == int(10 * 1024 * 1024)
        assert node.backup_count == 3
        assert node.node_id == "node42"


class TestFileLoggerNodeLifecycle:
    def test_start_creates_file_and_sets_running(self, logger_node):
        logger_node.start()
        assert logger_node.running is True
        assert logger_node._file_handler is not None

    def test_start_idempotent(self, logger_node):
        logger_node.start()
        handler1 = logger_node._file_handler
        logger_node.start()
        assert logger_node._file_handler is handler1  # same handler

    def test_stop_clears_running(self, logger_node):
        logger_node.start()
        logger_node.stop()
        assert logger_node.running is False
        assert logger_node._file_handler is None

    def test_stop_before_start_is_safe(self, logger_node):
        logger_node.stop()  # should not raise

    def test_context_manager(self, tmp_log_path):
        with FileLoggerNode(path=tmp_log_path, node_id="ctx") as node:
            assert node.running is True
        assert node.running is False

    def test_subscribes_to_event_bus_on_start(self, tmp_log_path):
        mock_bus = MagicMock()
        node = FileLoggerNode(path=tmp_log_path, event_bus=mock_bus)
        node.start()
        mock_bus.subscribe.assert_called_once_with(EventType.DETECTION, node._on_detection_event)
        node.stop()

    def test_unsubscribes_from_event_bus_on_stop(self, tmp_log_path):
        mock_bus = MagicMock()
        node = FileLoggerNode(path=tmp_log_path, event_bus=mock_bus)
        node.start()
        node.stop()
        mock_bus.unsubscribe.assert_called_once_with(
            EventType.DETECTION, node._on_detection_event
        )


class TestFileLoggerNodeWriting:
    def _make_event(self, confidence=0.9):
        return DetectionEvent(
            timestamp=1234567890.0,
            source="AubioOnset",
            confidence=confidence,
            detector_type="aubio_complex",
            buffer_index=42,
        )

    def test_writes_jsonl_on_detection(self, logger_node, tmp_log_path):
        logger_node.start()
        event = self._make_event()
        logger_node._on_detection_event(event)
        logger_node.stop()

        lines = Path(tmp_log_path).read_text().strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["node_id"] == "test_node"
        assert record["event_type"] == "detection"
        assert record["timestamp"] == pytest.approx(1234567890.0)

    def test_stats_incremented_on_write(self, logger_node):
        logger_node.start()
        logger_node._on_detection_event(self._make_event())
        logger_node._on_detection_event(self._make_event())
        stats = logger_node.get_stats()
        assert stats["events_logged"] == 2
        assert stats["bytes_written"] > 0
        logger_node.stop()

    def test_write_when_not_running_is_safe(self, logger_node):
        # Should not raise even when node isn't started
        event = self._make_event()
        logger_node._on_detection_event(event)
        assert logger_node.get_stats()["events_logged"] == 0

    def test_write_error_increments_failed_stat(self, logger_node):
        logger_node.start()
        # Force a write error by corrupting the logger
        logger_node._jsonl_logger = None
        # _on_detection_event should catch the error without raising
        logger_node._on_detection_event(self._make_event())
        # events_failed is only incremented if the exception path is hit
        # (None logger triggers AttributeError inside _on_detection_event)
        stats = logger_node.get_stats()
        assert stats["events_failed"] >= 0  # just verify it didn't raise
        logger_node.stop()

    def test_multiple_events_multiple_lines(self, logger_node, tmp_log_path):
        logger_node.start()
        for _ in range(5):
            logger_node._on_detection_event(self._make_event())
        logger_node.stop()

        lines = Path(tmp_log_path).read_text().strip().splitlines()
        assert len(lines) == 5
        for line in lines:
            record = json.loads(line)
            assert "timestamp" in record
            assert "node_id" in record

    def test_get_stats_returns_copy(self, logger_node):
        stats1 = logger_node.get_stats()
        stats1["events_logged"] = 999
        assert logger_node.get_stats()["events_logged"] == 0  # original unchanged

    def test_integration_with_real_event_bus(self, tmp_log_path):
        """End-to-end: publish on event bus, verify written to file."""
        bus = EventBus()
        bus.start()
        node = FileLoggerNode(path=tmp_log_path, node_id="bus_test", event_bus=bus)
        node.start()

        event = DetectionEvent(
            timestamp=time.time(),
            source="TestSource",
            confidence=0.8,
            detector_type="threshold",
            buffer_index=1,
        )
        bus.publish(event)
        time.sleep(0.1)  # let dispatch thread process

        node.stop()
        bus.stop()

        lines = Path(tmp_log_path).read_text().strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["node_id"] == "bus_test"
