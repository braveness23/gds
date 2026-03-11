"""Unit tests for NTPClock."""

import time
from unittest.mock import MagicMock, patch

import pytest

from src.core.event_bus import EventType
from src.timing.ntp_clock import NTPClock


def _make_ntp_response(offset_s: float = 0.001, stratum: int = 2, ref_id: int = 0):
    """Build a mock ntplib NTPStats response."""
    r = MagicMock()
    r.offset = offset_s
    r.stratum = stratum
    r.tx_time = time.time()
    r.ref_id = ref_id
    return r


@pytest.fixture
def clock():
    node = NTPClock(
        ntp_server="test.ntp.org",
        sync_interval=300.0,
        max_offset_ms=10.0,
        node_id="test_node",
    )
    yield node
    if node.running:
        node.stop()


class TestNTPClockInit:
    def test_defaults(self):
        node = NTPClock()
        assert node.ntp_server == "pool.ntp.org"
        assert node.sync_interval == 300.0
        assert node.max_offset_ms == 10.0
        assert node.running is False

    def test_custom_params(self):
        node = NTPClock(ntp_server="time.google.com", max_offset_ms=5.0)
        assert node.ntp_server == "time.google.com"
        assert node.max_offset_ms == 5.0


class TestNTPClockLifecycle:
    def test_start_sets_running(self, clock):
        with patch("ntplib.NTPClient.request", return_value=_make_ntp_response()):
            clock.start()
        assert clock.running is True
        clock.stop()

    def test_start_idempotent(self, clock):
        with patch("ntplib.NTPClient.request", return_value=_make_ntp_response()):
            clock.start()
            thread1 = clock._thread
            clock.start()
            assert clock._thread is thread1
        clock.stop()

    def test_stop_clears_running(self, clock):
        with patch("ntplib.NTPClient.request", return_value=_make_ntp_response()):
            clock.start()
        clock.stop()
        assert clock.running is False

    def test_stop_before_start_safe(self, clock):
        clock.stop()  # should not raise

    def test_context_manager(self):
        with patch("ntplib.NTPClient.request", return_value=_make_ntp_response()):
            with NTPClock(sync_interval=300.0) as node:
                assert node.running is True
        assert node.running is False


class TestNTPClockQuery:
    def test_successful_query_returns_offset(self, clock):
        mock_response = _make_ntp_response(offset_s=0.005, stratum=2)
        with patch("ntplib.NTPClient.request", return_value=mock_response):
            result = clock.query()

        assert result is not None
        assert abs(result["offset_ms"] - 5.0) < 0.001
        assert result["stratum"] == 2

    def test_query_updates_stats(self, clock):
        mock_response = _make_ntp_response(offset_s=0.002)
        with patch("ntplib.NTPClient.request", return_value=mock_response):
            clock.query()

        stats = clock.get_stats()
        assert stats["queries"] == 1
        assert abs(stats["last_offset_ms"] - 2.0) < 0.001
        assert stats["last_sync"] is not None

    def test_query_failure_returns_none(self, clock):
        with patch("ntplib.NTPClient.request", side_effect=Exception("DNS error")):
            result = clock.query()

        assert result is None
        assert clock.get_stats()["errors"] == 1

    def test_max_offset_tracked(self, clock):
        with patch("ntplib.NTPClient.request", return_value=_make_ntp_response(offset_s=0.050)):
            clock.query()
        with patch("ntplib.NTPClient.request", return_value=_make_ntp_response(offset_s=0.010)):
            clock.query()

        stats = clock.get_stats()
        assert abs(stats["max_offset_seen_ms"] - 50.0) < 0.01


class TestNTPClockEvents:
    def test_no_event_published_when_offset_ok(self):
        mock_bus = MagicMock()
        clock = NTPClock(max_offset_ms=10.0, event_bus=mock_bus)
        with patch("ntplib.NTPClient.request", return_value=_make_ntp_response(offset_s=0.003)):
            clock._check_and_publish()

        mock_bus.publish.assert_not_called()

    def test_warning_event_published_when_offset_exceeds_threshold(self):
        mock_bus = MagicMock()
        clock = NTPClock(max_offset_ms=10.0, event_bus=mock_bus, node_id="n1")
        with patch("ntplib.NTPClient.request", return_value=_make_ntp_response(offset_s=0.050)):
            clock._check_and_publish()

        mock_bus.publish.assert_called_once()
        event = mock_bus.publish.call_args[0][0]
        assert event.event_type == EventType.TIMING
        assert event.data["level"] == "warning"
        assert abs(event.data["offset_ms"] - 50.0) < 0.01
        assert event.data["node_id"] == "n1"

    def test_error_event_published_on_ntp_failure(self):
        mock_bus = MagicMock()
        clock = NTPClock(max_offset_ms=10.0, event_bus=mock_bus)
        with patch("ntplib.NTPClient.request", side_effect=Exception("timeout")):
            clock._check_and_publish()

        mock_bus.publish.assert_called_once()
        event = mock_bus.publish.call_args[0][0]
        assert event.data["level"] == "error"

    def test_timing_warnings_stat_incremented(self):
        mock_bus = MagicMock()
        clock = NTPClock(max_offset_ms=5.0, event_bus=mock_bus)
        with patch("ntplib.NTPClient.request", return_value=_make_ntp_response(offset_s=0.100)):
            clock._check_and_publish()
            clock._check_and_publish()

        assert clock.get_stats()["timing_warnings"] == 2

    def test_no_event_bus_does_not_raise(self, clock):
        """Publishing without an event bus should be a silent no-op."""
        assert clock.event_bus is None
        with patch("ntplib.NTPClient.request", return_value=_make_ntp_response(offset_s=0.100)):
            clock._check_and_publish()  # should not raise


class TestNTPClockStats:
    def test_get_stats_returns_copy(self, clock):
        stats = clock.get_stats()
        stats["queries"] = 999
        assert clock.get_stats()["queries"] == 0

    def test_initial_stats_all_none_or_zero(self, clock):
        stats = clock.get_stats()
        assert stats["queries"] == 0
        assert stats["errors"] == 0
        assert stats["last_offset_ms"] is None
        assert stats["last_sync"] is None
        assert stats["stratum"] is None
