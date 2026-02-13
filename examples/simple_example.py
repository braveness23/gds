#!/usr/bin/env python3
"""
Simple example demonstrating the gunshot detection pipeline.

This example shows how to connect audio source → processing → detection.
"""

import sys
import time
import signal
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from core.event_bus import get_event_bus, EventType
from audio.audio_nodes import FileSourceNode, ALSASourceNode
from processing.processing_nodes import MonoConversionNode, HighPassFilterNode
from detection.detection_nodes import AubioOnsetNode, ThresholdDetectorNode


def simple_file_example():
    """
    Simple example using a file source.
    
    Usage:
        python simple_example.py test.wav
    """
    if len(sys.argv) < 2:
        print("Usage: python simple_example.py <audio_file>")
        print("Example: python simple_example.py test_gunshot.wav")
        sys.exit(1)
    
    audio_file = sys.argv[1]
    
    # Get event bus
    event_bus = get_event_bus()
    
    # Track detections
    detections = []
    def on_detection(event):
        detections.append(event)
        print(f"\n🎯 DETECTION: {event.data['detector_type']} at {event.timestamp:.3f}s "
              f"(confidence: {event.data['confidence']:.2f})")
    
    event_bus.subscribe(EventType.DETECTION, on_detection)
    
    print("=" * 60)
    print("Simple Gunshot Detection Example")
    print("=" * 60)
    print(f"Audio file: {audio_file}")
    print()
    
    # Create pipeline
    print("Building pipeline...")
    
    # Source
    source = FileSourceNode(
        filepath=audio_file,
        buffer_size=1024,
        realtime=True  # Simulate real-time processing
    )
    
    # Processing
    mono = MonoConversionNode()
    hpf = HighPassFilterNode(cutoff_freq=5000, order=4)
    
    # Detection
    aubio = AubioOnsetNode(
        method='complex',
        hop_size=512,
        threshold=0.3,
        event_bus=event_bus
    )
    
    # Connect pipeline
    source.connect(mono.receive)
    mono.connect(hpf.receive)
    hpf.connect(aubio.receive)
    
    print("Pipeline: FileSource → Mono → HPF(5kHz) → Aubio")
    print()
    
    # Run
    print("Processing audio...")
    source.start()
    
    # Wait for completion
    while source.running:
        time.sleep(0.1)
    
    # Summary
    print()
    print("=" * 60)
    print(f"Processing complete!")
    print(f"Total detections: {len(detections)}")
    print("=" * 60)


def simple_microphone_example():
    """
    Simple example using microphone input.
    
    Usage:
        python simple_example.py mic
    """
    # Get event bus
    event_bus = get_event_bus()
    
    # Track detections
    def on_detection(event):
        print(f"\n🎯 DETECTION: {event.data['detector_type']} at {event.timestamp:.3f}s "
              f"(confidence: {event.data['confidence']:.2f})")
    
    event_bus.subscribe(EventType.DETECTION, on_detection)
    
    print("=" * 60)
    print("Live Microphone Detection Example")
    print("=" * 60)
    print("Make a loud sound (clap, knock, etc.) to test detection")
    print("Press Ctrl+C to stop")
    print()
    
    # Create pipeline
    print("Building pipeline...")
    
    # Source (use default ALSA device)
    source = ALSASourceNode(
        device="default",
        sample_rate=48000,
        channels=1,
        buffer_size=1024
    )
    
    # Processing
    mono = MonoConversionNode()
    hpf = HighPassFilterNode(cutoff_freq=5000, order=4)
    
    # Detection (use both Aubio and threshold)
    aubio = AubioOnsetNode(
        method='complex',
        hop_size=512,
        threshold=0.3,
        event_bus=event_bus
    )
    
    threshold = ThresholdDetectorNode(
        threshold_db=-15,
        min_duration_ms=10,
        event_bus=event_bus
    )
    
    # Connect pipeline with splitter for parallel detection
    source.connect(mono.receive)
    mono.connect(hpf.receive)
    
    # Split to both detectors
    hpf.connect(aubio.receive)
    hpf.connect(threshold.receive)
    
    print("Pipeline: ALSA → Mono → HPF(5kHz) → [Aubio, Threshold]")
    print()
    
    # Set up signal handler for clean shutdown
    def signal_handler(sig, frame):
        print("\n\nStopping...")
        source.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run
    print("Listening... (Ctrl+C to stop)")
    print()
    source.start()
    
    # Keep running
    try:
        while source.running:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\nStopping...")
        source.stop()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "mic":
        simple_microphone_example()
    else:
        simple_file_example()
