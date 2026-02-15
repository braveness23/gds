import numpy as np
import time
from .audio_nodes import AudioSourceNode, AudioBuffer

class I2SRawSourceNode(AudioSourceNode):
    """Capture audio directly from I2S interface (bypassing ALSA)."""
    def __init__(self, name="I2SRaw", device="/dev/i2s", sample_rate=48000, channels=1, buffer_size=1024, format_bits=32):
        super().__init__(name, sample_rate, channels, buffer_size)
        self.device = device
        self.format_bits = format_bits
        self.running = False
        self.file = None

    def start(self):
        import logging
        logger = logging.getLogger(self.__class__.__name__)
        try:
            self.file = open(self.device, "rb")
            self.running = True
            logger.info(f"[{self.name}] Opened I2S device: {self.device}")
        except Exception as e:
            logger.error(f"[{self.name}] Failed to open I2S device: {e}")
            self.running = False
            raise

    def stop(self):
        import logging
        logger = logging.getLogger(self.__class__.__name__)
        self.running = False
        if self.file:
            self.file.close()
            self.file = None
            logger.info(f"[{self.name}] Closed I2S device")

    def read_buffer(self):
        import logging
        logger = logging.getLogger(self.__class__.__name__)
        if not self.running or not self.file:
            return None
        bytes_per_sample = self.format_bits // 8
        total_bytes = self.buffer_size * self.channels * bytes_per_sample
        data = self.file.read(total_bytes)
        if len(data) != total_bytes:
            logger.warning(f"[{self.name}] Incomplete read from I2S device")
            return None
        if self.format_bits == 32:
            dtype = np.int32
        elif self.format_bits == 24:
            dtype = np.int32  # 24-bit packed in 32 bits
        elif self.format_bits == 16:
            dtype = np.int16
        else:
            raise ValueError(f"Unsupported format_bits: {self.format_bits}")
        samples = np.frombuffer(data, dtype=dtype)
        if self.channels > 1:
            samples = samples.reshape(-1, self.channels)
        buffer = AudioBuffer(
            samples=samples,
            timestamp=time.time(),
            sample_rate=self.sample_rate,
            channels=self.channels,
            buffer_index=self.buffer_index
        )
        self.buffer_index += 1
        return buffer

    def process(self, buffer):
        # Source node does not process incoming buffers
        return None
