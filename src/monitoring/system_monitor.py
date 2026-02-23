"""System monitoring for health metrics.

This module provides system resource monitoring (CPU, memory, disk, temperature)
and publishes health events to the event bus for MQTT distribution.
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.core.event_bus import Event, EventBus, EventType


@dataclass
class SystemMetrics:
    """System health metrics container."""

    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    disk_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    cpu_temperature: Optional[float] = None
    alerts: Dict[str, bool] = None

    def __post_init__(self):
        if self.alerts is None:
            self.alerts = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "cpu_percent": round(self.cpu_percent, 2),
            "memory_percent": round(self.memory_percent, 2),
            "memory_used_mb": round(self.memory_used_mb, 2),
            "memory_total_mb": round(self.memory_total_mb, 2),
            "disk_percent": round(self.disk_percent, 2),
            "disk_used_gb": round(self.disk_used_gb, 2),
            "disk_total_gb": round(self.disk_total_gb, 2),
            "cpu_temperature": round(self.cpu_temperature, 2) if self.cpu_temperature is not None else None,
            "alerts": self.alerts,
        }


class SystemMonitorNode:
    """
    Monitor system health metrics and publish to event bus.

    Collects CPU, memory, disk, and temperature data using psutil,
    then publishes HEALTH events for MQTT distribution.
    """

    def __init__(
        self,
        event_bus: EventBus,
        node_id: str = "gunshot_node",
        update_interval: float = 30.0,
        disk_path: str = "/",
        alert_thresholds: Optional[Dict[str, float]] = None,
        enabled: bool = True,
    ):
        """
        Initialize system monitor.

        Args:
            event_bus: Event bus to publish health events
            node_id: Unique identifier for this node
            update_interval: Seconds between health checks
            disk_path: Path for disk usage monitoring
            alert_thresholds: Dict with keys cpu_percent, memory_percent,
                            disk_percent, cpu_temp (optional)
            enabled: Whether monitoring is enabled
        """
        self.logger = logging.getLogger("SystemMonitor")
        self.event_bus = event_bus
        self.node_id = node_id
        self.update_interval = update_interval
        self.disk_path = disk_path
        self.enabled = enabled

        # Default alert thresholds
        self.alert_thresholds = {
            "cpu_percent": 90.0,
            "memory_percent": 90.0,
            "disk_percent": 95.0,
            "cpu_temp": 80.0,
        }
        if alert_thresholds:
            self.alert_thresholds.update(alert_thresholds)

        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.stats = {
            "samples_collected": 0,
            "errors": 0,
            "alerts_triggered": 0,
        }

        # Try to import psutil
        self._psutil_available = False
        self._psutil = None
        try:
            import psutil

            self._psutil = psutil
            self._psutil_available = True
        except ImportError:
            self.logger.warning(
                "psutil not installed. Install with: pip install psutil"
            )

    def start(self):
        """Start monitoring thread."""
        if not self.enabled:
            self.logger.info("System monitoring disabled")
            return

        if not self._psutil_available:
            self.logger.error("Cannot start monitoring: psutil not available")
            return

        if self.running:
            return

        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        self.logger.info(
            f"System monitor started (interval={self.update_interval}s, "
            f"node_id={self.node_id})"
        )

    def stop(self):
        """Stop monitoring thread."""
        self.running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2.0)
        self.logger.info("System monitor stopped")

    def _monitor_loop(self):
        """Main monitoring loop."""
        # Collect initial CPU sample (psutil requires a baseline)
        if self._psutil:
            self._psutil.cpu_percent(interval=None)

        while self.running:
            try:
                metrics = self._collect_metrics()
                self._publish_health_event(metrics)
                self.stats["samples_collected"] += 1

                # Log warnings for alerts
                for alert_type, triggered in metrics.alerts.items():
                    if triggered:
                        self.logger.warning(
                            f"ALERT: {alert_type} threshold exceeded"
                        )
                        self.stats["alerts_triggered"] += 1

            except Exception as e:
                self.logger.error(f"Error collecting metrics: {e}")
                self.stats["errors"] += 1

            # Sleep with interruptible wait
            for _ in range(int(self.update_interval)):
                if not self.running:
                    break
                time.sleep(1)

    def _collect_metrics(self) -> SystemMetrics:
        """Collect current system metrics using psutil."""
        if not self._psutil:
            raise RuntimeError("psutil not available")

        # CPU usage (requires interval for first accurate reading, but we
        # use non-blocking mode with previous baseline)
        cpu_percent = self._psutil.cpu_percent(interval=None)

        # Memory usage
        memory = self._psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used_mb = memory.used / (1024 * 1024)
        memory_total_mb = memory.total / (1024 * 1024)

        # Disk usage
        disk = self._psutil.disk_usage(self.disk_path)
        disk_percent = (disk.used / disk.total) * 100
        disk_used_gb = disk.used / (1024 * 1024 * 1024)
        disk_total_gb = disk.total / (1024 * 1024 * 1024)

        # CPU temperature (Raspberry Pi specific paths, with fallbacks)
        cpu_temperature = self._get_cpu_temperature()

        # Build metrics object
        metrics = SystemMetrics(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_used_mb=memory_used_mb,
            memory_total_mb=memory_total_mb,
            disk_percent=disk_percent,
            disk_used_gb=disk_used_gb,
            disk_total_gb=disk_total_gb,
            cpu_temperature=cpu_temperature,
        )

        # Check alert thresholds
        metrics.alerts = self._check_alerts(metrics)

        return metrics

    def _get_cpu_temperature(self) -> Optional[float]:
        """
        Get CPU temperature in Celsius.

        Tries multiple methods:
        1. psutil sensors_temperatures (cross-platform)
        2. Raspberry Pi specific thermal zone
        3. Return None if unavailable
        """
        if not self._psutil:
            return None

        # Method 1: psutil sensors_temperatures
        try:
            temps = self._psutil.sensors_temperatures()
            if temps:
                # Look for common temperature sensor labels
                for name, entries in temps.items():
                    for entry in entries:
                        if "cpu" in entry.label.lower() or name.lower() in ("coretemp", "cpu_thermal"):
                            return entry.current
        except (AttributeError, IOError):
            pass

        # Method 2: Raspberry Pi thermal zone
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                temp_millidegrees = int(f.read().strip())
                return temp_millidegrees / 1000.0
        except (FileNotFoundError, IOError, ValueError):
            pass

        return None

    def _check_alerts(self, metrics: SystemMetrics) -> Dict[str, bool]:
        """Check metrics against alert thresholds."""
        alerts = {}

        if metrics.cpu_percent > self.alert_thresholds["cpu_percent"]:
            alerts["cpu_high"] = True

        if metrics.memory_percent > self.alert_thresholds["memory_percent"]:
            alerts["memory_high"] = True

        if metrics.disk_percent > self.alert_thresholds["disk_percent"]:
            alerts["disk_high"] = True

        if metrics.cpu_temperature and metrics.cpu_temperature > self.alert_thresholds["cpu_temp"]:
            alerts["cpu_temp_high"] = True

        return alerts

    def _publish_health_event(self, metrics: SystemMetrics):
        """Publish health event to event bus."""
        event = Event(
            event_type=EventType.HEALTH,
            timestamp=time.time(),
            source=self.node_id,
            data=metrics.to_dict(),
        )

        self.event_bus.publish(event)
        self.logger.debug(
            f"Published health event: CPU={metrics.cpu_percent:.1f}%, "
            f"Memory={metrics.memory_percent:.1f}%, "
            f"Disk={metrics.disk_percent:.1f}%"
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get monitoring statistics."""
        return {
            "enabled": self.enabled,
            "running": self.running,
            "psutil_available": self._psutil_available,
            **self.stats,
        }

    def get_current_metrics(self) -> Optional[SystemMetrics]:
        """Get current metrics (synchronous call)."""
        if not self._psutil_available:
            return None

        try:
            return self._collect_metrics()
        except Exception as e:
            self.logger.error(f"Error collecting current metrics: {e}")
            return None
