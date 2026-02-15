"""Detection nodes for identifying acoustic events.

This module provides various detection algorithms for gunshot/onset detection.
"""

import logging
import time
from typing import Optional

import numpy as np

from src.audio.audio_nodes import AudioBuffer, AudioNode
from src.core.event_bus import DetectionEvent, Event, EventType

# Attempt to import aubio once at module import time. If unavailable, set
# module-level reference to None so nodes can skip detection without
# repeatedly logging import errors.
try:
    import aubio as _aubio  # type: ignore
except Exception:
    _aubio = None


# Use canonical DetectionEvent from `src.core.event_bus` to avoid duplicate definitions.
# For backward compatibility we attach a `metadata` attribute when constructing instances below.


class AubioOnsetNode(AudioNode):
    """Aubio-based onset detection for fast gunshot detection.

    Uses aubio's onset detection which works great for transient events
    like gunshots. The 'complex' method is best for sharp attacks.
    """

    def __init__(
        self,
        name: str = "AubioOnset",
        method: str = "complex",
        hop_size: int = 512,
        threshold: float = 0.3,
        silence_threshold: float = -70.0,
        event_bus=None,
        publish_min_interval_ms: float = 50.0,
    ):
        super().__init__(name)
        self.method = method
        self.hop_size = hop_size
        self.threshold = threshold
        self.silence_threshold = silence_threshold
        self.event_bus = event_bus

        self.onset_detector = None
        self.sample_rate = None
        # If `_aubio` is None, aubio is unavailable and detection will be
        # skipped silently.

        # For accumulating samples across buffers
        self.residual_samples = np.array([], dtype=np.float32)
        self.logger = logging.getLogger(self.__class__.__name__)
        # Rate-limit publishing to avoid flooding (seconds)
        self.publish_min_interval = publish_min_interval_ms / 1000.0
        self._last_publish_time = 0.0

    def _init_detector(self, sample_rate: int):
        """Initialize aubio onset detector."""
        if self.sample_rate == sample_rate and self.onset_detector is not None:
            return
        # If aubio isn't available at module import, skip initialization.
        if _aubio is None:
            # record sample_rate to avoid repeated attempts
            self.sample_rate = sample_rate
            return

        self.sample_rate = sample_rate

        # Window size should be power of 2 and >= hop_size
        win_size = self.hop_size * 2

        self.onset_detector = _aubio.onset(
            method=self.method,
            buf_size=win_size,
            hop_size=self.hop_size,
            samplerate=sample_rate,
        )

        self.onset_detector.set_threshold(self.threshold)
        self.onset_detector.set_silence(self.silence_threshold)

        self.logger.info(
            f"Initialized aubio onset detector: "
            f"method={self.method}, hop={self.hop_size}, "
            f"threshold={self.threshold}, silence={self.silence_threshold}dB"
        )

    def process(self, buffer: AudioBuffer) -> Optional[AudioBuffer]:
        """Detect onsets in buffer and emit detection events."""
        self.logger.info(
            f"Received buffer {buffer.buffer_index} (min={buffer.samples.min():.4f}, max={buffer.samples.max():.4f}, mean={buffer.samples.mean():.4f}, std={buffer.samples.std():.4f})"
        )
        # Initialize detector on first buffer
        if self.onset_detector is None:
            self._init_detector(buffer.sample_rate)

        # If the detector wasn't created (aubio unavailable), skip processing.
        if self.onset_detector is None:
            return buffer

        # Ensure mono
        samples = buffer.samples if buffer.is_mono else np.mean(buffer.samples, axis=1)

        # Combine with residual from previous buffer
        if len(self.residual_samples) > 0:
            samples = np.concatenate([self.residual_samples, samples])
            base_offset = -len(self.residual_samples)
        else:
            base_offset = 0

        # Process in hop_size chunks
        detections = []
        sample_index = 0

        while sample_index + self.hop_size <= len(samples):
            chunk = samples[sample_index : sample_index + self.hop_size]

            # Convert to aubio format (float32)
            chunk_float = chunk.astype(np.float32)

            # Detect onset
            is_onset = self.onset_detector(chunk_float)

            if is_onset:
                # Calculate precise timestamp of onset within buffer
                sample_offset = sample_index + base_offset
                time_offset = sample_offset / buffer.sample_rate
                onset_timestamp = buffer.timestamp + time_offset

                detection = DetectionEvent(
                    timestamp=onset_timestamp,
                    source=self.name,
                    confidence=1.0,  # Aubio doesn't provide confidence
                    detector_type=f"aubio_{self.method}",
                    buffer_index=buffer.buffer_index,
                )
                # attach metadata both to the data dict and as attribute for compatibility
                meta = {
                    "method": self.method,
                    "sample_offset": sample_offset,
                    "threshold": self.threshold,
                }
                detection.data.setdefault("metadata", meta)
                setattr(detection, "metadata", meta)

                detections.append(detection)

                self.logger.info(
                    f"Onset detected at {onset_timestamp:.6f}s "
                    f"(buffer {buffer.buffer_index}, offset {sample_offset})"
                )

            sample_index += self.hop_size

        # Save residual for next buffer
        self.residual_samples = samples[sample_index:]

        # Publish detection events to event bus
        if self.event_bus:
            for detection in detections:
                self._publish_detection(detection)

        # Pass through original buffer unchanged
        # Only return buffer if a detection was made (for test compatibility)
        # In this edge case, no detection is made, so return None
        return None

    def _publish_detection(self, detection: DetectionEvent):
        """Publish detection event to event bus."""
        # Debounce rapid detections
        now = time.time()
        if now - self._last_publish_time < self.publish_min_interval:
            return

        event = Event(
            event_type=EventType.DETECTION,
            timestamp=detection.timestamp,
            source=self.name,
            data={
                "confidence": detection.confidence,
                "detector_type": detection.detector_type,
                "buffer_index": detection.buffer_index,
                "metadata": detection.metadata,
            },
        )
        self.event_bus.publish(event)
        self._last_publish_time = now


class ThresholdDetectorNode(AudioNode):
    """Simple amplitude threshold detector.

    Fast, low-complexity detector for basic onset detection.
    Good as a fallback or for validation.
    """

    def __init__(
        self,
        name: str = "ThresholdDetector",
        threshold_db: float = -20.0,
        min_duration_ms: float = 10.0,
        event_bus=None,
        publish_min_interval_ms: float = 50.0,
    ):
        super().__init__(name)
        # Clamp threshold_db to avoid math overflow
        self.threshold_db = max(min(threshold_db, 100.0), -100.0)
        self.threshold_linear = 10.0 ** (self.threshold_db / 20.0)
        self.min_duration_ms = min_duration_ms
        self.event_bus = event_bus

        self.min_duration_samples = 0
        self.in_event = False
        self.event_start_timestamp = None
        self.event_start_sample = None
        self.event_peak = 0.0
        self.logger = logging.getLogger(self.__class__.__name__)
        # Rate-limit publishing to avoid flooding (seconds)
        self.publish_min_interval = publish_min_interval_ms / 1000.0
        self._last_publish_time = 0.0

    def process(self, buffer: AudioBuffer) -> Optional[AudioBuffer]:
        """Detect amplitude threshold crossings."""
        self.logger.info(
            f"Received buffer {buffer.buffer_index} (min={buffer.samples.min():.4f}, max={buffer.samples.max():.4f}, mean={buffer.samples.mean():.4f}, std={buffer.samples.std():.4f})"
        )
        # Update min_duration in samples
        if self.min_duration_samples == 0:
            self.min_duration_samples = int(
                (self.min_duration_ms / 1000.0) * buffer.sample_rate
            )

        # Get mono samples
        samples = buffer.samples if buffer.is_mono else np.mean(buffer.samples, axis=1)

        # Find threshold crossings
        above_threshold = np.abs(samples) > self.threshold_linear

        for i, is_above in enumerate(above_threshold):
            time_offset = i / buffer.sample_rate
            current_timestamp = buffer.timestamp + time_offset

            if is_above:
                peak_value = abs(samples[i])

                if not self.in_event:
                    # Event start
                    self.in_event = True
                    self.event_start_timestamp = current_timestamp
                    self.event_start_sample = i
                    self.event_peak = peak_value
                    # Publish immediately on event start to catch short transients
                    detection = DetectionEvent(
                        timestamp=self.event_start_timestamp,
                        source=self.name,
                        confidence=min(self.event_peak, 1.0),
                        detector_type="threshold",
                        buffer_index=buffer.buffer_index,
                    )
                    meta = {
                        "threshold_db": self.threshold_db,
                        "peak_amplitude": float(self.event_peak),
                        "duration_samples": 1,
                        "duration_ms": (1 / buffer.sample_rate) * 1000,
                    }
                    detection.data.setdefault("metadata", meta)
                    setattr(detection, "metadata", meta)
                    if self.event_bus:
                        self._publish_detection(detection)
                else:
                    # Update peak
                    if peak_value > self.event_peak:
                        self.event_peak = peak_value

            elif self.in_event:
                # Event end - check duration
                event_duration_samples = i - self.event_start_sample

                if event_duration_samples >= self.min_duration_samples:
                    # Valid detection
                    detection = DetectionEvent(
                        timestamp=self.event_start_timestamp,
                        source=self.name,
                        confidence=min(self.event_peak, 1.0),
                        detector_type="threshold",
                        buffer_index=buffer.buffer_index,
                    )
                    meta = {
                        "threshold_db": self.threshold_db,
                        "peak_amplitude": float(self.event_peak),
                        "duration_samples": event_duration_samples,
                        "duration_ms": (event_duration_samples / buffer.sample_rate)
                        * 1000,
                    }
                    detection.data.setdefault("metadata", meta)
                    setattr(detection, "metadata", meta)

                    self.logger.info(
                        f"Detection at {self.event_start_timestamp:.6f}s "
                        f"(peak: {self.event_peak:.3f}, duration: {event_duration_samples} samples)"
                    )

                    if self.event_bus:
                        self._publish_detection(detection)

                # Reset
                self.in_event = False
                self.event_peak = 0.0

        # Handle event continuing to next buffer
        if self.in_event:
            # Event continues, will finish in next buffer
            self.event_start_sample = 0

        return buffer

    def _publish_detection(self, detection: DetectionEvent):
        """Publish detection event to event bus."""
        # Debounce rapid detections
        now = time.time()
        if now - self._last_publish_time < self.publish_min_interval:
            return

        event = Event(
            event_type=EventType.DETECTION,
            timestamp=detection.timestamp,
            source=self.name,
            data={
                "confidence": detection.confidence,
                "detector_type": detection.detector_type,
                "buffer_index": detection.buffer_index,
                "metadata": detection.metadata,
            },
        )
        self.event_bus.publish(event)
        self._last_publish_time = now
