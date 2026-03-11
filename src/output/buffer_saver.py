"""Buffer saver — saves audio windows around detection events as WAV + JSON.

Sits in the audio processing pipeline to receive AudioBuffer objects and
maintains a rolling pre-detection window. When a DETECTION event fires,
saves pre_seconds + post_seconds of audio as a WAV file with a JSON sidecar.
These files are critical for debugging false positives and building ML datasets.
"""

import collections
import json
import math
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.audio.audio_nodes import AudioBuffer, AudioNode
from src.core.event_bus import Event, EventType


class BufferSaverNode(AudioNode):
    """Capture audio windows around detections and save as WAV + JSON sidecar.

    Connect this node in the audio pipeline to receive buffers, and subscribe
    it to the event bus for DETECTION events. On each detection, snapshots
    the pre-roll window from the rolling buffer and waits post_seconds for
    the post-roll before writing both to disk.

    Filename format: {timestamp_unix}_{node_id}_{buffer_index}.wav
    Sidecar format: same name but .json
    """

    def __init__(
        self,
        path: str = "/var/log/gds_captures",
        pre_seconds: float = 1.0,
        post_seconds: float = 2.0,
        node_id: str = "unknown",
        sample_rate: int = 48000,
        channels: int = 1,
        buffer_size: int = 1024,
        event_bus=None,
    ):
        """
        Initialize BufferSaverNode.

        Args:
            path: Directory to save WAV and JSON sidecar files.
            pre_seconds: Seconds of audio to include before the detection.
            post_seconds: Seconds of audio to include after the detection.
            node_id: Node identifier written into JSON sidecar.
            sample_rate: Expected audio sample rate (for buffer sizing).
            channels: Expected number of audio channels.
            buffer_size: Expected samples per buffer (for deque sizing).
            event_bus: Local event bus to subscribe to DETECTION events.
        """
        super().__init__("BufferSaver")
        self.save_path = Path(path)
        self.pre_seconds = pre_seconds
        self.post_seconds = post_seconds
        self.node_id = node_id
        self.sample_rate = sample_rate
        self.channels = channels
        self.buffer_size = buffer_size
        self.event_bus = event_bus
        self.running = False

        # Rolling buffer holds (pre_seconds + post_seconds + 1s margin) of audio
        window_seconds = pre_seconds + post_seconds + 1.0
        max_buffers = math.ceil(window_seconds * sample_rate / max(buffer_size, 1))
        self._ring: collections.deque = collections.deque(maxlen=max_buffers)
        self._ring_lock = threading.Lock()

        # Pending saves: list of (detection_event, detection_time, save_after_time)
        self._pending: List[Dict] = []
        self._pending_lock = threading.Lock()

        self._save_thread: Optional[threading.Thread] = None
        self.stats: Dict[str, Any] = {
            "detections_seen": 0,
            "files_saved": 0,
            "save_errors": 0,
        }
        self._stats_lock = threading.Lock()

        import logging

        self.logger = logging.getLogger(self.__class__.__name__)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start accepting buffers and listening for detection events."""
        if self.running:
            return

        self.save_path.mkdir(parents=True, exist_ok=True)
        self.running = True

        self._save_thread = threading.Thread(target=self._save_loop, daemon=True)
        self._save_thread.start()

        if self.event_bus:
            self.event_bus.subscribe(EventType.DETECTION, self._on_detection_event)

        self.logger.info(f"BufferSaverNode started — saving captures to {self.save_path}")

    def stop(self) -> None:
        """Stop saving and unsubscribe from events."""
        if not self.running:
            return

        self.running = False

        if self.event_bus:
            self.event_bus.unsubscribe(EventType.DETECTION, self._on_detection_event)

        if self._save_thread:
            self._save_thread.join(timeout=self.post_seconds + 2.0)
            self._save_thread = None

        self.logger.info(
            f"BufferSaverNode stopped — {self.stats['files_saved']} captures saved"
        )

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    # ------------------------------------------------------------------
    # AudioNode interface — receives buffers from the pipeline
    # ------------------------------------------------------------------

    def process(self, buffer: AudioBuffer) -> Optional[AudioBuffer]:
        """Receive a buffer into the rolling window; pass it through unchanged."""
        if self.running:
            with self._ring_lock:
                self._ring.append(buffer)
        return None  # terminal node — does not forward buffers

    # ------------------------------------------------------------------
    # Event bus interface
    # ------------------------------------------------------------------

    def _on_detection_event(self, event: Event) -> None:
        """Record a pending save triggered by a detection event."""
        if not self.running:
            return

        detection_time = getattr(event, "timestamp", time.time())
        save_after = time.monotonic() + self.post_seconds

        with self._pending_lock:
            self._pending.append(
                {
                    "event": event,
                    "detection_time": detection_time,
                    "save_after": save_after,
                    "buffer_index": getattr(event, "buffer_index", 0),
                }
            )

        with self._stats_lock:
            self.stats["detections_seen"] += 1

    # ------------------------------------------------------------------
    # Save loop
    # ------------------------------------------------------------------

    def _save_loop(self) -> None:
        """Background thread: flush pending saves once post_seconds have elapsed."""
        while self.running:
            now = time.monotonic()
            ready = []

            with self._pending_lock:
                still_pending = []
                for p in self._pending:
                    if now >= p["save_after"]:
                        ready.append(p)
                    else:
                        still_pending.append(p)
                self._pending = still_pending

            for p in ready:
                self._do_save(p)

            time.sleep(0.05)

    def _do_save(self, pending: Dict) -> None:
        """Collect the audio window and write WAV + JSON sidecar."""
        try:
            import numpy as np

            detection_time = pending["detection_time"]
            event = pending["event"]

            # Collect buffers in the pre/post window
            window_start = detection_time - self.pre_seconds
            window_end = detection_time + self.post_seconds

            with self._ring_lock:
                window_buffers = [
                    b for b in self._ring if window_start <= b.timestamp <= window_end
                ]

            if not window_buffers:
                self.logger.warning(
                    f"BufferSaverNode: no audio buffers in window for detection at "
                    f"{detection_time:.3f} — ring may be too small"
                )
                return

            samples = np.concatenate([b.samples for b in window_buffers])
            sr = window_buffers[0].sample_rate

            # Filename: {unix_timestamp}_{node_id}_{buffer_index}
            ts_str = f"{detection_time:.6f}".replace(".", "_")
            buf_idx = pending.get("buffer_index", 0)
            stem = f"{ts_str}_{self.node_id}_{buf_idx}"
            wav_path = self.save_path / f"{stem}.wav"
            json_path = self.save_path / f"{stem}.json"

            # Write WAV
            import soundfile as sf

            sf.write(str(wav_path), samples, sr, subtype="FLOAT")

            # Write JSON sidecar
            sidecar = {
                "node_id": self.node_id,
                "detection_time": detection_time,
                "window_start": window_start,
                "window_end": window_end,
                "pre_seconds": self.pre_seconds,
                "post_seconds": self.post_seconds,
                "sample_rate": sr,
                "channels": window_buffers[0].channels,
                "n_samples": len(samples),
                "n_buffers": len(window_buffers),
                "event_type": event.event_type.value,
                "event_data": event.data if isinstance(event.data, dict) else {},
                "wav_file": wav_path.name,
            }
            json_path.write_text(json.dumps(sidecar, indent=2))

            with self._stats_lock:
                self.stats["files_saved"] += 1

            self.logger.info(f"BufferSaverNode saved capture: {wav_path.name}")

        except Exception as e:  # Intentionally broad: save failures must not crash the pipeline
            with self._stats_lock:
                self.stats["save_errors"] += 1
            self.logger.error("BufferSaverNode failed to save capture: %s", e, exc_info=True)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return a snapshot of saver statistics."""
        with self._stats_lock:
            return dict(self.stats)
