import io
import numpy as np
import pytest
from src.audio.i2s_raw_source import I2SRawSourceNode

class DummyFile:
    def __init__(self, data: bytes):
        self._io = io.BytesIO(data)
        self.closed = False
    def read(self, n):
        return self._io.read(n)
    def close(self):
        self.closed = True

@pytest.fixture
def dummy_i2s_data():
    # Generate 1024 samples of int32 data (mono)
    samples = np.arange(1024, dtype=np.int32)
    return samples.tobytes()


def test_read_buffer(monkeypatch, dummy_i2s_data):
    node = I2SRawSourceNode(buffer_size=1024, format_bits=32)
    dummy_file = DummyFile(dummy_i2s_data)
    monkeypatch.setattr(node, 'file', dummy_file)
    node.running = True
    buf = node.read_buffer()
    assert buf is not None
    assert buf.samples.shape[0] == 1024
    assert np.all(buf.samples == np.arange(1024, dtype=np.int32))
    assert buf.channels == 1
    assert buf.sample_rate == 48000
    assert buf.buffer_index == 0 or buf.buffer_index == 1


def test_incomplete_read(monkeypatch):
    node = I2SRawSourceNode(buffer_size=1024, format_bits=32)
    dummy_file = DummyFile(b'1234')  # Too short
    monkeypatch.setattr(node, 'file', dummy_file)
    node.running = True
    buf = node.read_buffer()
    assert buf is None


def test_stop_closes_file(monkeypatch):
    node = I2SRawSourceNode()
    dummy_file = DummyFile(b'0' * 4096)
    monkeypatch.setattr(node, 'file', dummy_file)
    node.running = True
    node.stop()
    assert dummy_file.closed
