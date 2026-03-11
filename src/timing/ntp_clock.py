"""NTP clock monitor — tracks system time offset against NTP server.

This module does NOT discipline the system clock. That is handled by the OS
(ntpd / chrony). What NTPClock does is *observe* the current offset and
publish TIMING events when drift exceeds safe bounds for trilateration.

For GPS PPS setups, the OS clock is already GPS-accurate — this monitor
simply verifies that's still the case and alerts when it's not.

Trilateration accuracy reference:
    1ms offset → 0.34m position error
    10ms offset → 3.4m position error
    100ms offset → 34m position error
"""

import threading
import time
from typing import Any, Dict, Optional

from src.core.event_bus import Event, EventType


class NTPClock:
    """Monitor NTP time offset and publish TIMING events when drift is excessive.

    Periodically queries an NTP server and compares the reported time to the
    local system clock. When the offset exceeds max_offset_ms, publishes a
    TIMING event so the rest of the system can react (e.g. suppress detections
    until sync is restored, flag trilateration results as low-confidence).
    """

    def __init__(
        self,
        ntp_server: str = "pool.ntp.org",
        sync_interval: float = 300.0,
        max_offset_ms: float = 10.0,
        node_id: str = "unknown",
        event_bus=None,
    ):
        """
        Initialize NTPClock.

        Args:
            ntp_server: NTP server hostname to query.
            sync_interval: Seconds between NTP queries (default 300 = 5 minutes).
            max_offset_ms: Offset threshold in milliseconds above which a
                TIMING warning event is published.
            node_id: Node identifier included in TIMING events.
            event_bus: Local event bus for publishing TIMING events.
        """
        self.ntp_server = ntp_server
        self.sync_interval = sync_interval
        self.max_offset_ms = max_offset_ms
        self.node_id = node_id
        self.event_bus = event_bus
        self.running = False

        self._thread: Optional[threading.Thread] = None
        self.stats: Dict[str, Any] = {
            "queries": 0,
            "errors": 0,
            "last_offset_ms": None,
            "last_sync": None,
            "stratum": None,
            "max_offset_seen_ms": None,
            "timing_warnings": 0,
        }
        self._stats_lock = threading.Lock()

        import logging

        self.logger = logging.getLogger(self.__class__.__name__)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the NTP monitoring thread."""
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        self.logger.info(
            f"NTPClock started — querying {self.ntp_server} every {self.sync_interval}s"
        )

    def stop(self) -> None:
        """Stop the NTP monitoring thread."""
        if not self.running:
            return
        self.running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        self.logger.info("NTPClock stopped")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    # ------------------------------------------------------------------
    # NTP query
    # ------------------------------------------------------------------

    def query(self) -> Optional[Dict[str, Any]]:
        """Query NTP server once and return offset info.

        Returns:
            Dict with offset_ms, stratum, tx_time; or None on error.
        """
        try:
            import ntplib

            client = ntplib.NTPClient()
            response = client.request(self.ntp_server, version=3)
            offset_ms = response.offset * 1000.0

            result = {
                "offset_ms": offset_ms,
                "stratum": response.stratum,
                "tx_time": response.tx_time,
                "ref_id": ntplib.ref_id_to_text(response.ref_id, response.stratum),
            }

            with self._stats_lock:
                self.stats["queries"] += 1
                self.stats["last_offset_ms"] = offset_ms
                self.stats["last_sync"] = time.time()
                self.stats["stratum"] = response.stratum
                if (
                    self.stats["max_offset_seen_ms"] is None
                    or abs(offset_ms) > abs(self.stats["max_offset_seen_ms"])
                ):
                    self.stats["max_offset_seen_ms"] = offset_ms

            self.logger.debug(
                f"NTP query: offset={offset_ms:.3f}ms stratum={response.stratum} "
                f"ref={result['ref_id']}"
            )
            return result

        except Exception as e:  # Intentionally broad: network errors, DNS failures, timeouts
            with self._stats_lock:
                self.stats["errors"] += 1
            self.logger.warning("NTP query failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Monitor loop
    # ------------------------------------------------------------------

    def _monitor_loop(self) -> None:
        """Background thread: query NTP at sync_interval, publish TIMING events."""
        # Query immediately on first start, then on interval
        self._check_and_publish()

        while self.running:
            # Sleep in short increments to be responsive to stop()
            deadline = time.monotonic() + self.sync_interval
            while self.running and time.monotonic() < deadline:
                time.sleep(min(1.0, deadline - time.monotonic()))

            if self.running:
                self._check_and_publish()

    def _check_and_publish(self) -> None:
        """Query NTP and publish a TIMING event if offset is out of bounds."""
        result = self.query()
        if result is None:
            self._publish_timing_event(
                level="error",
                message="NTP query failed — cannot verify clock accuracy",
                offset_ms=None,
            )
            return

        offset_ms = result["offset_ms"]
        abs_offset = abs(offset_ms)

        if abs_offset > self.max_offset_ms:
            with self._stats_lock:
                self.stats["timing_warnings"] += 1
            self.logger.warning(
                f"NTP offset {offset_ms:.3f}ms exceeds {self.max_offset_ms}ms threshold "
                f"(~{abs_offset * 0.34:.1f}m trilateration error)"
            )
            self._publish_timing_event(
                level="warning",
                message=(
                    f"Clock offset {offset_ms:.1f}ms > {self.max_offset_ms}ms threshold. "
                    f"Trilateration accuracy degraded (~{abs_offset * 0.34:.1f}m error)."
                ),
                offset_ms=offset_ms,
                stratum=result["stratum"],
            )
        else:
            self.logger.info(
                f"NTP sync OK: offset={offset_ms:.3f}ms stratum={result['stratum']}"
            )

    def _publish_timing_event(
        self,
        level: str,
        message: str,
        offset_ms: Optional[float],
        stratum: Optional[int] = None,
    ) -> None:
        """Publish a TIMING event to the event bus."""
        if self.event_bus is None:
            return
        try:
            event = Event(
                event_type=EventType.TIMING,
                timestamp=time.time(),
                source="NTPClock",
                data={
                    "node_id": self.node_id,
                    "level": level,
                    "message": message,
                    "offset_ms": offset_ms,
                    "stratum": stratum,
                    "ntp_server": self.ntp_server,
                },
            )
            self.event_bus.publish(event)
        except Exception as e:  # Intentionally broad: event bus errors must not crash the clock
            self.logger.error("Failed to publish TIMING event: %s", e)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return a snapshot of NTP monitoring statistics."""
        with self._stats_lock:
            return dict(self.stats)
