"""File logger output — writes detection events to a local JSONL file.

Serves as a local fallback when MQTT is unavailable. JSONL format (one JSON
object per line) allows streaming reads and easy parsing with standard tools.
"""

import json
import logging
import logging.handlers
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from src.core.event_bus import Event, EventType


class FileLoggerNode:
    """Write detection events to a rotating JSONL file.

    Acts as a local fallback output — keeps a complete record of all detections
    on disk regardless of MQTT connectivity. Each line is a self-contained JSON
    object; the file rotates when it reaches max_size_mb.
    """

    def __init__(
        self,
        path: str = "/var/log/detections.jsonl",
        max_size_mb: float = 100.0,
        backup_count: int = 5,
        node_id: str = "unknown",
        event_bus=None,
    ):
        """
        Initialize FileLoggerNode.

        Args:
            path: Destination JSONL file path.
            max_size_mb: Rotate the file after this many megabytes.
            backup_count: Number of rotated backup files to retain.
            node_id: Node identifier written into each log entry.
            event_bus: Local event bus to subscribe to.
        """
        self.path = Path(path)
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)
        self.backup_count = backup_count
        self.node_id = node_id
        self.event_bus = event_bus
        self.running = False
        self._file_handler: Optional[logging.handlers.RotatingFileHandler] = None
        self._jsonl_logger: Optional[logging.Logger] = None
        self._lock = threading.Lock()
        self.stats: Dict[str, Any] = {
            "events_logged": 0,
            "events_failed": 0,
            "bytes_written": 0,
            "rotations": 0,
        }
        self.logger = logging.getLogger(self.__class__.__name__)

    def start(self) -> None:
        """Open the log file and subscribe to detection events."""
        if self.running:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Dedicated logger writing raw JSON lines (no formatter overhead)
        self._jsonl_logger = logging.getLogger(f"gds.jsonl.{self.node_id}")
        self._jsonl_logger.setLevel(logging.INFO)
        self._jsonl_logger.propagate = False  # Don't bubble up to root logger

        self._file_handler = logging.handlers.RotatingFileHandler(
            self.path,
            maxBytes=self.max_size_bytes,
            backupCount=self.backup_count,
            encoding="utf-8",
        )
        self._file_handler.rotator = self._on_rotate
        self._jsonl_logger.addHandler(self._file_handler)

        self.running = True

        if self.event_bus:
            self.event_bus.subscribe(EventType.DETECTION, self._on_detection_event)

        self.logger.info(f"FileLoggerNode started — writing to {self.path}")

    def stop(self) -> None:
        """Flush, close the log file, and unsubscribe from events."""
        if not self.running:
            return

        self.running = False

        if self.event_bus:
            self.event_bus.unsubscribe(EventType.DETECTION, self._on_detection_event)

        if self._file_handler:
            self._file_handler.flush()
            self._file_handler.close()
            if self._jsonl_logger:
                self._jsonl_logger.removeHandler(self._file_handler)
            self._file_handler = None

        self.logger.info(
            f"FileLoggerNode stopped — {self.stats['events_logged']} events logged"
        )

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def _on_rotate(self, source, dest):
        """Called by RotatingFileHandler on each rotation."""
        import os

        os.rename(source, dest)
        self.stats["rotations"] += 1
        self.logger.info(f"FileLoggerNode rotated log to {dest}")

    def _on_detection_event(self, event: Event) -> None:
        """Write a detection event to the JSONL file."""
        if not self.running or self._jsonl_logger is None:
            return

        try:
            record = {
                "node_id": self.node_id,
                "timestamp": getattr(event, "timestamp", time.time()),
                "event_type": event.event_type.value,
                "source": getattr(event, "source", ""),
                "data": event.data if isinstance(event.data, dict) else {},
            }
            line = json.dumps(record, separators=(",", ":"))

            with self._lock:
                self._jsonl_logger.info(line)
                self.stats["events_logged"] += 1
                self.stats["bytes_written"] += len(line) + 1  # +1 for newline

        except Exception as e:  # Intentionally broad: log errors must never crash the pipeline
            self.stats["events_failed"] += 1
            self.logger.error("FileLoggerNode failed to write event: %s", e, exc_info=True)

    def get_stats(self) -> Dict[str, Any]:
        """Return a snapshot of logging statistics."""
        with self._lock:
            return dict(self.stats)
