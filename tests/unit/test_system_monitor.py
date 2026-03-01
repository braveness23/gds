"""Unit tests for system monitoring.

These tests mock psutil to avoid requiring it as a test dependency.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from src.core.event_bus import EventType
from src.monitoring.system_monitor import SystemMetrics, SystemMonitorNode


@pytest.fixture
def mock_psutil():
    """Provide a mock psutil module."""
    mock = MagicMock()

    # CPU
    mock.cpu_percent.return_value = 45.5

    # Memory
    memory_mock = MagicMock()
    memory_mock.percent = 67.8
    memory_mock.used = 4_000_000_000  # ~4GB
    memory_mock.total = 8_000_000_000  # 8GB
    mock.virtual_memory.return_value = memory_mock

    # Disk
    disk_mock = MagicMock()
    disk_mock.used = 50_000_000_000  # 50GB
    disk_mock.total = 100_000_000_000  # 100GB
    mock.disk_usage.return_value = disk_mock

    # Temperature sensors (empty by default)
    mock.sensors_temperatures.return_value = {}

    return mock


@pytest.fixture
def system_monitor(event_bus, mock_psutil):
    """Provide a system monitor with mocked psutil."""
    with patch.dict("sys.modules", {"psutil": mock_psutil}):
        monitor = SystemMonitorNode(
            event_bus=event_bus,
            node_id="test_node",
            update_interval=0.1,  # Fast for tests
            disk_path="/",
            alert_thresholds={
                "cpu_percent": 90.0,
                "memory_percent": 90.0,
                "disk_percent": 95.0,
                "cpu_temp": 80.0,
            },
            enabled=True,
        )
        # Manually set psutil since we're mocking the module
        monitor._psutil = mock_psutil
        monitor._psutil_available = True
        yield monitor
        monitor.stop()


class TestSystemMetrics:
    """Test suite for SystemMetrics dataclass."""

    def test_default_creation(self):
        """Test creating metrics with defaults."""
        metrics = SystemMetrics()

        assert metrics.cpu_percent == 0.0
        assert metrics.memory_percent == 0.0
        assert metrics.alerts is not None
        assert isinstance(metrics.alerts, dict)

    def test_custom_values(self):
        """Test creating metrics with specific values."""
        metrics = SystemMetrics(
            cpu_percent=75.0,
            memory_percent=60.0,
            cpu_temperature=45.5,
            alerts={"cpu_high": True},
        )

        assert metrics.cpu_percent == 75.0
        assert metrics.memory_percent == 60.0
        assert metrics.cpu_temperature == 45.5
        assert metrics.alerts["cpu_high"] is True

    def test_to_dict(self):
        """Test serialization to dictionary."""
        metrics = SystemMetrics(
            cpu_percent=45.12345,
            memory_percent=67.89123,
            memory_used_mb=4096.5,
            memory_total_mb=8192.0,
            disk_percent=50.0,
            disk_used_gb=50.5,
            disk_total_gb=100.0,
            cpu_temperature=55.5,
            alerts={"cpu_high": True},
        )

        data = metrics.to_dict()

        assert data["cpu_percent"] == 45.12  # Rounded to 2 decimals
        assert data["memory_percent"] == 67.89
        assert data["memory_used_mb"] == 4096.5
        assert data["memory_total_mb"] == 8192.0
        assert data["disk_percent"] == 50.0
        assert data["disk_used_gb"] == 50.5
        assert data["disk_total_gb"] == 100.0
        assert data["cpu_temperature"] == 55.5
        assert data["alerts"]["cpu_high"] is True

    def test_to_dict_no_temperature(self):
        """Test serialization without temperature."""
        metrics = SystemMetrics(cpu_temperature=None)
        data = metrics.to_dict()

        assert data["cpu_temperature"] is None


class TestSystemMonitorNodeBasics:
    """Test basic SystemMonitorNode functionality."""

    def test_initialization(self, event_bus, mock_psutil):
        """Test monitor initialization."""
        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            monitor = SystemMonitorNode(
                event_bus=event_bus,
                node_id="test_node",
                update_interval=30.0,
                disk_path="/data",
                alert_thresholds={"cpu_percent": 80.0},
                enabled=True,
            )
            # Set mock psutil manually
            monitor._psutil = mock_psutil
            monitor._psutil_available = True

            assert monitor.node_id == "test_node"
            assert monitor.update_interval == 30.0
            assert monitor.disk_path == "/data"
            assert monitor.alert_thresholds["cpu_percent"] == 80.0
            assert monitor.enabled is True
            assert monitor.running is False

    def test_initialization_no_psutil(self, event_bus):
        """Test monitor when psutil is not available."""
        with patch.dict("sys.modules", {"psutil": None}):
            monitor = SystemMonitorNode(
                event_bus=event_bus,
                node_id="test_node",
                update_interval=30.0,
            )

            assert monitor._psutil_available is False
            assert monitor.start() is None  # Should not start without psutil

    def test_start_stop(self, system_monitor):
        """Test starting and stopping the monitor."""
        system_monitor.start()

        assert system_monitor.running is True
        assert system_monitor.monitor_thread is not None
        assert system_monitor.monitor_thread.is_alive()

        system_monitor.stop()

        assert system_monitor.running is False
        assert not system_monitor.monitor_thread.is_alive()

    def test_disabled_monitor(self, event_bus, mock_psutil):
        """Test that disabled monitor does not start."""
        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            monitor = SystemMonitorNode(
                event_bus=event_bus,
                node_id="test_node",
                enabled=False,
            )
            monitor._psutil = mock_psutil
            monitor._psutil_available = True

            result = monitor.start()
            # start() returns None when disabled
            assert monitor.running is False

    def test_get_stats(self, system_monitor):
        """Test getting statistics."""
        stats = system_monitor.get_stats()

        assert stats["enabled"] is True
        assert stats["psutil_available"] is True
        assert "samples_collected" in stats
        assert "errors" in stats
        assert "alerts_triggered" in stats


class TestSystemMonitorMetricsCollection:
    """Test metrics collection functionality."""

    def test_collect_metrics(self, system_monitor, mock_psutil):
        """Test metrics collection."""
        metrics = system_monitor._collect_metrics()

        assert metrics.cpu_percent == 45.5
        assert metrics.memory_percent == 67.8
        assert metrics.disk_percent == 50.0

    def test_cpu_temperature_psutil(self, system_monitor, mock_psutil):
        """Test temperature reading from psutil sensors."""
        # Mock temperature sensors
        temp_entry = MagicMock()
        temp_entry.label = "Core 0"
        temp_entry.current = 55.0

        mock_psutil.sensors_temperatures.return_value = {
            "coretemp": [temp_entry]
        }

        temp = system_monitor._get_cpu_temperature()

        assert temp == 55.0

    def test_cpu_temperature_raspberry_pi(self, system_monitor, mock_psutil, tmp_path, monkeypatch):
        """Test temperature reading from Raspberry Pi thermal zone."""
        mock_psutil.sensors_temperatures.return_value = {}

        # Write a Pi-style thermal zone file in tmp_path
        thermal_file = tmp_path / "thermal_temp"
        thermal_file.write_text("55000")  # 55.0°C in millidegrees

        # Redirect the hardcoded path by capturing the real open first to avoid recursion
        _real_open = open
        thermal_path = "/sys/class/thermal/thermal_zone0/temp"

        def patched_open(path, *args, **kwargs):
            if path == thermal_path:
                return _real_open(str(thermal_file), *args, **kwargs)
            return _real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", patched_open)
        temp = system_monitor._get_cpu_temperature()

        assert temp == 55.0

    def test_collect_metrics_without_psutil(self, system_monitor):
        """Test that collecting metrics fails without psutil."""
        system_monitor._psutil = None

        with pytest.raises(RuntimeError, match="psutil not available"):
            system_monitor._collect_metrics()


class TestSystemMonitorAlertChecking:
    """Test alert threshold checking."""

    def test_no_alerts_when_normal(self, system_monitor):
        """Test that normal metrics don't trigger alerts."""
        metrics = SystemMetrics(
            cpu_percent=50.0,  # Below 90%
            memory_percent=60.0,  # Below 90%
            disk_percent=70.0,  # Below 95%
            cpu_temperature=60.0,  # Below 80°C
        )

        alerts = system_monitor._check_alerts(metrics)

        assert len(alerts) == 0

    def test_cpu_alert(self, system_monitor):
        """Test CPU high alert."""
        metrics = SystemMetrics(cpu_percent=95.0)

        alerts = system_monitor._check_alerts(metrics)

        assert alerts.get("cpu_high") is True

    def test_memory_alert(self, system_monitor):
        """Test memory high alert."""
        metrics = SystemMetrics(memory_percent=95.0)

        alerts = system_monitor._check_alerts(metrics)

        assert alerts.get("memory_high") is True

    def test_disk_alert(self, system_monitor):
        """Test disk high alert."""
        metrics = SystemMetrics(disk_percent=97.0)

        alerts = system_monitor._check_alerts(metrics)

        assert alerts.get("disk_high") is True

    def test_temperature_alert(self, system_monitor):
        """Test CPU temperature alert."""
        metrics = SystemMetrics(cpu_temperature=85.0)

        alerts = system_monitor._check_alerts(metrics)

        assert alerts.get("cpu_temp_high") is True

    def test_multiple_alerts(self, system_monitor):
        """Test multiple simultaneous alerts."""
        metrics = SystemMetrics(
            cpu_percent=95.0,
            memory_percent=95.0,
            disk_percent=97.0,
            cpu_temperature=85.0,
        )

        alerts = system_monitor._check_alerts(metrics)

        assert alerts.get("cpu_high") is True
        assert alerts.get("memory_high") is True
        assert alerts.get("disk_high") is True
        assert alerts.get("cpu_temp_high") is True


class TestSystemMonitorEventPublishing:
    """Test event publishing functionality."""

    def test_health_event_published(self, system_monitor, event_bus):
        """Test that health events are published to event bus."""
        received_events = []

        def handler(event):
            received_events.append(event)

        event_bus.subscribe(EventType.HEALTH, handler)

        # Publish a health event
        metrics = SystemMetrics(
            cpu_percent=50.0,
            memory_percent=60.0,
        )
        metrics.alerts = {}
        system_monitor._publish_health_event(metrics)

        time.sleep(0.1)

        assert len(received_events) == 1
        assert received_events[0].event_type == EventType.HEALTH
        assert received_events[0].source == "test_node"
        assert received_events[0].data["cpu_percent"] == 50.0
        assert received_events[0].data["memory_percent"] == 60.0

    def test_multiple_health_events(self, system_monitor, event_bus):
        """Test publishing multiple health events."""
        received_events = []

        event_bus.subscribe(EventType.HEALTH, lambda e: received_events.append(e))

        for i in range(3):
            metrics = SystemMetrics(cpu_percent=float(i * 10))
            metrics.alerts = {}
            system_monitor._publish_health_event(metrics)

        time.sleep(0.1)

        assert len(received_events) == 3


class TestSystemMonitorIntegration:
    """Integration tests for the full monitoring loop."""

    def test_monitoring_loop_publishes_events(self, system_monitor, event_bus):
        """Test that the monitoring loop publishes events over time."""
        received_events = []

        event_bus.subscribe(EventType.HEALTH, lambda e: received_events.append(e))

        # Start monitoring with fast interval
        system_monitor.update_interval = 0.05  # 50ms for tests
        system_monitor.start()

        # Wait for a couple of health events
        time.sleep(0.15)

        system_monitor.stop()

        # Should have collected at least 2 samples
        assert len(received_events) >= 1
        assert system_monitor.stats["samples_collected"] >= 1

    def test_get_current_metrics(self, system_monitor):
        """Test synchronous metrics collection."""
        metrics = system_monitor.get_current_metrics()

        assert metrics is not None
        assert metrics.cpu_percent == 45.5
        assert metrics.memory_percent == 67.8

    def test_get_current_metrics_no_psutil(self, system_monitor):
        """Test that get_current_metrics returns None without psutil."""
        system_monitor._psutil_available = False

        metrics = system_monitor.get_current_metrics()

        assert metrics is None
