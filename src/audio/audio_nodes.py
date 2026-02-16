"""Audio source nodes for the gunshot detection system.

This module provides audio input sources that capture timestamped audio buffers.
All timestamps are captured at the earliest possible moment (buffer arrival) for
trilateration accuracy.
"""


import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, List, Optional

import numpy as np


@dataclass
class AudioBuffer:
    """Timestamped audio buffer with metadata."""

    samples: np.ndarray  # shape: (n_samples,) for mono, (n_samples, n_channels) for stereo
    timestamp: float  # System time (already GPS-synced via chrony/ntpd)
    sample_rate: int
    channels: int
    buffer_index: int

    @property
    def duration(self) -> float:
        """Duration of buffer in seconds."""
        return len(self.samples) / self.sample_rate

    @property
    def is_mono(self) -> bool:
        """Check if buffer is mono."""
        return self.channels == 1

    def to_mono(self) -> "AudioBuffer":
        """Convert stereo to mono by averaging channels."""
        if self.is_mono:
            return self

        mono_samples = np.mean(self.samples, axis=1)
        return AudioBuffer(
            samples=mono_samples,
            timestamp=self.timestamp,
            sample_rate=self.sample_rate,
            channels=1,
            buffer_index=self.buffer_index,
        )


class AudioNode(ABC):
    """Base class for all audio processing nodes."""

    def __init__(self, name: str):
        self.name = name
        self.outputs: List[Callable[[AudioBuffer], None]] = []

    def connect(self, receiver: Callable[[AudioBuffer], None]):
        """Connect this node's output to another node's input."""
        self.outputs.append(receiver)

    def emit(self, buffer: AudioBuffer):
        """Send buffer to all connected nodes."""
        for output in self.outputs:
            try:
                output(buffer)
            except Exception as e:
                # Intentionally broad: isolate callback failures to prevent one bad output
                # from crashing the audio pipeline. Still excludes system exits.
                logging.error(f"[{self.name}] Error in output callback: {e}")

    @abstractmethod
    def process(self, buffer: AudioBuffer) -> Optional[AudioBuffer]:
        """Process input buffer, return processed buffer or None."""
        pass

    def receive(self, buffer: AudioBuffer):
        """Receive buffer, process, and emit if result exists."""
        result = self.process(buffer)
        if result is not None:
            self.emit(result)


class AudioSourceNode(AudioNode):
    """Base class for audio sources that generate timestamped buffers."""

    def __init__(self, name: str, sample_rate: int, channels: int, buffer_size: int):
        super().__init__(name)
        self.sample_rate = sample_rate
        self.channels = channels
        self.buffer_size = buffer_size
        self.buffer_index = 0
        self.running = False

    @abstractmethod
    def start(self):
        """Start capturing audio."""
        pass

    @abstractmethod
    def stop(self):
        """Stop capturing audio."""
        pass

    def _create_buffer(self, samples: np.ndarray) -> AudioBuffer:
        """Create timestamped buffer from samples."""
        # System clock is already GPS-synced via chrony/ntpd
        timestamp = time.time()
        buffer = AudioBuffer(
            samples=samples,
            timestamp=timestamp,
            sample_rate=self.sample_rate,
            channels=self.channels,
            buffer_index=self.buffer_index,
        )
        self.buffer_index += 1
        return buffer


class ALSASourceNode(AudioSourceNode):
    """Capture audio from ALSA device (I2S mics configured as ALSA)."""

    def __init__(
        self,
        name: str = "ALSA",
        device: str = "default",
        sample_rate: int = 48000,
        channels: int = 1,
        buffer_size: int = 1024,
        format_bits: int = 32,
    ):
        # Ensure all positional arguments come before keyword arguments
        super().__init__(name, sample_rate, channels, buffer_size)
        self.device = device
        self.format_bits = format_bits
        self.stream = None
        self.pa = None
        self.logger = logging.getLogger(self.__class__.__name__)

    def start(self):
        """Start ALSA capture stream."""
        try:
            import pyaudio
        except ImportError:
            self.logger.error("pyaudio not installed. Run: pip install pyaudio")
            raise

        # Suppress ALSA warnings about missing PCM devices
        try:
            from ctypes import CFUNCTYPE, c_char_p, c_int, cdll

            ERROR_HANDLER_FUNC = CFUNCTYPE(
                None, c_char_p, c_int, c_char_p, c_int, c_char_p
            )

            def py_error_handler(filename, line, function, err, fmt):
                pass  # Suppress all ALSA error messages

            c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
            asound = cdll.LoadLibrary("libasound.so.2")
            asound.snd_lib_error_set_handler(c_error_handler)
        except (OSError, AttributeError, TypeError) as e:
            # Not critical; log at debug level and continue
            self.logger.debug("Failed to set ALSA error handler: %s", e, exc_info=True)

        self.running = True
        self.pa = pyaudio.PyAudio()

        # Determine format
        if self.format_bits == 32:
            format_type = pyaudio.paInt32
        elif self.format_bits == 24:
            format_type = pyaudio.paInt24
        elif self.format_bits == 16:
            format_type = pyaudio.paInt16
        else:
            raise ValueError(f"Unsupported format_bits: {self.format_bits}")

        # Find device index if not "default"
        device_index = None
        if self.device != "default":
            # First try: substring match against reported device names
            for i in range(self.pa.get_device_count()):
                info = self.pa.get_device_info_by_index(i)
                if self.device in info["name"] or info["name"] in self.device:
                    device_index = i
                    self.logger.info(f"Found device by name match: {info['name']}")
                    break

            # Second try: if device looks like hw:X,Y or plughw:X,Y, use /proc/asound/cards
            if device_index is None and (
                self.device.startswith("hw:") or self.device.startswith("plughw:")
            ):
                try:
                    # extract card number
                    _, card_dev = self.device.split(":", 1)
                    card_num = int(card_dev.split(",")[0])
                    # parse /proc/asound/cards to find the card id/text
                    card_name = None
                    with open("/proc/asound/cards", "r") as f:
                        lines = f.readlines()
                    for i in range(0, len(lines), 2):
                        if i + 1 < len(lines):
                            header = lines[i].strip()
                            if header.startswith(str(card_num) + " "):
                                # header format: "N [id       ]: short - long"
                                parts = header.split("]")
                                if len(parts) > 0:
                                    # extract id within brackets
                                    start = header.find("[")
                                    end = header.find("]")
                                    if start != -1 and end != -1:
                                        card_id = header[start + 1:end].strip()
                                        card_name = card_id
                                        break

                    if card_name:
                        for i in range(self.pa.get_device_count()):
                            info = self.pa.get_device_info_by_index(i)
                            if card_name in info["name"] or card_name.replace(
                                "_", ""
                            ) in info["name"].replace("_", ""):
                                device_index = i
                                self.logger.info(
                                    f"Found device by card id match: {info['name']}"
                                )
                                break
                except (IOError, OSError, ValueError, IndexError) as e:
                    # Ignore parsing errors but log for diagnostics
                    self.logger.debug(
                        "Failed parsing /proc/asound/cards: %s", e, exc_info=True
                    )

            if device_index is None:
                self.logger.warning(f"Device '{self.device}' not found, using default")

        try:
            self.stream = self.pa.open(
                format=format_type,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.buffer_size,
                stream_callback=self._audio_callback,
            )

            self.stream.start_stream()
            self.logger.info(
                f"Started ALSA capture - {self.sample_rate}Hz, "
                f"{self.channels}ch, {self.buffer_size} samples"
            )

        except (IOError, OSError, ValueError) as e:
            self.logger.error(f"Failed to start audio stream: {e}")
            self.running = False
            raise

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio callback - captures timestamp immediately."""
        import pyaudio

        # CRITICAL: Capture timestamp FIRST for trilateration accuracy
        timestamp = time.time()

        if status:
            self.logger.warning(f"Audio callback status: {status}")

        try:
            # Convert bytes to numpy array
            if self.format_bits == 32:
                samples = np.frombuffer(in_data, dtype=np.int32).astype(np.float32)
                samples = samples / (2**31 - 1)  # Normalize to [-1, 1]
            elif self.format_bits == 24:
                samples = np.frombuffer(in_data, dtype=np.int32).astype(np.float32)
                samples = samples / (2**23 - 1)
            elif self.format_bits == 16:
                samples = np.frombuffer(in_data, dtype=np.int16).astype(np.float32)
                samples = samples / (2**15 - 1)

            # Reshape for stereo
            if self.channels > 1:
                samples = samples.reshape(-1, self.channels)

            # Debug: print buffer stats
            self.logger.debug(
                f"Buffer stats: min={samples.min():.4f}, "
                f"max={samples.max():.4f}, mean={samples.mean():.4f}, "
                f"std={samples.std():.4f}"
            )

            # Create buffer with precise timestamp
            buffer = AudioBuffer(
                samples=samples,
                timestamp=timestamp,
                sample_rate=self.sample_rate,
                channels=self.channels,
                buffer_index=self.buffer_index,
            )
            self.buffer_index += 1

            # Emit to connected nodes
            self.emit(buffer)

        except Exception as e:
            # Intentionally broad: audio callback is critical real-time code.
            # Must never let exceptions escape or audio stream crashes. Excludes system exits.
            self.logger.error(f"Error in audio callback: {e}")

        return (None, pyaudio.paContinue)

    def stop(self):
        """Stop ALSA capture stream."""
        self.running = False

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()

        if self.pa:
            self.pa.terminate()

        self.logger.info("Stopped ALSA capture")

    def process(self, buffer: AudioBuffer) -> Optional[AudioBuffer]:
        """Source nodes don't process incoming buffers."""
        return None


class FileSourceNode(AudioSourceNode):
    """Read from audio file for testing/replay."""

    def __init__(
        self,
        name: str = "FileSource",
        filepath: str = None,
        buffer_size: int = 1024,
        realtime: bool = True,
        loop: bool = False,
    ):
        # Will determine sample_rate and channels when file is opened
        super().__init__(name, sample_rate=48000, channels=1, buffer_size=buffer_size)
        self.filepath = filepath
        self.realtime = realtime
        self.loop = loop
        self.sf = None
        self.read_thread = None

    def start(self):
        """Open file and start reading."""
        if not self.filepath:
            raise ValueError("No filepath specified")

        try:
            import soundfile as sf
        except ImportError:
            raise ImportError("soundfile not installed. Run: pip install soundfile")

        try:
            self.sf = sf.SoundFile(self.filepath)
            self.sample_rate = self.sf.samplerate
            self.channels = self.sf.channels

            self.running = True
            self.read_thread = threading.Thread(target=self._read_loop)
            self.read_thread.daemon = True
            self.read_thread.start()

            logging.info(
                f"[{self.name}] Reading from {self.filepath} "
                f"({self.sample_rate}Hz, {self.channels}ch)"
            )

        except (IOError, OSError, RuntimeError, ValueError) as e:
            logging.error(f"[{self.name}] Failed to open file: {e}")
            raise

    def _read_loop(self):
        """Read file in chunks."""
        while self.running:
            try:
                samples = self.sf.read(self.buffer_size)
                if len(samples) == 0:
                    # End of file
                    if self.loop:
                        self.sf.seek(0)
                        continue
                    else:
                        break
                # Pad last chunk if needed
                if len(samples) < self.buffer_size:
                    if self.channels == 1:
                        samples = np.pad(samples, (0, self.buffer_size - len(samples)))
                    else:
                        pad_size = self.buffer_size - len(samples)
                        samples = np.pad(samples, ((0, pad_size), (0, 0)))
                # Convert to float32 if needed
                if samples.dtype != np.float32:
                    samples = samples.astype(np.float32)
                buffer = self._create_buffer(samples)
                self.emit(buffer)
                # Simulate realtime if requested
                if self.realtime:
                    time.sleep(self.buffer_size / self.sample_rate)
            except (IOError, OSError, ValueError, RuntimeError) as e:
                logging.error(f"[{self.name}] Error reading file: {e}")
                break
        self.running = False
        logging.info(f"[{self.name}] Finished reading file")

    def stop(self):
        """Stop reading file."""
        self.running = False

        if self.read_thread:
            self.read_thread.join(timeout=2.0)

        if self.sf:
            self.sf.close()

        logging.info(f"[{self.name}] Stopped file reading")

    def process(self, buffer: AudioBuffer) -> Optional[AudioBuffer]:
        """Source nodes don't process incoming buffers."""
        return None
