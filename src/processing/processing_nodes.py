"""Signal processing nodes for audio pipeline.

This module provides nodes for filtering, conversion, and analysis of audio buffers.
"""

import numpy as np
from scipy import signal
from typing import Optional
from src.audio.audio_nodes import AudioNode, AudioBuffer


class MonoConversionNode(AudioNode):
    """Convert stereo to mono by averaging channels."""
    
    def __init__(self, name: str = "MonoConverter"):
        super().__init__(name)
    
    def process(self, buffer: AudioBuffer) -> Optional[AudioBuffer]:
        """Convert to mono if stereo, pass through if already mono."""
        if buffer.is_mono:
            return buffer
        
        return buffer.to_mono()


class HighPassFilterNode(AudioNode):
    """High-pass filter for removing low-frequency noise.
    
    Gunshots have most energy above 5kHz, so filtering below that
    removes environmental noise (wind, traffic, voices).
    """
    
    def __init__(self,
                 name: str = "HighPassFilter",
                 cutoff_freq: float = 5000,
                 order: int = 4,
                 filter_type: str = 'butterworth'):
        super().__init__(name)
        self.cutoff_freq = cutoff_freq
        self.order = order
        self.filter_type = filter_type
        self.sample_rate = None
        self.sos = None  # Second-order sections for numerical stability
        self.zi = None   # Filter state for continuous processing
    
    def _init_filter(self, sample_rate: int, channels: int):
        """Initialize filter coefficients."""
        if self.sample_rate == sample_rate and self.zi is not None:
            return  # Already initialized for this sample rate
        
        self.sample_rate = sample_rate
        nyquist = sample_rate / 2.0
        normalized_cutoff = self.cutoff_freq / nyquist
        
        if normalized_cutoff >= 1.0:
            raise ValueError(f"Cutoff frequency {self.cutoff_freq}Hz is above Nyquist "
                           f"frequency {nyquist}Hz for sample rate {sample_rate}Hz")
        
        # Design filter using second-order sections (more stable than ba form)
        if self.filter_type == 'butterworth':
            self.sos = signal.butter(
                self.order,
                normalized_cutoff,
                btype='highpass',
                output='sos'
            )
        elif self.filter_type == 'chebyshev':
            self.sos = signal.cheby1(
                self.order,
                0.5,  # 0.5 dB ripple in passband
                normalized_cutoff,
                btype='highpass',
                output='sos'
            )
        else:
            raise ValueError(f"Unknown filter type: {self.filter_type}")
        
        # Initialize filter state for continuous processing across buffers
        self.zi = signal.sosfilt_zi(self.sos)
        
        # Expand state for multi-channel
        if channels > 1:
            # Shape: (n_sections, channels, 2)
            self.zi = np.tile(self.zi[:, np.newaxis, :], (1, channels, 1))
        
        print(f"[{self.name}] Initialized {self.filter_type} filter: "
              f"{self.cutoff_freq}Hz cutoff, order {self.order}")
    
    def process(self, buffer: AudioBuffer) -> Optional[AudioBuffer]:
        """Apply high-pass filter to buffer."""
        # Initialize filter on first buffer
        if self.sos is None:
            self._init_filter(buffer.sample_rate, buffer.channels)
        
        # Apply filter with state
        if buffer.channels == 1:
            # Mono processing
            filtered, self.zi = signal.sosfilt(
                self.sos,
                buffer.samples,
                zi=self.zi
            )
        else:
            # Stereo/multi-channel processing
            filtered = np.zeros_like(buffer.samples)
            for ch in range(buffer.channels):
                filtered[:, ch], self.zi[:, ch, :] = signal.sosfilt(
                    self.sos,
                    buffer.samples[:, ch],
                    zi=self.zi[:, ch, :]
                )
        
        return AudioBuffer(
            samples=filtered,
            timestamp=buffer.timestamp,
            sample_rate=buffer.sample_rate,
            channels=buffer.channels,
            buffer_index=buffer.buffer_index
        )


class GainNode(AudioNode):
    """Apply gain or attenuation to audio signal."""
    
    def __init__(self, name: str = "Gain", gain_db: float = 0.0):
        super().__init__(name)
        self.gain_db = gain_db
        self.gain_linear = 10.0 ** (gain_db / 20.0)
    
    def set_gain(self, gain_db: float):
        """Update gain in dB."""
        self.gain_db = gain_db
        self.gain_linear = 10.0 ** (gain_db / 20.0)
        print(f"[{self.name}] Gain updated to {gain_db:.1f} dB")
    
    def process(self, buffer: AudioBuffer) -> Optional[AudioBuffer]:
        """Apply gain to samples."""
        if self.gain_linear == 1.0:
            # No gain change, pass through unchanged
            return buffer
        
        return AudioBuffer(
            samples=buffer.samples * self.gain_linear,
            timestamp=buffer.timestamp,
            sample_rate=buffer.sample_rate,
            channels=buffer.channels,
            buffer_index=buffer.buffer_index
        )


class BufferSplitterNode(AudioNode):
    """Split audio buffer to multiple outputs for parallel processing.
    
    This allows running multiple detectors (Aubio, ML, threshold) in parallel
    on the same audio stream.
    """
    
    def __init__(self, name: str = "Splitter"):
        super().__init__(name)
    
    def process(self, buffer: AudioBuffer) -> Optional[AudioBuffer]:
        """Pass through unchanged - splitting happens in emit()."""
        return buffer


class RMSCalculatorNode(AudioNode):
    """Calculate RMS (Root Mean Square) level for monitoring."""
    
    def __init__(self, name: str = "RMS", window_size: int = 10):
        super().__init__(name)
        self.window_size = window_size
        self.rms_history = []
        self.current_rms = 0.0
    
    def process(self, buffer: AudioBuffer) -> Optional[AudioBuffer]:
        """Calculate RMS and pass through buffer."""
        # Calculate RMS of this buffer
        rms = np.sqrt(np.mean(buffer.samples ** 2))
        
        # Update history
        self.rms_history.append(rms)
        if len(self.rms_history) > self.window_size:
            self.rms_history.pop(0)
        
        # Update current (windowed average)
        self.current_rms = np.mean(self.rms_history)
        
        # Pass through unchanged
        return buffer
    
    def get_rms_db(self) -> float:
        """Get current RMS in dB."""
        if self.current_rms > 0:
            return 20 * np.log10(self.current_rms)
        return -np.inf
    
    def get_rms_linear(self) -> float:
        """Get current RMS in linear scale [0, 1]."""
        return self.current_rms


class DCRemovalNode(AudioNode):
    """Remove DC offset from audio signal.
    
    Uses a simple high-pass filter at very low frequency (~5Hz)
    to remove any DC component.
    """
    
    def __init__(self, name: str = "DCRemoval", cutoff_freq: float = 5.0):
        super().__init__(name)
        self.cutoff_freq = cutoff_freq
        self.hpf = HighPassFilterNode(
            name=f"{name}_HPF",
            cutoff_freq=cutoff_freq,
            order=2
        )
    
    def process(self, buffer: AudioBuffer) -> Optional[AudioBuffer]:
        """Remove DC offset."""
        return self.hpf.process(buffer)


class NormalizationNode(AudioNode):
    """Normalize audio to target RMS level.
    
    Useful for compensating for different microphone sensitivities
    across the fleet.
    """
    
    def __init__(self,
                 name: str = "Normalizer",
                 target_rms: float = 0.1,
                 max_gain_db: float = 40.0):
        super().__init__(name)
        self.target_rms = target_rms
        self.max_gain = 10.0 ** (max_gain_db / 20.0)
    
    def process(self, buffer: AudioBuffer) -> Optional[AudioBuffer]:
        """Normalize buffer to target RMS."""
        current_rms = np.sqrt(np.mean(buffer.samples ** 2))
        
        if current_rms < 1e-6:
            # Silence, don't amplify
            return buffer
        
        # Calculate required gain
        gain = self.target_rms / current_rms
        
        # Limit gain to prevent excessive amplification
        gain = min(gain, self.max_gain)
        
        return AudioBuffer(
            samples=buffer.samples * gain,
            timestamp=buffer.timestamp,
            sample_rate=buffer.sample_rate,
            channels=buffer.channels,
            buffer_index=buffer.buffer_index
        )


class ClippingDetectorNode(AudioNode):
    """Detect audio clipping (saturation).
    
    Useful for alerting when microphone input is too loud.
    """
    
    def __init__(self,
                 name: str = "ClipDetector",
                 threshold: float = 0.99,
                 min_duration_samples: int = 3):
        super().__init__(name)
        self.threshold = threshold
        self.min_duration_samples = min_duration_samples
        self.clipping_count = 0
    
    def process(self, buffer: AudioBuffer) -> Optional[AudioBuffer]:
        """Check for clipping and pass through."""
        # Find samples above threshold
        clipped = np.abs(buffer.samples) > self.threshold
        
        if np.any(clipped):
            # Count consecutive clipped samples
            clipped_runs = self._find_runs(clipped)
            
            for start, length in clipped_runs:
                if length >= self.min_duration_samples:
                    self.clipping_count += 1
                    print(f"[{self.name}] WARNING: Clipping detected at buffer "
                          f"{buffer.buffer_index}, sample {start}, duration {length}")
        
        return buffer
    
    @staticmethod
    def _find_runs(x):
        """Find runs of consecutive True values."""
        # Ensure it's a 1D array
        if x.ndim > 1:
            x = x.flatten()
        
        # Find run starts
        x_padded = np.concatenate([[False], x, [False]])
        diff = np.diff(x_padded.astype(int))
        run_starts = np.where(diff == 1)[0]
        run_ends = np.where(diff == -1)[0]
        
        runs = []
        for start, end in zip(run_starts, run_ends):
            runs.append((start, end - start))
        
        return runs
