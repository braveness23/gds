"""Unit tests for audio nodes."""

import time
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest

from src.audio.audio_nodes import (
    ALSASourceNode,
    AudioBuffer,
    AudioNode,
    AudioSourceNode,
    FileSourceNode,
)

# ============================================================================
# AudioBuffer Tests
# ============================================================================


class TestAudioBuffer:
    """Tests for AudioBuffer dataclass."""

    def test_audio_buffer_creation(self):
        """AudioBuffer should store samples and metadata."""
        samples = np.random.randn(1024).astype(np.float32)
        buffer = AudioBuffer(
            samples=samples,
            timestamp=123.456,
            sample_rate=48000,
            channels=1,
            buffer_index=5,
        )

        assert len(buffer.samples) == 1024
        assert buffer.timestamp == 123.456
        assert buffer.sample_rate == 48000
        assert buffer.channels == 1
        assert buffer.buffer_index == 5

    def test_duration_property(self):
        """Duration should be calculated correctly."""
        samples = np.zeros(480, dtype=np.float32)  # 10ms at 48kHz
        buffer = AudioBuffer(
            samples=samples,
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        assert buffer.duration == pytest.approx(0.01, rel=1e-6)  # 10ms

    def test_is_mono_property(self):
        """is_mono should correctly identify mono vs stereo."""
        mono_buffer = AudioBuffer(
            samples=np.zeros(1024, dtype=np.float32),
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )
        assert mono_buffer.is_mono is True

        stereo_buffer = AudioBuffer(
            samples=np.zeros((1024, 2), dtype=np.float32),
            timestamp=0.0,
            sample_rate=48000,
            channels=2,
            buffer_index=0,
        )
        assert stereo_buffer.is_mono is False

    def test_to_mono_stereo_conversion(self):
        """to_mono should average stereo channels."""
        # Create stereo signal: left=1.0, right=-1.0
        stereo_samples = np.zeros((1024, 2), dtype=np.float32)
        stereo_samples[:, 0] = 1.0  # Left channel
        stereo_samples[:, 1] = -1.0  # Right channel

        stereo_buffer = AudioBuffer(
            samples=stereo_samples,
            timestamp=123.0,
            sample_rate=48000,
            channels=2,
            buffer_index=5,
        )

        mono_buffer = stereo_buffer.to_mono()

        # Should average to 0.0
        assert mono_buffer.channels == 1
        assert np.all(mono_buffer.samples == pytest.approx(0.0))
        assert mono_buffer.timestamp == 123.0
        assert mono_buffer.sample_rate == 48000
        assert mono_buffer.buffer_index == 5

    def test_to_mono_already_mono(self):
        """to_mono should return same buffer if already mono."""
        mono_buffer = AudioBuffer(
            samples=np.ones(1024, dtype=np.float32),
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        result = mono_buffer.to_mono()
        assert result is mono_buffer  # Should be same object


# ============================================================================
# AudioNode Tests (Base Class)
# ============================================================================


class TestAudioNode:
    """Tests for AudioNode base class."""

    def test_audio_node_connect(self):
        """AudioNode should connect to receivers."""

        class DummyNode(AudioNode):
            def process(self, buffer):
                return buffer

        node = DummyNode("test")
        receiver = Mock()

        node.connect(receiver)
        assert receiver in node.outputs

    def test_audio_node_emit_success(self):
        """emit should send buffer to all connected receivers."""

        class DummyNode(AudioNode):
            def process(self, buffer):
                return buffer

        node = DummyNode("test")
        receiver1 = Mock()
        receiver2 = Mock()

        node.connect(receiver1)
        node.connect(receiver2)

        buffer = AudioBuffer(
            samples=np.zeros(100, dtype=np.float32),
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        node.emit(buffer)

        receiver1.assert_called_once_with(buffer)
        receiver2.assert_called_once_with(buffer)

    def test_audio_node_emit_error_isolation(self, caplog):
        """emit should isolate errors in output callbacks."""

        class DummyNode(AudioNode):
            def process(self, buffer):
                return buffer

        node = DummyNode("test")
        receiver1 = Mock(side_effect=ValueError("receiver1 error"))
        receiver2 = Mock()  # This should still be called

        node.connect(receiver1)
        node.connect(receiver2)

        buffer = AudioBuffer(
            samples=np.zeros(100, dtype=np.float32),
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        node.emit(buffer)

        # receiver1 raised error but receiver2 should still be called
        receiver1.assert_called_once()
        receiver2.assert_called_once_with(buffer)
        assert "Error in output callback" in caplog.text

    def test_audio_node_receive_and_emit(self):
        """receive should process and emit result."""

        class PassthroughNode(AudioNode):
            def process(self, buffer):
                return buffer  # Just return input

        node = PassthroughNode("passthrough")
        receiver = Mock()
        node.connect(receiver)

        buffer = AudioBuffer(
            samples=np.zeros(100, dtype=np.float32),
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        node.receive(buffer)
        receiver.assert_called_once_with(buffer)

    def test_audio_node_receive_none_result(self):
        """receive should not emit if process returns None."""

        class FilterNode(AudioNode):
            def process(self, buffer):
                return None  # Filter out all buffers

        node = FilterNode("filter")
        receiver = Mock()
        node.connect(receiver)

        buffer = AudioBuffer(
            samples=np.zeros(100, dtype=np.float32),
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        node.receive(buffer)
        receiver.assert_not_called()


# ============================================================================
# AudioSourceNode Tests (Base Class)
# ============================================================================


class TestAudioSourceNode:
    """Tests for AudioSourceNode base class."""

    def test_audio_source_initialization(self):
        """AudioSourceNode should initialize with audio parameters."""

        class DummySource(AudioSourceNode):
            def start(self):
                pass

            def stop(self):
                pass

            def process(self, buffer):
                return None

        source = DummySource("test", sample_rate=48000, channels=2, buffer_size=1024)

        assert source.sample_rate == 48000
        assert source.channels == 2
        assert source.buffer_size == 1024
        assert source.buffer_index == 0
        assert source.running is False

    def test_create_buffer(self):
        """_create_buffer should create timestamped AudioBuffer."""

        class DummySource(AudioSourceNode):
            def start(self):
                pass

            def stop(self):
                pass

            def process(self, buffer):
                return None

        source = DummySource("test", sample_rate=48000, channels=1, buffer_size=1024)
        samples = np.random.randn(1024).astype(np.float32)

        buffer = source._create_buffer(samples)

        assert isinstance(buffer, AudioBuffer)
        assert len(buffer.samples) == 1024
        assert buffer.sample_rate == 48000
        assert buffer.channels == 1
        assert buffer.buffer_index == 0
        assert isinstance(buffer.timestamp, float)

        # Create second buffer - index should increment
        buffer2 = source._create_buffer(samples)
        assert buffer2.buffer_index == 1


# ============================================================================
# ALSASourceNode Tests
# ============================================================================


class TestALSASourceNode:
    """Tests for ALSASourceNode (ALSA audio capture)."""

    def test_alsa_initialization(self):
        """ALSASourceNode should initialize with ALSA parameters."""
        node = ALSASourceNode(
            name="TestALSA",
            device="hw:1,0",
            sample_rate=44100,
            channels=2,
            buffer_size=512,
            format_bits=16,
        )

        assert node.name == "TestALSA"
        assert node.device == "hw:1,0"
        assert node.sample_rate == 44100
        assert node.channels == 2
        assert node.buffer_size == 512
        assert node.format_bits == 16

    @pytest.mark.skip(
        reason="ALSA tests require hardware integration - tested in integration tests"
    )
    def test_alsa_start_success(self):
        """start should initialize PyAudio and open stream."""
        pass

    @pytest.mark.skip(
        reason="ALSA tests require hardware integration - tested in integration tests"
    )
    def test_alsa_start_invalid_format(self):
        """start should raise ValueError for unsupported format_bits."""
        pass

    @pytest.mark.skip(
        reason="ALSA tests require hardware integration - tested in integration tests"
    )
    def test_alsa_stop(self):
        """stop should close stream and terminate PyAudio."""
        pass

    def test_alsa_process_returns_none(self):
        """process should return None (sources don't process input)."""
        node = ALSASourceNode()
        buffer = AudioBuffer(
            samples=np.zeros(1024, dtype=np.float32),
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        result = node.process(buffer)
        assert result is None

    def test_alsa_valid_device_strings(self):
        """Valid ALSA device strings should not raise."""
        for device in ("default", "", "hw:0,0", "hw:1,0", "hw:2,3", "plughw:0,0", "plughw:1,2"):
            ALSASourceNode(device=device)  # should not raise

    def test_alsa_invalid_device_string_raises(self):
        """Malformed hw:/plughw: device strings should raise ValueError at construction."""
        for bad in ("hw:abc,0", "hw:0", "hw:,0", "plughw:abc,1", "hw:0,"):
            with pytest.raises(ValueError, match="Invalid ALSA device string"):
                ALSASourceNode(device=bad)


# ============================================================================
# FileSourceNode Tests
# ============================================================================


class TestFileSourceNode:
    """Tests for FileSourceNode (file reading)."""

    def test_file_source_initialization(self):
        """FileSourceNode should initialize with file parameters."""
        node = FileSourceNode(
            name="TestFile",
            filepath="/path/to/audio.wav",
            buffer_size=2048,
            realtime=False,
            loop=True,
        )

        assert node.name == "TestFile"
        assert node.filepath == "/path/to/audio.wav"
        assert node.buffer_size == 2048
        assert node.realtime is False
        assert node.loop is True

    def test_file_source_start_no_filepath(self):
        """start should raise ValueError if no filepath."""
        node = FileSourceNode()

        with pytest.raises(ValueError, match="No filepath specified"):
            node.start()

    def test_file_source_start_success(self):
        """start should open file and start read thread."""
        mock_sf = MagicMock()
        mock_file = Mock()
        mock_file.samplerate = 44100
        mock_file.channels = 2
        mock_sf.SoundFile.return_value = mock_file

        with patch.dict("sys.modules", {"soundfile": mock_sf}):
            node = FileSourceNode(filepath="/fake/path.wav")
            node.start()

            assert node.running is True
            assert node.sample_rate == 44100
            assert node.channels == 2
            mock_sf.SoundFile.assert_called_once_with("/fake/path.wav")
            assert node.read_thread is not None
            assert node.read_thread.daemon is True

            # Cleanup
            node.stop()

    def test_file_source_read_loop_emit(self):
        """_read_loop should emit buffers when reading."""
        mock_sf = MagicMock()
        mock_file = Mock()
        mock_file.samplerate = 48000
        mock_file.channels = 1
        # Return one buffer then EOF
        mock_file.read.side_effect = [
            np.random.randn(1024).astype(np.float32),
            np.array([]),  # EOF
        ]
        mock_sf.SoundFile.return_value = mock_file

        with patch.dict("sys.modules", {"soundfile": mock_sf}):
            node = FileSourceNode(filepath="/fake/path.wav", realtime=False)
            receiver = Mock()
            node.connect(receiver)

            node.start()
            time.sleep(0.2)  # Let thread run
            node.stop()

            # Should have emitted one buffer
            assert receiver.call_count >= 1
            buffer = receiver.call_args[0][0]
            assert isinstance(buffer, AudioBuffer)

    def test_file_source_loop_mode(self):
        """_read_loop should loop file when loop=True."""
        mock_sf = MagicMock()
        mock_file = Mock()
        mock_file.samplerate = 48000
        mock_file.channels = 1

        read_count = [0]

        def read_side_effect(buffer_size):
            read_count[0] += 1
            if read_count[0] <= 2:
                return np.random.randn(buffer_size).astype(np.float32)
            else:
                return np.array([])  # EOF after 2 reads

        mock_file.read.side_effect = read_side_effect
        mock_sf.SoundFile.return_value = mock_file

        with patch.dict("sys.modules", {"soundfile": mock_sf}):
            node = FileSourceNode(filepath="/fake/path.wav", loop=True, realtime=False)
            node.start()
            time.sleep(0.3)
            node.stop()

            # Should have called seek(0) to loop
            assert mock_file.seek.called

    def test_file_source_process_returns_none(self):
        """process should return None (sources don't process input)."""
        node = FileSourceNode(filepath="/fake/path.wav")
        buffer = AudioBuffer(
            samples=np.zeros(1024, dtype=np.float32),
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        result = node.process(buffer)
        assert result is None

    def test_file_source_stop_closes_file(self):
        """stop should close file and join thread."""
        mock_sf = MagicMock()
        mock_file = Mock()
        mock_file.samplerate = 48000
        mock_file.channels = 1
        mock_file.read.return_value = np.array([])  # EOF immediately
        mock_sf.SoundFile.return_value = mock_file

        with patch.dict("sys.modules", {"soundfile": mock_sf}):
            node = FileSourceNode(filepath="/fake/path.wav", realtime=False)
            node.start()
            time.sleep(0.1)
            node.stop()

            assert node.running is False
            mock_file.close.assert_called()
