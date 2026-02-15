import pytest
from src.processing.processing_nodes import HighPassFilterNode, GainNode
from src.audio.audio_nodes import AudioBuffer
import numpy as np

def test_highpass_invalid_cutoff():
    node = HighPassFilterNode(cutoff_freq=1e9)
    buf = AudioBuffer(samples=np.zeros(1024), timestamp=0, sample_rate=48000, channels=1, buffer_index=0)
    with pytest.raises(ValueError):
        node.process(buf)

def test_gain_node_extreme_gain():
    node = GainNode(gain_db=100)
    buf = AudioBuffer(samples=np.ones(10), timestamp=0, sample_rate=48000, channels=1, buffer_index=0)
    out = node.process(buf)
    assert np.all(out.samples > 1e3)
