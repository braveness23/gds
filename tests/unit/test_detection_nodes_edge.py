import pytest
from src.detection.detection_nodes import ThresholdDetectorNode
from src.audio.audio_nodes import AudioBuffer
import numpy as np

def test_threshold_detector_invalid_input():
    node = ThresholdDetectorNode()
    # Pass None as buffer
    with pytest.raises(AttributeError):
        node.process(None)

def test_threshold_detector_extreme_threshold():
    node = ThresholdDetectorNode(threshold_db=1e6)
    buf = AudioBuffer(samples=np.zeros(1024), timestamp=0, sample_rate=48000, channels=1, buffer_index=0)
    result = node.process(buf)
    assert result is None
