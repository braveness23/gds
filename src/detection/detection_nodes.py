"""Detection nodes for identifying acoustic events.

This module provides various detection algorithms for gunshot/onset detection.
"""

import numpy as np
from typing import Optional, Dict
from audio.audio_nodes import AudioNode, AudioBuffer
from core.event_bus import Event, EventType


class DetectionEvent:
    """Detection event with metadata."""
    
    def __init__(self,
                 timestamp: float,
                 confidence: float,
                 detector_type: str,
                 buffer_index: int,
                 metadata: Optional[Dict] = None):
        self.timestamp = timestamp
        self.confidence = confidence
        self.detector_type = detector_type
        self.buffer_index = buffer_index
        self.metadata = metadata or {}


class AubioOnsetNode(AudioNode):
    """Aubio-based onset detection for fast gunshot detection.
    
    Uses aubio's onset detection which works great for transient events
    like gunshots. The 'complex' method is best for sharp attacks.
    """
    
    def __init__(self,
                 name: str = "AubioOnset",
                 method: str = 'complex',
                 hop_size: int = 512,
                 threshold: float = 0.3,
                 silence_threshold: float = -70.0,
                 event_bus=None):
        super().__init__(name)
        self.method = method
        self.hop_size = hop_size
        self.threshold = threshold
        self.silence_threshold = silence_threshold
        self.event_bus = event_bus
        
        self.onset_detector = None
        self.sample_rate = None
        
        # For accumulating samples across buffers
        self.residual_samples = np.array([], dtype=np.float32)
    
    def _init_detector(self, sample_rate: int):
        """Initialize aubio onset detector."""
        if self.sample_rate == sample_rate and self.onset_detector is not None:
            return
        
        try:
            import aubio
        except ImportError:
            raise ImportError("aubio not installed. Run: pip install aubio")
        
        self.sample_rate = sample_rate
        
        # Window size should be power of 2 and >= hop_size
        win_size = self.hop_size * 2
        
        self.onset_detector = aubio.onset(
            method=self.method,
            buf_size=win_size,
            hop_size=self.hop_size,
            samplerate=sample_rate
        )
        
        self.onset_detector.set_threshold(self.threshold)
        self.onset_detector.set_silence(self.silence_threshold)
        
        print(f"[{self.name}] Initialized aubio onset detector: "
              f"method={self.method}, hop={self.hop_size}, "
              f"threshold={self.threshold}, silence={self.silence_threshold}dB")
    
    def process(self, buffer: AudioBuffer) -> Optional[AudioBuffer]:
        """Detect onsets in buffer and emit detection events."""
        # Initialize detector on first buffer
        if self.onset_detector is None:
            self._init_detector(buffer.sample_rate)
        
        # Ensure mono
        samples = buffer.samples if buffer.is_mono else np.mean(buffer.samples, axis=1)
        
        # Combine with residual from previous buffer
        if len(self.residual_samples) > 0:
            samples = np.concatenate([self.residual_samples, samples])
            base_offset = -len(self.residual_samples)
        else:
            base_offset = 0
        
        # Process in hop_size chunks
        detections = []
        sample_index = 0
        
        while sample_index + self.hop_size <= len(samples):
            chunk = samples[sample_index:sample_index + self.hop_size]
            
            # Convert to aubio format (float32)
            chunk_float = chunk.astype(np.float32)
            
            # Detect onset
            is_onset = self.onset_detector(chunk_float)
            
            if is_onset:
                # Calculate precise timestamp of onset within buffer
                sample_offset = sample_index + base_offset
                time_offset = sample_offset / buffer.sample_rate
                onset_timestamp = buffer.timestamp + time_offset
                
                detection = DetectionEvent(
                    timestamp=onset_timestamp,
                    confidence=1.0,  # Aubio doesn't provide confidence
                    detector_type=f"aubio_{self.method}",
                    buffer_index=buffer.buffer_index,
                    metadata={
                        'method': self.method,
                        'sample_offset': sample_offset,
                        'threshold': self.threshold
                    }
                )
                
                detections.append(detection)
                
                # Log detection
                print(f"[{self.name}] Onset detected at {onset_timestamp:.6f}s "
                      f"(buffer {buffer.buffer_index}, offset {sample_offset})")
            
            sample_index += self.hop_size
        
        # Save residual for next buffer
        self.residual_samples = samples[sample_index:]
        
        # Publish detection events to event bus
        if self.event_bus:
            for detection in detections:
                self._publish_detection(detection)
        
        # Pass through original buffer unchanged
        return buffer
    
    def _publish_detection(self, detection: DetectionEvent):
        """Publish detection event to event bus."""
        event = Event(
            event_type=EventType.DETECTION,
            timestamp=detection.timestamp,
            source=self.name,
            data={
                'confidence': detection.confidence,
                'detector_type': detection.detector_type,
                'buffer_index': detection.buffer_index,
                'metadata': detection.metadata
            }
        )
        self.event_bus.publish(event)


class ThresholdDetectorNode(AudioNode):
    """Simple amplitude threshold detector.
    
    Fast, low-complexity detector for basic onset detection.
    Good as a fallback or for validation.
    """
    
    def __init__(self,
                 name: str = "ThresholdDetector",
                 threshold_db: float = -20.0,
                 min_duration_ms: float = 10.0,
                 event_bus=None):
        super().__init__(name)
        self.threshold_db = threshold_db
        self.threshold_linear = 10.0 ** (threshold_db / 20.0)
        self.min_duration_ms = min_duration_ms
        self.event_bus = event_bus
        
        self.min_duration_samples = 0
        self.in_event = False
        self.event_start_timestamp = None
        self.event_start_sample = None
        self.event_peak = 0.0
    
    def process(self, buffer: AudioBuffer) -> Optional[AudioBuffer]:
        """Detect amplitude threshold crossings."""
        # Update min_duration in samples
        if self.min_duration_samples == 0:
            self.min_duration_samples = int(
                (self.min_duration_ms / 1000.0) * buffer.sample_rate
            )
        
        # Get mono samples
        samples = buffer.samples if buffer.is_mono else np.mean(buffer.samples, axis=1)
        
        # Find threshold crossings
        above_threshold = np.abs(samples) > self.threshold_linear
        
        for i, is_above in enumerate(above_threshold):
            time_offset = i / buffer.sample_rate
            current_timestamp = buffer.timestamp + time_offset
            
            if is_above:
                peak_value = abs(samples[i])
                
                if not self.in_event:
                    # Event start
                    self.in_event = True
                    self.event_start_timestamp = current_timestamp
                    self.event_start_sample = i
                    self.event_peak = peak_value
                else:
                    # Update peak
                    if peak_value > self.event_peak:
                        self.event_peak = peak_value
            
            elif self.in_event:
                # Event end - check duration
                event_duration_samples = i - self.event_start_sample
                
                if event_duration_samples >= self.min_duration_samples:
                    # Valid detection
                    detection = DetectionEvent(
                        timestamp=self.event_start_timestamp,
                        confidence=min(self.event_peak, 1.0),
                        detector_type="threshold",
                        buffer_index=buffer.buffer_index,
                        metadata={
                            'threshold_db': self.threshold_db,
                            'peak_amplitude': float(self.event_peak),
                            'duration_samples': event_duration_samples,
                            'duration_ms': (event_duration_samples / buffer.sample_rate) * 1000
                        }
                    )
                    
                    print(f"[{self.name}] Detection at {self.event_start_timestamp:.6f}s "
                          f"(peak: {self.event_peak:.3f}, duration: {event_duration_samples} samples)")
                    
                    if self.event_bus:
                        self._publish_detection(detection)
                
                # Reset
                self.in_event = False
                self.event_peak = 0.0
        
        # Handle event continuing to next buffer
        if self.in_event:
            # Event continues, will finish in next buffer
            self.event_start_sample = 0
        
        return buffer
    
    def _publish_detection(self, detection: DetectionEvent):
        """Publish detection event to event bus."""
        event = Event(
            event_type=EventType.DETECTION,
            timestamp=detection.timestamp,
            source=self.name,
            data={
                'confidence': detection.confidence,
                'detector_type': detection.detector_type,
                'buffer_index': detection.buffer_index,
                'metadata': detection.metadata
            }
        )
        self.event_bus.publish(event)


class MLGunShotDetectorNode(AudioNode):
    """Machine learning based gunshot classifier.
    
    This is a stub implementation ready for PyTorch/TensorFlow models.
    Train your own model or use a pre-trained one.
    """
    
    def __init__(self,
                 name: str = "MLDetector",
                 model_path: Optional[str] = None,
                 window_size: int = 4096,
                 hop_size: int = 2048,
                 confidence_threshold: float = 0.7,
                 event_bus=None):
        super().__init__(name)
        self.model_path = model_path
        self.window_size = window_size
        self.hop_size = hop_size
        self.confidence_threshold = confidence_threshold
        self.event_bus = event_bus
        
        self.model = None
        self.sample_buffer = np.array([], dtype=np.float32)
        
        if model_path:
            self._load_model()
    
    def _load_model(self):
        """Load ML model - implement based on your framework."""
        print(f"[{self.name}] ML model loading not implemented")
        print(f"[{self.name}] To implement, uncomment the appropriate code:")
        print(f"  - PyTorch: torch.load('{self.model_path}')")
        print(f"  - TensorFlow: tf.keras.models.load_model('{self.model_path}')")
        
        # Example PyTorch implementation:
        # import torch
        # self.model = torch.load(self.model_path)
        # self.model.eval()
        
        # Example TensorFlow implementation:
        # import tensorflow as tf
        # self.model = tf.keras.models.load_model(self.model_path)
    
    def process(self, buffer: AudioBuffer) -> Optional[AudioBuffer]:
        """Run ML inference on audio buffer."""
        if self.model is None:
            # No model loaded, just pass through
            return buffer
        
        # Get mono samples
        samples = buffer.samples if buffer.is_mono else np.mean(buffer.samples, axis=1)
        
        # Accumulate samples
        self.sample_buffer = np.concatenate([self.sample_buffer, samples])
        
        # Process windows
        while len(self.sample_buffer) >= self.window_size:
            window = self.sample_buffer[:self.window_size]
            
            # Classify window
            prediction = self._classify_window(window)
            
            if prediction['confidence'] > self.confidence_threshold:
                # Calculate timestamp at window center
                center_sample = self.window_size // 2
                time_offset = center_sample / buffer.sample_rate
                detection_timestamp = buffer.timestamp + time_offset
                
                detection = DetectionEvent(
                    timestamp=detection_timestamp,
                    confidence=prediction['confidence'],
                    detector_type=f"ml_{prediction['class']}",
                    buffer_index=buffer.buffer_index,
                    metadata=prediction.get('metadata', {})
                )
                
                print(f"[{self.name}] {prediction['class']} detected at "
                      f"{detection_timestamp:.6f}s (confidence: {prediction['confidence']:.2f})")
                
                if self.event_bus:
                    self._publish_detection(detection)
            
            # Slide window by hop_size
            self.sample_buffer = self.sample_buffer[self.hop_size:]
        
        return buffer
    
    def _classify_window(self, window: np.ndarray) -> Dict:
        """Run ML model on window - IMPLEMENT WITH YOUR MODEL."""
        # This is a stub implementation
        # Replace with your actual model inference
        
        # Example PyTorch implementation:
        # import torch
        # with torch.no_grad():
        #     features = self._extract_features(window)
        #     output = self.model(features)
        #     probabilities = torch.softmax(output, dim=1)
        #     confidence, class_idx = torch.max(probabilities, dim=1)
        #     return {
        #         'class': ['noise', 'gunshot'][class_idx.item()],
        #         'confidence': confidence.item(),
        #         'metadata': {}
        #     }
        
        # Stub: return low confidence so it doesn't trigger
        return {
            'class': 'unknown',
            'confidence': 0.0,
            'metadata': {'note': 'ML model not implemented'}
        }
    
    def _extract_features(self, window: np.ndarray) -> np.ndarray:
        """Extract features from audio window.
        
        Common approaches:
        - MFCC (Mel-frequency cepstral coefficients)
        - Mel spectrogram
        - Raw waveform (for CNNs)
        - Chromagram
        """
        # Example: Compute MFCC using librosa
        # import librosa
        # mfcc = librosa.feature.mfcc(y=window, sr=self.sample_rate, n_mfcc=13)
        # return mfcc
        
        return window  # Stub: return raw waveform
    
    def _publish_detection(self, detection: DetectionEvent):
        """Publish detection event to event bus."""
        event = Event(
            event_type=EventType.DETECTION,
            timestamp=detection.timestamp,
            source=self.name,
            data={
                'confidence': detection.confidence,
                'detector_type': detection.detector_type,
                'buffer_index': detection.buffer_index,
                'metadata': detection.metadata
            }
        )
        self.event_bus.publish(event)
