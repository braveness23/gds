"""Unit tests for ALSASourceNode._audio_callback.

Tests the real-time callback without any audio hardware.  pyaudio is mocked
via sys.modules injection so the module never needs to be installed.
"""

import struct
import sys
import types
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Mock pyaudio before importing audio_nodes
# ---------------------------------------------------------------------------

def _make_pyaudio_mock():
    mod = types.ModuleType("pyaudio")
    mod.paContinue = 0
    mod.paComplete = 1
    mod.paAbort = 2
    mod.paInt32 = 8
    mod.paInt24 = 4
    mod.paInt16 = 2
    mod.PyAudio = MagicMock()
    return mod


@pytest.fixture(autouse=True)
def mock_pyaudio():
    """Inject a fake pyaudio into sys.modules for the duration of each test."""
    fake = _make_pyaudio_mock()
    with patch.dict(sys.modules, {"pyaudio": fake}):
        yield fake


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_node(format_bits=32, channels=1, sample_rate=48000, buffer_size=1024):
    from src.audio.audio_nodes import ALSASourceNode

    node = ALSASourceNode(
        name="test",
        device="default",
        sample_rate=sample_rate,
        channels=channels,
        buffer_size=buffer_size,
        format_bits=format_bits,
    )
    node.running = True
    return node


def _int32_bytes(values):
    return struct.pack(f"{len(values)}i", *values)


def _int16_bytes(values):
    return struct.pack(f"{len(values)}h", *values)


FAKE_TIME = 1_700_000_000.0
DUMMY_TIME_INFO = {}
NO_STATUS = 0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAudioCallbackFormats:
    def test_32bit_normalization(self):
        """32-bit samples are normalized to [-1, 1] by 2^31 - 1."""
        node = _make_node(format_bits=32)
        received = []
        node.connect(received.append)

        values = [2**30, -(2**30), 0, 2**31 - 1]
        in_data = _int32_bytes(values)

        with patch("time.time", return_value=FAKE_TIME):
            ret = node._audio_callback(in_data, len(values), DUMMY_TIME_INFO, NO_STATUS)

        assert ret == (None, 0)  # paContinue
        assert len(received) == 1
        buf = received[0]
        expected = np.array(values, dtype=np.float32) / (2**31 - 1)
        np.testing.assert_allclose(buf.samples, expected, rtol=1e-5)

    def test_16bit_normalization(self):
        """16-bit samples are normalized to [-1, 1] by 2^15 - 1."""
        node = _make_node(format_bits=16)
        received = []
        node.connect(received.append)

        values = [16384, -16384, 0, 32767]
        in_data = _int16_bytes(values)

        with patch("time.time", return_value=FAKE_TIME):
            ret = node._audio_callback(in_data, len(values), DUMMY_TIME_INFO, NO_STATUS)

        assert ret == (None, 0)
        buf = received[0]
        expected = np.array(values, dtype=np.float32) / (2**15 - 1)
        np.testing.assert_allclose(buf.samples, expected, rtol=1e-5)

    def test_24bit_normalization(self):
        """24-bit samples are stored in int32 containers, normalized by 2^23 - 1."""
        node = _make_node(format_bits=24)
        received = []
        node.connect(received.append)

        # 24-bit values packed into 32-bit containers
        values = [2**22, -(2**22), 0]
        in_data = _int32_bytes(values)

        with patch("time.time", return_value=FAKE_TIME):
            ret = node._audio_callback(in_data, len(values), DUMMY_TIME_INFO, NO_STATUS)

        assert ret == (None, 0)
        buf = received[0]
        expected = np.array(values, dtype=np.float32) / (2**23 - 1)
        np.testing.assert_allclose(buf.samples, expected, rtol=1e-5)


class TestAudioCallbackMetadata:
    def test_timestamp_captured_first(self):
        """Timestamp is set to time.time() called at callback entry."""
        node = _make_node()
        received = []
        node.connect(received.append)

        values = [0] * 4
        with patch("time.time", return_value=FAKE_TIME):
            node._audio_callback(_int32_bytes(values), len(values), DUMMY_TIME_INFO, NO_STATUS)

        assert received[0].timestamp == FAKE_TIME

    def test_buffer_index_increments(self):
        """buffer_index increments with each callback invocation."""
        node = _make_node()
        received = []
        node.connect(received.append)

        for _ in range(3):
            node._audio_callback(_int32_bytes([0, 0, 0, 0]), 4, DUMMY_TIME_INFO, NO_STATUS)

        indices = [buf.buffer_index for buf in received]
        assert indices == [0, 1, 2]

    def test_buffer_metadata(self):
        """AudioBuffer carries correct sample_rate and channels."""
        node = _make_node(sample_rate=44100, channels=1)
        received = []
        node.connect(received.append)

        node._audio_callback(_int32_bytes([0, 0]), 2, DUMMY_TIME_INFO, NO_STATUS)

        buf = received[0]
        assert buf.sample_rate == 44100
        assert buf.channels == 1


class TestAudioCallbackStereo:
    def test_stereo_reshape(self):
        """Stereo audio is reshaped to (n_frames, 2)."""
        node = _make_node(channels=2, format_bits=32)
        received = []
        node.connect(received.append)

        # 4 frames × 2 channels = 8 samples
        values = [1, 2, 3, 4, 5, 6, 7, 8]
        in_data = _int32_bytes(values)

        node._audio_callback(in_data, 4, DUMMY_TIME_INFO, NO_STATUS)

        buf = received[0]
        assert buf.samples.shape == (4, 2)


class TestAudioCallbackEdgeCases:
    def test_status_nonzero_logs_warning(self):
        """Non-zero status triggers a warning log."""
        node = _make_node()

        with patch.object(node.logger, "warning") as mock_warn:
            node._audio_callback(_int32_bytes([0, 0]), 2, DUMMY_TIME_INFO, status=42)

        mock_warn.assert_called_once()
        assert "42" in str(mock_warn.call_args)

    def test_exception_does_not_crash(self):
        """Exception inside callback is caught; paContinue still returned."""
        node = _make_node(format_bits=32)

        # Pass invalid bytes (wrong length for int32) to force a frombuffer error
        bad_data = b"\x00\x01\x02"  # 3 bytes — not a multiple of 4

        with patch.object(node.logger, "error") as mock_err:
            ret = node._audio_callback(bad_data, 0, DUMMY_TIME_INFO, NO_STATUS)

        assert ret == (None, 0)  # Must still return paContinue
        mock_err.assert_called_once()

    def test_emit_called_once_per_invocation(self):
        """emit() is called exactly once per callback invocation."""
        node = _make_node()

        with patch.object(node, "emit") as mock_emit:
            node._audio_callback(_int32_bytes([0, 0, 0, 0]), 4, DUMMY_TIME_INFO, NO_STATUS)

        mock_emit.assert_called_once()

    def test_multiple_outputs_all_receive(self):
        """All connected outputs receive the buffer."""
        node = _make_node()
        outputs = [[], []]
        node.connect(outputs[0].append)
        node.connect(outputs[1].append)

        node._audio_callback(_int32_bytes([0, 0]), 2, DUMMY_TIME_INFO, NO_STATUS)

        assert len(outputs[0]) == 1
        assert len(outputs[1]) == 1
