import pytest

from src.audio.audio_nodes import AudioSourceNode


class FailingSource(AudioSourceNode):
    def start(self):
        raise Exception("Source start failure")

    def stop(self):
        pass

    def read_buffer(self):
        raise Exception("Read buffer failure")

    def process(self, buffer):
        pass


def test_source_start_failure():
    source = FailingSource(name="fail_source", sample_rate=48000, channels=1, buffer_size=1024)
    with pytest.raises(Exception):
        source.start()


def test_source_read_buffer_failure():
    source = FailingSource(name="fail_source", sample_rate=48000, channels=1, buffer_size=1024)
    with pytest.raises(Exception):
        source.read_buffer()
