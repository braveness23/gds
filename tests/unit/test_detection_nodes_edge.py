import numpy as np
import pytest

from src.audio.audio_nodes import AudioBuffer
from src.detection.detection_nodes import ThresholdDetectorNode


def test_threshold_detector_invalid_input():
    node = ThresholdDetectorNode()
    # Pass None as buffer
    with pytest.raises(AttributeError):
        node.process(None)


def test_threshold_detector_extreme_threshold():
    """Test that extreme threshold doesn't cause crashes, returns buffer."""
    node = ThresholdDetectorNode(threshold_db=1e6)
    buf = AudioBuffer(
        samples=np.zeros(1024),
        timestamp=0,
        sample_rate=48000,
        channels=1,
        buffer_index=0,
    )
    result = node.process(buf)
    # Should return buffer even with extreme threshold (no detection)
    assert result is not None
    assert result.buffer_index == 0
