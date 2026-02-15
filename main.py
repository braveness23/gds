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

import argparse
import logging
import signal
import sys
import time

from src.audio.audio_nodes import ALSASourceNode, FileSourceNode
from src.config.config import Config
from src.core.event_bus import EventBus, EventType
from src.core.logging_utils import setup_logging
from src.detection.detection_nodes import AubioOnsetNode, ThresholdDetectorNode
from src.output.mqtt_output import MQTTOutputNode
from src.sensors.gps import create_gps_reader
from src.sensors.static_gps import StaticGPSDevice

logger = logging.getLogger(__name__)


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

    def __init__(self, config_path: str = "config.yaml"):
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

        logger.info("Initializing gunshot detection system")
        logger.info(f"Config: {config_path}")

    def initialize(self) -> bool:
        """
        Initialize all components.

        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            logger.info("\nInitializing components...")

            # 1. Load configuration (if not already loaded by command-line args)
            if not self.config:
                self.config = Config(self.config_path)
                logger.info("  ✓ Configuration loaded")
            else:
                logger.info("  ✓ Using pre-configured settings")

            # 2. Initialize event bus
            self.event_bus = EventBus()
            self.event_bus.start()
            logger.info("  ✓ Event bus started")

            # Subscribe to events for local monitoring
            self.event_bus.subscribe(EventType.DETECTION, self._on_detection_event)
            self.event_bus.subscribe(EventType.SYSTEM, self._on_system_event)

            # 3. Initialize GPS reader if enabled
            gps_config = self.config.get("sensors.gps", {})
            if gps_config.get("enabled", True):
                gps_type = gps_config.get("type", "static")
                if gps_type == "static":
                    self.gps_reader = StaticGPSDevice(
                        latitude=gps_config.get("latitude", 0.0),
                        longitude=gps_config.get("longitude", 0.0),
                        altitude=gps_config.get("altitude", 0.0),
                    )
                    logger.info("  ✓ Static GPS initialized")
                else:
                    self.gps_reader = create_gps_reader(gps_config)
                    logger.info("  ✓ GPS reader initialized")
            else:
                logger.info("  - GPS disabled")

            # 4. Initialize MQTT output if enabled
            mqtt_config = self.config.get("output.mqtt", {})
            if mqtt_config.get("enabled", False):
                self.mqtt_output = MQTTOutputNode(
                    broker=mqtt_config.get("broker", "localhost"),
                    port=mqtt_config.get("port", 1883),
                    topic=mqtt_config.get("topic", "gunshot/detections"),
                    node_id=self.config.get("system.node_id", "unknown"),
                    qos=mqtt_config.get("qos", 1),
                    username=mqtt_config.get("username"),
                    password=mqtt_config.get("password"),
                    use_tls=mqtt_config.get("use_tls", False),
                    tls_ca_cert=mqtt_config.get("tls_ca_cert"),
                    tls_insecure=mqtt_config.get("tls_insecure", False),
                    event_bus=self.event_bus,
                    gps_reader=self.gps_reader,
                )
                self.mqtt_output.connect()
                logger.info("  ✓ MQTT output initialized")
            else:
                logger.info("  - MQTT disabled")

            # 5. Initialize audio source
            audio_config = self.config.get("audio", {})
            # Support both `source` and legacy `source_type` config keys
            source_type = audio_config.get("source") or audio_config.get(
                "source_type", "alsa"
            )

            if source_type == "alsa":
                self.audio_source = ALSASourceNode(
                    name="ALSASource",
                    device=audio_config.get("device", "default"),
                    sample_rate=audio_config.get("sample_rate", 48000),
                    channels=audio_config.get("channels", 1),
                    buffer_size=audio_config.get("buffer_size", 1024),
                    format_bits=audio_config.get("format_bits", 32),
                )
                logger.info("  ✓ ALSA audio source initialized")
            elif source_type == "file":
                # File source for test mode / replay
                self.audio_source = FileSourceNode(
                    name="FileSource",
                    filepath=audio_config.get("filepath"),
                    buffer_size=audio_config.get("buffer_size", 1024),
                    realtime=audio_config.get("realtime", True),
                    loop=audio_config.get("loop", False),
                )
                logger.info("  ✓ File audio source initialized")
            else:
                logger.error(f"  ! Unsupported audio source: {source_type}")
                return False

            # Wire audio source to detectors
            try:
                # Basic processing pipeline: send raw buffers to multiple detectors
                aubio_node = AubioOnsetNode(
                    method=self.config.get("detection.aubio.method", "complex"),
                    hop_size=self.config.get("detection.aubio.hop_size", 512),
                    threshold=self.config.get("detection.aubio.threshold", 0.3),
                    silence_threshold=self.config.get(
                        "detection.aubio.silence_threshold", -70.0
                    ),
                    event_bus=self.event_bus,
                    publish_min_interval_ms=self.config.get(
                        "detection.publish_min_interval_ms", 50.0
                    ),
                )
                thresh_node = ThresholdDetectorNode(
                    threshold_db=self.config.get(
                        "detection.threshold.threshold_db", -15.0
                    ),
                    min_duration_ms=self.config.get(
                        "detection.threshold.min_duration_ms", 10.0
                    ),
                    event_bus=self.event_bus,
                    publish_min_interval_ms=self.config.get(
                        "detection.publish_min_interval_ms", 50.0
                    ),
                )

                # Connect audio source to detectors
                self.audio_source.connect(aubio_node.receive)
                self.audio_source.connect(thresh_node.receive)
                logger.info("  ✓ Detection nodes connected to audio source")
            except Exception as e:
                logger.error(f"Failed to wire detection pipeline: {e}")

            logger.info("Initialization complete\n")
            return True

        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            import traceback

            traceback.print_exc()
            return False

    def start(self):
        """Start the detection system."""
        if self.running:
            logger.info("Already running")
            return

        logger.info(f"\n{'='*60}")
        logger.info("Starting Gunshot Detection System")
        logger.info(f"{'='*60}")

        self.running = True
        self.start_time = time.time()

        # Start audio source
        try:
            logger.info("Starting audio capture...")
            self.audio_source.start()
            logger.info("Audio capture started")
        except Exception as e:
            logger.error(f"Failed to start audio: {e}")
            self.stop()
            return

        logger.info(f"\n{'='*60}")
        logger.info("System Running")
        logger.info(f"{'='*60}")
        logger.info(f"Node ID: {self.config.get('system.node_id', 'unknown')}")
        logger.info(f"Audio source: {self.config.get('audio.source', 'unknown')}")

        if self.gps_reader:
            pos = self.gps_reader.get_position()
            if pos and pos.has_fix:
                logger.info(f"GPS: ({pos.latitude:.6f}, {pos.longitude:.6f})")
            else:
                logger.info("GPS: Waiting for fix...")

        if self.mqtt_output and self.mqtt_output.connected:
            logger.info(
                f"MQTT: Connected to {self.config.get('output.mqtt.broker', 'unknown')}"
            )

        logger.info("\nPress Ctrl+C to stop")
        logger.info(f"{'='*60}\n")

    def stop(self):
        """Stop the detection system."""
        if not self.running:
            return

        logger.info(f"\n{'='*60}")
        logger.info("Stopping Gunshot Detection System")
        logger.info(f"{'='*60}")

        self.running = False

        # Stop audio source
        if self.audio_source:
            logger.info("Stopping audio capture...")
            self.audio_source.stop()

        # Stop GPS
        if self.gps_reader:
            logger.info("Stopping GPS...")
            self.gps_reader.stop()

        # Disconnect MQTT
        if self.mqtt_output:
            logger.info("Disconnecting MQTT...")
            self.mqtt_output.disconnect()

        # Stop event bus
        if self.event_bus:
            logger.info("Stopping event bus...")
            self.event_bus.stop()

        # Print statistics
        if self.start_time:
            uptime = time.time() - self.start_time
            logger.info(f"\nUptime: {uptime:.1f}s")

        if self.event_bus:
            stats = self.event_bus.get_stats()
            logger.info(f"Events published: {stats['events_published']}")
            logger.info(f"Events dispatched: {stats['events_dispatched']}")

        logger.info("Shutdown complete")

    def run(self):
        """Run the detection system (blocking)."""
        if not self.initialize():
            logger.error("Initialization failed, exiting")
            return 1

        self.start()

        # Run until stopped
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\nInterrupted by user")

        self.stop()
        return 0

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"\nReceived signal {signum}")
        self.running = False

    def _on_detection_event(self, event):
        """Handle detection events (for logging/monitoring)."""
        # This is just for local logging
        # MQTT output will handle publishing to network
        logger.info(
            f"[Detection] {event.data.get('detector_type', 'unknown')} "
            f"at {event.timestamp:.6f}s "
            f"(confidence: {event.data.get('confidence', 0):.2f})"
        )

    def _on_system_event(self, event):
        """Handle system events (for logging/monitoring)."""
        # Could log important system events here
        pass


def main():
    """Main entry point."""
    # Configure logging early
    try:
        setup_logging()
    except Exception:
        logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description="Gunshot Detection System",
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
        """,
    )

    parser.add_argument(
        "--config",
        "-c",
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)",
    )

    parser.add_argument(
        "--test",
        "-t",
        metavar="AUDIOFILE",
        help="Test mode: process audio file instead of live capture",
    )

    parser.add_argument(
        "--no-mqtt", action="store_true", help="Disable MQTT output (local only)"
    )

    parser.add_argument(
        "--no-gps",
        action="store_true",
        help="Disable GPS (use static location from config)",
    )

    args = parser.parse_args()

    # Banner
    logger.info(
        """
╔════════════════════════════════════════════════════════════╗
║        Gunshot Detection System v1.0                       ║
║        Distributed Acoustic Event Detection                ║
╚════════════════════════════════════════════════════════════╝
    """
    )

    # Create system
    system = GunshotDetectionSystem(config_path=args.config)

    # Override config with command line args
    if args.test:
        logger.info(f"Test mode: processing file {args.test}")
        # Temporarily modify config for testing
        system.config = Config(args.config)
        system.config.set("audio.source", "file")
        system.config.set("audio.filepath", args.test)
        system.config.set("audio.realtime", False)

    if args.no_mqtt:
        logger.info("MQTT disabled (command line)")
        if not system.config:
            system.config = Config(args.config)
        system.config.set("output.mqtt.enabled", False)

    if args.no_gps:
        logger.info("GPS disabled (command line)")
        if not system.config:
            system.config = Config(args.config)
        system.config.set("sensors.gps.enabled", False)

    # Run system
    exit_code = system.run()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
