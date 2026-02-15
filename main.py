#!/usr/bin/env python3
"""
Main application orchestrator for gunshot detection system.

This is the primary entry point that:
- Loads configuration
- Initializes all components
- Builds the processing pipeline
- Manages lifecycle (start/stop)
- Handles signals for graceful shutdown
"""

import sys
import time
import os
import argparse
import yaml
import signal
import threading
import logging
from src.core.logging_utils import setup_logging
from src.config.config import Config
from src.core.event_bus import EventBus, EventType
from src.audio.audio_nodes import ALSASourceNode
from src.detection.detection_nodes import AubioOnsetNode, ThresholdDetectorNode
from src.sensors.gps import GPSReader, create_gps_reader
from src.sensors.static_gps import StaticGPSDevice
from src.sensors.environmental import BME280Sensor, DHTSensor, create_environmental_sensor
from src.output.mqtt_output import MQTTOutputNode


class GunshotDetectionSystem:
    """
    Main orchestrator for the gunshot detection system.

    Responsibilities:
    - Load configuration
    - Initialize all components
    - Build processing pipeline
    - Start/stop all services
    - Handle graceful shutdown
    """

    def __init__(self, config_path: str = 'config.yaml'):
        """
        Initialize the detection system.

        Args:
            config_path: Path to configuration file
        """
        self.config_path = config_path
        self.config = None
        self.event_bus = None

        # Components (initialized later)
        self.audio_source = None
        self.gps_reader = None
        self.mqtt_output = None
        self.pipeline_nodes = []

        # State
        self.running = False
        self.start_time = None

        # Signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        print(f"[System] Initializing gunshot detection system")
        print(f"[System] Config: {config_path}")

    def initialize(self) -> bool:
        """
        Initialize all components.

        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            print(f"\n[System] Initializing components...")

            # 1. Load configuration (if not already loaded by command-line args)
            if not self.config:
                self.config = Config(self.config_path)
                print(f"  ✓ Configuration loaded")
            else:
                print(f"  ✓ Using pre-configured settings")

            # 2. Initialize event bus
            self.event_bus = EventBus()
            self.event_bus.start()
            print(f"  ✓ Event bus started")

            # Subscribe to events for local monitoring
            self.event_bus.subscribe(EventType.DETECTION, self._on_detection_event)
            self.event_bus.subscribe(EventType.SYSTEM, self._on_system_event)

            # 3. Initialize GPS reader if enabled
            gps_config = self.config.get('sensors.gps', {})
            if gps_config.get('enabled', True):
                gps_type = gps_config.get('type', 'static')
                if gps_type == 'static':
                    self.gps_reader = StaticGPSDevice(
                        latitude=gps_config.get('latitude', 0.0),
                        longitude=gps_config.get('longitude', 0.0),
                        altitude=gps_config.get('altitude', 0.0)
                    )
                    print(f"  ✓ Static GPS initialized")
                else:
                    self.gps_reader = create_gps_reader(gps_config)
                    print(f"  ✓ GPS reader initialized")
            else:
                print(f"  - GPS disabled")

            # 4. Initialize MQTT output if enabled
            mqtt_config = self.config.get('output.mqtt', {})
            if mqtt_config.get('enabled', False):
                self.mqtt_output = MQTTOutputNode(
                    broker=mqtt_config.get('broker', 'localhost'),
                    port=mqtt_config.get('port', 1883),
                    topic=mqtt_config.get('topic', 'gunshot/detections'),
                    node_id=self.config.get('system.node_id', 'unknown'),
                    qos=mqtt_config.get('qos', 1),
                    username=mqtt_config.get('username'),
                    password=mqtt_config.get('password'),
                    use_tls=mqtt_config.get('use_tls', False),
                    event_bus=self.event_bus,
                    gps_reader=self.gps_reader
                )
                self.mqtt_output.connect()
                print(f"  ✓ MQTT output initialized")
            else:
                print(f"  - MQTT disabled")

            # 5. Initialize audio source
            audio_config = self.config.get('audio', {})
            source_type = audio_config.get('source', 'alsa')

            if source_type == 'alsa':
                self.audio_source = ALSASourceNode(
                    name="ALSASource",
                    device=audio_config.get('device', 'default'),
                    sample_rate=audio_config.get('sample_rate', 48000),
                    channels=audio_config.get('channels', 1),
                    buffer_size=audio_config.get('buffer_size', 1024),
                    format_bits=audio_config.get('format_bits', 32)
                )
                print(f"  ✓ ALSA audio source initialized")
            else:
                print(f"  ! Unsupported audio source: {source_type}")
                return False

            print(f"[System] Initialization complete\n")
            return True

        except Exception as e:
            print(f"[System] Initialization failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def start(self):
        """Start the detection system."""
        if self.running:
            print(f"[System] Already running")
            return

        print(f"\n{'='*60}")
        print(f"Starting Gunshot Detection System")
        print(f"{'='*60}")

        self.running = True
        self.start_time = time.time()

        # Start audio source
        try:
            print(f"[System] Starting audio capture...")
            self.audio_source.start()
            print(f"[System] Audio capture started")
        except Exception as e:
            print(f"[System] Failed to start audio: {e}")
            self.stop()
            return

        print(f"\n{'='*60}")
        print(f"System Running")
        print(f"{'='*60}")
        print(f"Node ID: {self.config.get('system.node_id', 'unknown')}")
        print(f"Audio source: {self.config.get('audio.source', 'unknown')}")

        if self.gps_reader:
            pos = self.gps_reader.get_position()
            if pos and pos.has_fix:
                print(f"GPS: ({pos.latitude:.6f}, {pos.longitude:.6f})")
            else:
                print(f"GPS: Waiting for fix...")

        if self.mqtt_output and self.mqtt_output.connected:
            print(f"MQTT: Connected to {self.config.get('output.mqtt.broker', 'unknown')}")

        print(f"\nPress Ctrl+C to stop")
        print(f"{'='*60}\n")

    def stop(self):
        """Stop the detection system."""
        if not self.running:
            return

        print(f"\n{'='*60}")
        print(f"Stopping Gunshot Detection System")
        print(f"{'='*60}")

        self.running = False

        # Stop audio source
        if self.audio_source:
            print(f"[System] Stopping audio capture...")
            self.audio_source.stop()

        # Stop GPS
        if self.gps_reader:
            print(f"[System] Stopping GPS...")
            self.gps_reader.stop()

        # Disconnect MQTT
        if self.mqtt_output:
            print(f"[System] Disconnecting MQTT...")
            self.mqtt_output.disconnect()

        # Stop event bus
        if self.event_bus:
            print(f"[System] Stopping event bus...")
            self.event_bus.stop()

        # Print statistics
        if self.start_time:
            uptime = time.time() - self.start_time
            print(f"\n[System] Uptime: {uptime:.1f}s")

        if self.event_bus:
            stats = self.event_bus.get_stats()
            print(f"[System] Events published: {stats['events_published']}")
            print(f"[System] Events dispatched: {stats['events_dispatched']}")

        print(f"[System] Shutdown complete")

    def run(self):
        """Run the detection system (blocking)."""
        if not self.initialize():
            print(f"[System] Initialization failed, exiting")
            return 1

        self.start()

        # Run until stopped
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print(f"\n[System] Interrupted by user")

        self.stop()
        return 0

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        print(f"\n[System] Received signal {signum}")
        self.running = False

    def _on_detection_event(self, event):
        """Handle detection events (for logging/monitoring)."""
        # This is just for local logging
        # MQTT output will handle publishing to network
        print(f"[Detection] {event.data.get('detector_type', 'unknown')} "
              f"at {event.timestamp:.6f}s "
              f"(confidence: {event.data.get('confidence', 0):.2f})")

    def _on_system_event(self, event):
        """Handle system events (for logging/monitoring)."""
        # Could log important system events here
        pass


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Gunshot Detection System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default config
  python main.py

  # Run with custom config
  python main.py --config /path/to/config.yaml

  # Test mode (file input)
  python main.py --test test_audio.wav

Configuration:
  Edit config.yaml to customize:
  - Audio source (ALSA device, file)
  - Detection parameters (sensitivity, filters)
  - GPS settings
  - MQTT broker
  - Node ID and location
        """
    )

    parser.add_argument(
        '--config', '-c',
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )

    parser.add_argument(
        '--test', '-t',
        metavar='AUDIOFILE',
        help='Test mode: process audio file instead of live capture'
    )

    parser.add_argument(
        '--no-mqtt',
        action='store_true',
        help='Disable MQTT output (local only)'
    )

    parser.add_argument(
        '--no-gps',
        action='store_true',
        help='Disable GPS (use static location from config)'
    )

    args = parser.parse_args()

    # Print banner
    print("""
╔════════════════════════════════════════════════════════════╗
║        Gunshot Detection System v1.0                       ║
║        Distributed Acoustic Event Detection                ║
╚════════════════════════════════════════════════════════════╝
    """)

    # Create system
    system = GunshotDetectionSystem(config_path=args.config)

    # Override config with command line args
    if args.test:
        print(f"[System] Test mode: processing file {args.test}")
        # Temporarily modify config for testing
        system.config = Config(args.config)
        system.config.set('audio.source', 'file')
        system.config.set('audio.filepath', args.test)
        system.config.set('audio.realtime', False)

    if args.no_mqtt:
        print(f"[System] MQTT disabled (command line)")
        if not system.config:
            system.config = Config(args.config)
        system.config.set('output.mqtt.enabled', False)

    if args.no_gps:
        print(f"[System] GPS disabled (command line)")
        if not system.config:
            system.config = Config(args.config)
        system.config.set('sensors.gps.enabled', False)

    # Run system
    exit_code = system.run()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
