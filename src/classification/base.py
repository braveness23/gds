"""Base classes for strix acoustic event classifiers.

Implement AcousticClassifier to add custom classification logic to the pipeline.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class ClassificationResult:
    """Result of acoustic event classification."""

    event_type: str  # "gunshot", "explosion", "drone", "thunder", "unknown"
    confidence: float  # 0.0 - 1.0
    subtype: Optional[str] = None  # e.g. "muzzle_blast", "ballistic_crack"
    metadata: dict = field(default_factory=dict)


class AcousticClassifier(ABC):
    """Base class for all strix acoustic event classifiers.

    Implement this interface to add custom classification logic.
    A classifier receives audio buffer data and returns an event type
    with confidence score.

    Example:
        class MyClassifier(AcousticClassifier):
            def classify(self, audio_buffer, sample_rate, detection_event):
                # your logic here
                return ClassificationResult("gunshot", 0.92)
    """

    @abstractmethod
    def classify(
        self,
        audio_buffer: np.ndarray,
        sample_rate: int,
        detection_event=None,
    ) -> ClassificationResult:
        """Classify an acoustic event from an audio buffer.

        Args:
            audio_buffer: Raw audio samples (float32, normalized -1.0 to 1.0)
            sample_rate: Sample rate in Hz
            detection_event: Optional detection event from the event bus

        Returns:
            ClassificationResult with event_type and confidence
        """
        pass

    @property
    def name(self) -> str:
        """Classifier name (defaults to class name)."""
        return self.__class__.__name__


class RuleBasedClassifier(AcousticClassifier):
    """Simple rule-based classifier using signal characteristics.

    Subclass and implement classify() with your rules.
    """

    pass
