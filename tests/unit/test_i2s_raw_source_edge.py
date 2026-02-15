import pytest
from src.audio.i2s_raw_source import I2SRawSourceNode

class DummyFile:
    def __init__(self, fail_read=False, incomplete=False):
        self.closed = False
        self.fail_read = fail_read
        self.incomplete = incomplete
        self.read_calls = 0
    def read(self, n):
        self.read_calls += 1
        if self.fail_read:
            raise IOError("Read error")
        if self.incomplete:
            return b"\x00" * (n - 1)
        return b"\x00" * n
    def close(self):
        self.closed = True

def test_open_device_failure(monkeypatch):
    node = I2SRawSourceNode(device="/dev/nonexistent")
    monkeypatch.setattr("builtins.open", lambda *a, **kw: (_ for _ in ()).throw(IOError("Open error")))
    with pytest.raises(IOError):
        node.start()

def test_incomplete_read(monkeypatch):
    node = I2SRawSourceNode()
    node.file = DummyFile(incomplete=True)
    node.running = True
    node.channels = 1
    node.buffer_size = 1024
    node.format_bits = 32
    assert node.read_buffer() is None

def test_read_error(monkeypatch):
    node = I2SRawSourceNode()
    node.file = DummyFile(fail_read=True)
    node.running = True
    node.channels = 1
    node.buffer_size = 1024
    node.format_bits = 32
    with pytest.raises(IOError):
        node.read_buffer()

def test_stop_closes_file():
    node = I2SRawSourceNode()
    dummy = DummyFile()
    node.file = dummy
    node.running = True
    node.stop()
    assert dummy.closed
