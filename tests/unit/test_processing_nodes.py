"""Unit tests for processing nodes."""

import numpy as np
import pytest

from src.audio.audio_nodes import AudioBuffer
from src.processing.processing_nodes import (
    ClippingDetectorNode,
    DCRemovalNode,
    GainNode,
    HighPassFilterNode,
    MonoConversionNode,
    NormalizationNode,
    RMSCalculatorNode,
)


# ============================================================================
# MonoConversionNode Tests
# ============================================================================


class TestMonoConversionNode:
    """Tests for MonoConversionNode."""

    def test_mono_pass_through(self):
        """Mono buffers should pass through unchanged."""
        node = MonoConversionNode()
        buffer = AudioBuffer(
            samples=np.ones(100, dtype=np.float32),
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        result = node.process(buffer)
        assert result is buffer  # Same object

    def test_stereo_conversion(self):
        """Stereo buffers should be converted to mono."""
        node = MonoConversionNode()
        stereo_samples = np.zeros((100, 2), dtype=np.float32)
        stereo_samples[:, 0] = 1.0
        stereo_samples[:, 1] = -1.0

        buffer = AudioBuffer(
            samples=stereo_samples,
            timestamp=0.0,
            sample_rate=48000,
            channels=2,
            buffer_index=0,
        )

        result = node.process(buffer)
        assert result.channels == 1
        assert np.all(result.samples == pytest.approx(0.0))


# ============================================================================
# HighPassFilterNode Tests
# ============================================================================


class TestHighPassFilterNode:
    """Tests for HighPassFilterNode."""

    def test_initialization(self):
        """HighPassFilterNode should initialize with filter parameters."""
        node = HighPassFilterNode(cutoff_freq=3000, order=6)
        assert node.cutoff_freq == 3000
        assert node.order == 6

    def test_filter_attenuates_low_frequencies(self):
        """High-pass filter should attenuate low frequencies."""
        node = HighPassFilterNode(cutoff_freq=5000, order=4)

        # Create low-frequency signal (100Hz)
        t = np.arange(1024) / 48000
        samples = np.sin(2 * np.pi * 100 * t).astype(np.float32)
        buffer = AudioBuffer(
            samples=samples,
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        result = node.process(buffer)
        # Low frequency should be heavily attenuated
        assert np.sqrt(np.mean(result.samples**2)) < np.sqrt(np.mean(samples**2)) * 0.1

    def test_filter_passes_high_frequencies(self):
        """High-pass filter should pass high frequencies."""
        node = HighPassFilterNode(cutoff_freq=1000, order=4)

        # Create high-frequency signal (10kHz)
        t = np.arange(1024) / 48000
        samples = np.sin(2 * np.pi * 10000 * t).astype(np.float32)
        buffer = AudioBuffer(
            samples=samples,
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        result = node.process(buffer)
        # High frequency should pass with minimal attenuation
        assert np.sqrt(np.mean(result.samples**2)) > np.sqrt(np.mean(samples**2)) * 0.8

    def test_cutoff_above_nyquist_raises_error(self):
        """Cutoff frequency above Nyquist should raise ValueError."""
        node = HighPassFilterNode(cutoff_freq=30000)  # Above 24kHz Nyquist

        buffer = AudioBuffer(
            samples=np.zeros(100, dtype=np.float32),
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        with pytest.raises(ValueError, match="above Nyquist"):
            node.process(buffer)

    def test_invalid_filter_type(self):
        """Invalid filter type should raise ValueError."""
        node = HighPassFilterNode(filter_type="invalid")

        buffer = AudioBuffer(
            samples=np.zeros(100, dtype=np.float32),
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        with pytest.raises(ValueError, match="Unknown filter type"):
            node.process(buffer)


# ============================================================================
# GainNode Tests
# ============================================================================


class TestGainNode:
    """Tests for GainNode."""

    def test_gain_amplification(self):
        """Gain node should amplify signal."""
        node = GainNode(gain_db=6.0)  # 2x linear gain

        samples = np.ones(100, dtype=np.float32) * 0.5
        buffer = AudioBuffer(
            samples=samples,
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        result = node.process(buffer)
        assert np.allclose(result.samples, 1.0, rtol=0.01)

    def test_gain_attenuation(self):
        """Gain node should attenuate signal."""
        node = GainNode(gain_db=-6.0)  # 0.5x linear gain

        samples = np.ones(100, dtype=np.float32)
        buffer = AudioBuffer(
            samples=samples,
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        result = node.process(buffer)
        assert np.allclose(result.samples, 0.5, rtol=0.01)

    def test_zero_gain(self):
        """Zero dB gain should not change signal."""
        node = GainNode(gain_db=0.0)

        samples = np.random.randn(100).astype(np.float32)
        buffer = AudioBuffer(
            samples=samples,
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        result = node.process(buffer)
        assert np.allclose(result.samples, samples)


# ============================================================================
# RMSCalculatorNode Tests
# ============================================================================


class TestRMSCalculatorNode:
    """Tests for RMSCalculatorNode."""

    def test_rms_calculation(self):
        """RMS should be calculated correctly."""
        node = RMSCalculatorNode()

        samples = np.ones(100, dtype=np.float32)
        buffer = AudioBuffer(
            samples=samples,
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        result = node.process(buffer)
        assert result is buffer  # Passes through
        assert node.current_rms == pytest.approx(1.0)
        assert node.get_rms_linear() == pytest.approx(1.0)

    def test_rms_zero_signal(self):
        """RMS of silence should be zero."""
        node = RMSCalculatorNode()

        samples = np.zeros(100, dtype=np.float32)
        buffer = AudioBuffer(
            samples=samples,
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        node.process(buffer)
        assert node.current_rms == pytest.approx(0.0)
        assert node.get_rms_db() == -np.inf


# ============================================================================
# DCRemovalNode Tests
# ============================================================================


class TestDCRemovalNode:
    """Tests for DCRemovalNode."""

    def test_dc_removal(self):
        """DC offset should be removed using HPF."""
        node = DCRemovalNode()

        # Create test signal with DC offset
        samples = np.ones(2000, dtype=np.float32) * 0.5  # Constant DC signal
        buffer = AudioBuffer(
            samples=samples,
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        result = node.process(buffer)
        # DC component should be heavily attenuated by HPF
        assert np.mean(np.abs(result.samples)) < 0.2  # Much lower than 0.5


# ============================================================================
# NormalizationNode Tests
# ============================================================================


class TestNormalizationNode:
    """Tests for NormalizationNode."""

    def test_normalization_to_target(self):
        """Signal should be normalized to target RMS."""
        node = NormalizationNode(target_rms=0.5)

        samples = np.random.randn(1000).astype(np.float32) * 0.1  # Low level
        buffer = AudioBuffer(
            samples=samples,
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        result = node.process(buffer)
        actual_rms = np.sqrt(np.mean(result.samples**2))
        assert actual_rms == pytest.approx(0.5, rel=0.1)

    def test_normalization_silence(self):
        """Silence should not be amplified."""
        node = NormalizationNode()

        samples = np.zeros(100, dtype=np.float32)
        buffer = AudioBuffer(
            samples=samples,
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        result = node.process(buffer)
        assert np.all(result.samples == 0.0)


# ============================================================================
# ClippingDetectorNode Tests
# ============================================================================


class TestClippingDetectorNode:
    """Tests for ClippingDetectorNode."""

    def test_detect_clipping(self, caplog):
        """Clipping should be detected and logged."""
        node = ClippingDetectorNode(threshold=0.95)

        samples = np.ones(100, dtype=np.float32)  # All samples at max
        buffer = AudioBuffer(
            samples=samples,
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        result = node.process(buffer)
        assert result is buffer  # Passes through
        assert "clipping" in caplog.text.lower()

    def test_no_clipping_below_threshold(self, caplog):
        """No clipping should be detected for normal signal."""
        node = ClippingDetectorNode(threshold=0.95)

        samples = np.random.randn(100).astype(np.float32) * 0.3
        buffer = AudioBuffer(
            samples=samples,
            timestamp=0.0,
            sample_rate=48000,
            channels=1,
            buffer_index=0,
        )

        node.process(buffer)
        assert "clipping" not in caplog.text.lower()
