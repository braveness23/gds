"""Unit tests for configuration management."""

import json
import tempfile
from pathlib import Path

import yaml

from src.config.config import Config


class TestConfig:
    """Test suite for Config class."""

    def test_default_config(self):
        """Test default configuration is created."""
        config = Config()

        assert config.get("system.node_id") is not None
        assert config.get("audio.sample_rate") == 48000
        assert config.get("audio.buffer_size") == 1024

    def test_get_nested_value(self):
        """Test getting nested config values."""
        config = Config()

        # Nested access
        assert config.get("detection.aubio.enabled") is True
        assert config.get("detection.aubio.hop_size") == 512

    def test_get_with_default(self):
        """Test get with default value."""
        config = Config()

        # Non-existent key returns default
        assert config.get("nonexistent.key", "default") == "default"
        assert config.get("another.missing.key", 42) == 42

    def test_set_value(self):
        """Test setting config values."""
        config = Config()

        config.set("audio.sample_rate", 96000)
        assert config.get("audio.sample_rate") == 96000

        config.set("new.nested.value", "test")
        assert config.get("new.nested.value") == "test"

    def test_load_yaml(self):
        """Test loading YAML configuration."""
        # Create temporary YAML file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(
                {"system": {"node_id": "test_node"}, "audio": {"sample_rate": 44100}}, f
            )
            temp_path = f.name

        try:
            config = Config(temp_path)

            # Loaded values
            assert config.get("system.node_id") == "test_node"
            assert config.get("audio.sample_rate") == 44100

            # Default values still present
            assert config.get("audio.buffer_size") == 1024
        finally:
            Path(temp_path).unlink()

    def test_load_json(self):
        """Test loading JSON configuration."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"system": {"node_id": "json_node"}, "audio": {"channels": 2}}, f)
            temp_path = f.name

        try:
            config = Config(temp_path)

            assert config.get("system.node_id") == "json_node"
            assert config.get("audio.channels") == 2
        finally:
            Path(temp_path).unlink()

    def test_save_yaml(self):
        """Test saving configuration to YAML."""
        config = Config()
        config.set("system.node_id", "saved_node")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            temp_path = f.name

        try:
            config.save(temp_path)

            # Load it back
            with open(temp_path, "r") as f:
                loaded = yaml.safe_load(f)

            assert loaded["system"]["node_id"] == "saved_node"
        finally:
            Path(temp_path).unlink()

    def test_deep_merge(self):
        """Test deep merging of configurations."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(
                {"detection": {"aubio": {"threshold": 0.7}}}, f  # Override default
            )
            temp_path = f.name

        try:
            config = Config(temp_path)

            # Overridden value
            assert config.get("detection.aubio.threshold") == 0.7

            # Other aubio values still from defaults
            assert config.get("detection.aubio.hop_size") == 512
            assert config.get("detection.aubio.enabled") is True
        finally:
            Path(temp_path).unlink()

    def test_missing_file(self):
        """Test loading non-existent file uses defaults."""
        config = Config("/nonexistent/path/config.yaml")

        # Should still have defaults
        assert config.get("audio.sample_rate") == 48000

    def test_get_entire_section(self):
        """Test getting an entire config section."""
        config = Config()

        audio_config = config.get("audio")

        assert isinstance(audio_config, dict)
        assert audio_config["sample_rate"] == 48000
        assert audio_config["buffer_size"] == 1024

    def test_config_path_stored(self):
        """Test config path is stored."""
        config = Config("test.yaml")
        assert config.config_path == "test.yaml"


class TestConfigValidation:
    """Test configuration validation scenarios."""

    def test_invalid_yaml_syntax(self):
        """Test handling of invalid YAML syntax."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: syntax: here:")
            temp_path = f.name

        try:
            # Should not crash, should fall back to defaults
            config = Config(temp_path)
            assert config.get("audio.sample_rate") == 48000
        finally:
            Path(temp_path).unlink()

    def test_unsupported_format(self):
        """Test unsupported file format."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("some text")
            temp_path = f.name

        try:
            # Should use defaults
            config = Config(temp_path)
            assert config.get("audio.sample_rate") == 48000
        finally:
            Path(temp_path).unlink()
