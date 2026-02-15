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
import sys
import os
import argparse
import yaml
import signal
import threading
import time
import logging
from src.core.logging_utils import setup_logging
from src.config.config import load_config
from src.core.event_bus import EventBus
from src.audio.audio_nodes import ALSASourceNode
from src.detection.detection_nodes import AubioOnsetNode, ThresholdDetectorNode
from src.sensors.gps import GPSDevice
from src.sensors.static_gps import StaticGPSDevice
from src.sensors.environmental import EnvironmentalSensor
from src.output.mqtt_output import MQTTOutputNode
from output.mqtt_output import MQTTOutputNode
from sensors.gps import create_gps_reader


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

            def main():
                setup_logging()
                logger = logging.getLogger("main")
                parser = argparse.ArgumentParser(description="Gunshot Detection System")
                parser.add_argument('-c', '--config', default='config.yaml', help='Path to config file')
                args = parser.parse_args()

                with open(args.config, 'r') as f:
                    config = yaml.safe_load(f)

                # Setup event bus
                event_bus = EventBus()

                # Setup audio source
                audio_cfg = config['audio']
                audio_source = ALSASourceNode(
                    name='mic',
                    device=audio_cfg.get('device', None),
                    sample_rate=audio_cfg.get('sample_rate', 16000),
                    channels=audio_cfg.get('channels', 1),
                    buffer_size=audio_cfg.get('buffer_size', 1024),
                    event_bus=event_bus
                )

                # Setup detection node
                detection_cfg = config['detection']
                onset_node = AubioOnsetNode(
                    name='onset',
                    method=detection_cfg.get('method', 'default'),
                    threshold=detection_cfg.get('threshold', 0.1),
                    event_bus=event_bus
                )

                # Setup output node
                output_cfg = config['output']
                mqtt_output = MQTTOutputNode(
                    name='mqtt',
                    host=output_cfg.get('host', 'localhost'),
                    port=output_cfg.get('port', 1883),
                    topic=output_cfg.get('topic', 'gds/detections'),
                    event_bus=event_bus
                )

                # Setup GPS device
                gps_cfg = config['gps']
                if gps_cfg.get('type', 'static') == 'static':
                    gps_device = StaticGPSDevice(
                        lat=gps_cfg.get('lat', 0.0),
                        lon=gps_cfg.get('lon', 0.0),
                        alt=gps_cfg.get('alt', 0.0)
                    )
                else:
                    gps_device = GPSDevice(
                        port=gps_cfg.get('port', '/dev/ttyUSB0'),
                        baudrate=gps_cfg.get('baudrate', 9600)
                    )

                # Setup environmental sensor
                env_cfg = config.get('environmental', {})
                env_sensor = None
                if env_cfg.get('enabled', False):
                    env_sensor = EnvironmentalSensor(
                        i2c_bus=env_cfg.get('i2c_bus', 1),
                        event_bus=event_bus
                    )

                # Register event handlers
                def on_detection(event):
                    logger.info(f"Detection event: {event}")

                event_bus.subscribe('detection', on_detection)

                # Start nodes
                audio_source.start()
                onset_node.start()
                mqtt_output.start()
                if env_sensor:
                    env_sensor.start()

                logger.info("System running. Press Ctrl+C to exit.")
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    logger.info("Shutting down...")
                finally:
                    audio_source.stop()
                    onset_node.stop()
                    mqtt_output.stop()
                    if env_sensor:
                        env_sensor.stop()

            if __name__ == "__main__":
                main()
                device=audio_config.get('device', 'default'),
                sample_rate=audio_config.get('sample_rate', 48000),
                channels=audio_config.get('channels', 1),
                buffer_size=audio_config.get('buffer_size', 1024),
                format_bits=audio_config.get('format_bits', 32)
            )
        elif source_type == 'file':
            self.audio_source = FileSourceNode(
                name="FileSource",
                filepath=audio_config.get('filepath'),
                buffer_size=audio_config.get('buffer_size', 1024),
                realtime=audio_config.get('realtime', True),
                loop=audio_config.get('loop', False)
            )
        else:
            raise ValueError(f"Unknown audio source type: {source_type}")

        print(f"  Audio source: {source_type}")

        # 2. Build processing chain
        current_node = self.audio_source

        # Mono conversion (if needed)
        if audio_config.get('channels', 1) > 1:
            mono_node = MonoConversionNode()
            current_node.connect(mono_node.receive)
            self.pipeline_nodes.append(mono_node)
            current_node = mono_node
            print(f"  + Mono conversion")

        # DC removal (optional)
        if processing_config.get('dc_removal.enabled', False):
            dc_node = DCRemovalNode(
                cutoff_freq=processing_config.get('dc_removal.cutoff', 5.0)
            )
            current_node.connect(dc_node.receive)
            self.pipeline_nodes.append(dc_node)
            current_node = dc_node
            print(f"  + DC removal")

        # High-pass filter
        if processing_config.get('highpass.enabled', True):
            hpf_node = HighPassFilterNode(
                cutoff_freq=processing_config.get('highpass.cutoff', 5000),
                order=processing_config.get('highpass.order', 4),
                filter_type=processing_config.get('highpass.type', 'butterworth')
            )
            current_node.connect(hpf_node.receive)
            self.pipeline_nodes.append(hpf_node)
            current_node = hpf_node
            print(f"  + High-pass filter ({processing_config.get('highpass.cutoff', 5000)}Hz)")

        # Gain (optional)
        gain_db = processing_config.get('gain.db', 0.0)
        if gain_db != 0.0:
            gain_node = GainNode(gain_db=gain_db)
            current_node.connect(gain_node.receive)
            self.pipeline_nodes.append(gain_node)
            current_node = gain_node
            print(f"  + Gain ({gain_db}dB)")

        # 3. Create splitter for multiple detectors
        splitter = BufferSplitterNode()
        current_node.connect(splitter.receive)
        self.pipeline_nodes.append(splitter)
        print(f"  + Splitter (for parallel detection)")

        # 4. Create detectors
        detector_count = 0

        # Aubio detector
        if detection_config.get('aubio.enabled', True):
            aubio_node = AubioOnsetNode(
                name="Aubio",
                method=detection_config.get('aubio.method', 'complex'),
                hop_size=detection_config.get('aubio.hop_size', 512),
                threshold=detection_config.get('aubio.threshold', 0.3),
                silence_threshold=detection_config.get('aubio.silence_threshold', -70.0),
                event_bus=self.event_bus
            )
            splitter.connect(aubio_node.receive)
            self.pipeline_nodes.append(aubio_node)
            detector_count += 1
            print(f"  + Aubio detector ({detection_config.get('aubio.method', 'complex')})")

        # Threshold detector
        if detection_config.get('threshold.enabled', False):
            threshold_node = ThresholdDetectorNode(
                name="Threshold",
                threshold_db=detection_config.get('threshold.threshold_db', -20.0),
                min_duration_ms=detection_config.get('threshold.min_duration_ms', 10.0),
                event_bus=self.event_bus
            )
            splitter.connect(threshold_node.receive)
            self.pipeline_nodes.append(threshold_node)
            detector_count += 1
            print(f"  + Threshold detector ({detection_config.get('threshold.threshold_db', -20.0)}dB)")

        if detector_count == 0:
            print(f"  WARNING: No detectors enabled!")

        print(f"[System] Pipeline built with {len(self.pipeline_nodes)} nodes")

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
