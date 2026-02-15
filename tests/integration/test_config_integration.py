"""Integration tests for configuration and system initialization."""

import tempfile
from pathlib import Path

import yaml

from src.config.config import Config


class TestConfigurationIntegration:
    """Test configuration integration with system components."""

    def test_load_full_config_yaml(self):
        """Test loading a complete configuration file."""
        config_data = {
            "system": {"node_id": "integration_test_001", "log_level": "DEBUG"},
            "audio": {
                "source": "alsa",
                "device": "hw:0",
                "sample_rate": 48000,
                "channels": 1,
                "buffer_size": 1024,
            },
            "processing": {
                "dc_removal": {"enabled": True, "cutoff": 5.0},
                "highpass": {"enabled": True, "cutoff": 5000, "order": 4},
                "gain": {"db": 0.0},
            },
            "detection": {
                "aubio": {"enabled": True, "method": "complex", "threshold": 0.3},
                "threshold": {"enabled": True, "threshold_db": -15.0},
            },
            "sensors": {"gps": {"enabled": False, "host": "localhost", "port": 2947}},
            "output": {
                "mqtt": {
                    "enabled": True,
                    "broker": "mqtt.example.com",
                    "port": 8883,
                    "topic": "gunshot/detections",
                    "username": "test_user",
                    "use_tls": True,
                }
            },
        }

        # Write to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            config = Config(temp_path)

            # Verify all sections loaded
            assert config.get("system.node_id") == "integration_test_001"
            assert config.get("audio.sample_rate") == 48000
            assert config.get("processing.highpass.cutoff") == 5000
            assert config.get("detection.aubio.enabled") is True
            assert config.get("sensors.gps.enabled") is False
            assert config.get("output.mqtt.broker") == "mqtt.example.com"

        finally:
            Path(temp_path).unlink()

    def test_config_with_environment_overrides(self):
        """Test configuration with environment-specific overrides."""
        base_config = {
            "system": {"node_id": "base_node"},
            "audio": {"sample_rate": 44100},
        }

        # Write base config
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(base_config, f)
            temp_path = f.name

        try:
            config = Config(temp_path)

            # Override at runtime
            config.set("system.node_id", "production_node_001")
            config.set("audio.sample_rate", 48000)

            assert config.get("system.node_id") == "production_node_001"
            assert config.get("audio.sample_rate") == 48000

        finally:
            Path(temp_path).unlink()

    def test_config_validates_required_fields(self):
        """Test configuration validation for required fields."""
        config = Config()

        # Should have required system fields
        assert config.get("system.node_id") is not None
        assert config.get("audio.sample_rate") is not None
        assert config.get("audio.buffer_size") is not None

    def test_config_with_partial_sections(self):
        """Test loading config with only some sections defined."""
        partial_config = {
            "system": {"node_id": "partial_test"},
            "detection": {"aubio": {"threshold": 0.5}},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(partial_config, f)
            temp_path = f.name

        try:
            config = Config(temp_path)

            # Overridden value
            assert config.get("detection.aubio.threshold") == 0.5

            # Default values still present
            assert config.get("audio.sample_rate") == 48000
            assert config.get("audio.buffer_size") == 1024

        finally:
            Path(temp_path).unlink()

    def test_initialize_components_from_config(self, event_bus):
        """Test initializing system components from configuration."""
        config = Config()
        config.set("system.node_id", "test_node_123")
        config.set("audio.sample_rate", 48000)
        config.set("audio.buffer_size", 1024)
        config.set("detection.threshold.enabled", True)
        config.set("detection.threshold.threshold_db", -18.0)

        # Initialize components based on config
        node_id = config.get("system.node_id")
        sample_rate = config.get("audio.sample_rate")

        assert node_id == "test_node_123"
        assert sample_rate == 48000

        # Would initialize detector with these settings
        if config.get("detection.threshold.enabled"):
            threshold = config.get("detection.threshold.threshold_db")
            assert threshold == -18.0

    def test_mqtt_config_extraction(self):
        """Test extracting MQTT configuration for initialization."""
        config = Config()
        config.set("output.mqtt.enabled", True)
        config.set("output.mqtt.broker", "mqtt.test.com")
        config.set("output.mqtt.port", 8883)
        config.set("output.mqtt.topic", "test/topic")
        config.set("output.mqtt.qos", 2)
        config.set("output.mqtt.use_tls", True)
        config.set("output.mqtt.username", "testuser")
        config.set("output.mqtt.password", "testpass")

        # Extract MQTT config
        mqtt_config = config.get("output.mqtt")

        assert mqtt_config["enabled"] is True
        assert mqtt_config["broker"] == "mqtt.test.com"
        assert mqtt_config["port"] == 8883
        assert mqtt_config["topic"] == "test/topic"
        assert mqtt_config["qos"] == 2
        assert mqtt_config["use_tls"] is True
        assert mqtt_config["username"] == "testuser"
        assert mqtt_config["password"] == "testpass"

    def test_gps_config_extraction(self):
        """Test extracting GPS configuration."""
        config = Config()
        config.set("sensors.gps.enabled", True)
        config.set("sensors.gps.host", "192.168.1.100")
        config.set("sensors.gps.port", 2947)
        config.set("sensors.gps.wait_for_fix", True)
        config.set("sensors.gps.fix_timeout", 120)

        gps_config = config.get("sensors.gps")

        assert gps_config["enabled"] is True
        assert gps_config["host"] == "192.168.1.100"
        assert gps_config["port"] == 2947
        assert gps_config["wait_for_fix"] is True
        assert gps_config["fix_timeout"] == 120

    def test_static_location_fallback(self):
        """Test static location when GPS disabled."""
        config = Config()
        config.set("sensors.gps.enabled", False)
        config.set("location.latitude", 37.7749)
        config.set("location.longitude", -122.4194)
        config.set("location.altitude", 10.0)

        # When GPS disabled, use static location
        if not config.get("sensors.gps.enabled"):
            location = config.get("location")
            assert location["latitude"] == 37.7749
            assert location["longitude"] == -122.4194
            assert location["altitude"] == 10.0

    def test_processing_chain_config(self):
        """Test configuring audio processing chain."""
        config = Config()

        # Configure processing nodes
        config.set("processing.dc_removal.enabled", True)
        config.set("processing.dc_removal.cutoff", 5.0)
        config.set("processing.highpass.enabled", True)
        config.set("processing.highpass.cutoff", 5000)
        config.set("processing.highpass.order", 4)
        config.set("processing.gain.db", 3.0)

        # Extract for initialization
        dc_config = config.get("processing.dc_removal")
        hp_config = config.get("processing.highpass")
        gain_config = config.get("processing.gain")

        assert dc_config["enabled"] is True
        assert dc_config["cutoff"] == 5.0
        assert hp_config["enabled"] is True
        assert hp_config["cutoff"] == 5000
        assert hp_config["order"] == 4
        assert gain_config["db"] == 3.0

    def test_multi_detector_config(self):
        """Test configuration for multiple detectors."""
        config = Config()

        # Configure multiple detection methods
        config.set("detection.aubio.enabled", True)
        config.set("detection.aubio.method", "complex")
        config.set("detection.aubio.threshold", 0.35)

        config.set("detection.threshold.enabled", True)
        config.set("detection.threshold.threshold_db", -18.0)
        config.set("detection.threshold.min_duration_ms", 10.0)

        config.set("detection.ml.enabled", False)
        config.set("detection.ml.model_path", "models/classifier.pth")
        config.set("detection.ml.confidence_threshold", 0.75)

        # Verify all detector configs
        aubio_cfg = config.get("detection.aubio")
        threshold_cfg = config.get("detection.threshold")
        ml_cfg = config.get("detection.ml")

        assert aubio_cfg["enabled"] is True
        assert aubio_cfg["method"] == "complex"

        assert threshold_cfg["enabled"] is True
        assert threshold_cfg["threshold_db"] == -18.0

        assert ml_cfg["enabled"] is False
        assert ml_cfg["model_path"] == "models/classifier.pth"
