"""Configuration management with file loading."""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)


class Config:
    """Configuration management with file loading"""

    # Environment variable → config path mappings.
    # These override any value from the config file. Format: GDS_<NAME>=value
    _ENV_MAP = {
        "GDS_NODE_ID": "system.node_id",
        "GDS_MQTT_BROKER": "output.mqtt.broker",
        "GDS_MQTT_PORT": "output.mqtt.port",
        "GDS_MQTT_USERNAME": "output.mqtt.username",
        "GDS_MQTT_PASSWORD": "output.mqtt.password",
        "GDS_MQTT_USE_TLS": "output.mqtt.use_tls",
        "GDS_MQTT_CA_CERT": "output.mqtt.tls_ca_cert",
        "GDS_REMOTE_MQTT_USERNAME": "remote_config.mqtt.username",
        "GDS_REMOTE_MQTT_PASSWORD": "remote_config.mqtt.password",
    }

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.data: Dict[str, Any] = self._default_config()

        if config_path:
            try:
                self.load(config_path)
            except (
                FileNotFoundError,
                ValueError,
                yaml.YAMLError,
                json.JSONDecodeError,
                IOError,
                OSError,
            ) as e:
                logger.warning(f"Failed to load config from {config_path}: {e}")
                logger.info("Using default configuration")

        self._apply_env_overrides()

    def _apply_env_overrides(self):
        """Apply environment variable overrides (highest priority, after file load)."""
        for env_var, config_path in self._ENV_MAP.items():
            value = os.environ.get(env_var)
            if value is not None:
                # Coerce to int for port-like keys
                if config_path.endswith(".port"):
                    try:
                        value = int(value)
                    except ValueError:
                        logger.warning(f"{env_var}: expected integer, got {value!r} — ignoring")
                        continue
                # Coerce "true"/"false" strings to bool
                elif config_path.endswith("use_tls") or config_path.endswith("tls_insecure"):
                    value = value.lower() in ("1", "true", "yes")
                self.set(config_path, value)
                logger.debug(f"Config override from env: {env_var} → {config_path}")

    def _default_config(self) -> Dict[str, Any]:
        """Default configuration"""
        return {
            "system": {
                "node_id": "gunshot_detector_001",
                "log_level": "INFO",
                "log_path": "/var/log/gunshot_detector.log",
            },
            "timing": {
                "use_pps": True,
                "pps_device": "/dev/pps0",
                "use_ntp": False,
                "ntp_server": "pool.ntp.org",
                "ntp_sync_interval": 300,
                "max_offset_ms": 10.0,
            },
            "sensors": {
                "gps": {
                    "enabled": True,
                    "host": "localhost",
                    "port": 2947,
                    "update_interval": 1.0,
                },
                "environment": {
                    "enabled": True,
                    "sensor_type": "BME280",
                    "i2c_address": 0x76,
                    "gpio_pin": 4,
                    "update_interval": 5.0,
                },
            },
            "audio": {
                "source": "alsa",
                "device": "hw:0,0",
                "sample_rate": 48000,
                "channels": 1,
                "buffer_size": 1024,
                "format_bits": 32,
            },
            "processing": {
                "highpass_filter": {
                    "enabled": True,
                    "cutoff_freq": 5000,
                    "order": 4,
                    "type": "butterworth",
                },
                "gain_db": 0.0,
            },
            "detection": {
                "aubio": {
                    "enabled": True,
                    "method": "complex",
                    "hop_size": 512,
                    "threshold": 0.3,
                    "silence_threshold": -70,
                },
                "threshold": {
                    "enabled": False,
                    "threshold_db": -15,
                    "min_duration_ms": 10,
                },
            },
            "output": {
                "mqtt": {
                    "enabled": True,
                    "broker": "localhost",
                    "port": 1883,
                    "topic": "gunshot/detections",
                    "qos": 1,
                    "username": None,
                    "password": None,
                    "use_tls": False,
                    "tls_insecure": False,
                    "tls_ca_cert": None,
                },
                "file_logger": {
                    "enabled": False,
                    "path": "/var/log/detections.jsonl",
                    "max_size_mb": 100.0,
                    "backup_count": 5,
                },
                "buffer_saver": {
                    "enabled": False,
                    "path": "/var/log/gds_captures",
                    "pre_seconds": 1.0,
                    "post_seconds": 2.0,
                },
            },
            "monitoring": {
                "system": {
                    "enabled": True,
                    "update_interval": 5.0,
                    "disk_path": "/",
                    "alert_thresholds": {
                        "cpu_percent": 90.0,
                        "memory_percent": 90.0,
                        "disk_percent": 95.0,
                        "cpu_temp": 80.0,
                    },
                },
                "audio_buffer": {"enabled": True, "report_interval": 60.0},
                "detection": {"enabled": True, "report_interval": 300.0},
            },
            "remote_config": {
                "enabled": False,
                "require_confirmation": True,
                "auto_save": True,
                "mqtt": {
                    "enabled": False,
                    "broker": "localhost",
                    "port": 1883,
                    "base_topic": "gunshot/config",
                    "username": None,
                    "password": None,
                },
                "web_api": {"enabled": False, "host": "0.0.0.0", "port": 8080},
            },
            "location": {"latitude": None, "longitude": None, "altitude": None},
        }

    def load(self, path: str):
        """Load configuration from file. Raises on error."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        if path.suffix not in [".yaml", ".yml", ".json"]:
            raise ValueError(f"Unsupported config format: {path.suffix}")

        try:
            with open(path, "r") as f:
                if path.suffix in [".yaml", ".yml"]:
                    loaded = yaml.safe_load(f)
                    logger.debug(f"Raw YAML loaded: {loaded}")
                elif path.suffix == ".json":
                    loaded = json.load(f)
                    logger.debug(f"Raw JSON loaded: {loaded}")

            self.data = self._deep_merge(self.data, loaded)
            self.config_path = str(path)
            logger.info(f"Loaded configuration from {path}")
        except (yaml.YAMLError, json.JSONDecodeError) as e:
            logger.error(f"Error parsing config file: {e}")
            raise
        except (IOError, OSError) as e:
            logger.error(f"Error loading config: {e}")
            raise

    def save(self, path: Optional[str] = None):
        """Save configuration to file"""
        path = Path(path or self.config_path)

        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, "w") as f:
                if path.suffix in [".yaml", ".yml"]:
                    yaml.dump(self.data, f, default_flow_style=False)
                elif path.suffix == ".json":
                    json.dump(self.data, f, indent=2)

            logger.info(f"Saved configuration to {path}")

        except (IOError, OSError, PermissionError) as e:
            logger.error(f"Error saving config: {e}")
            raise  # Don't swallow - let caller handle

    def _deep_merge(self, base: Dict, update: Dict) -> Dict:
        """Deep merge dictionaries recursively."""
        result = base.copy()
        for key, value in update.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge nested dicts
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def get(self, path: str, default: Any = None) -> Any:
        """Get config value by dot-separated path"""
        keys = path.split(".")
        value = self.data

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    def set(self, path: str, value: Any):
        """Set config value by dot-separated path"""
        keys = path.split(".")
        target = self.data

        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]

        target[keys[-1]] = value
