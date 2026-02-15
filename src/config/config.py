"""Configuration management with file loading."""

import yaml
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class Config:
    """Configuration management with file loading"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.data: Dict[str, Any] = self._default_config()

        if config_path:
            try:
                self.load(config_path)
            except Exception as e:
                logger.warning(f"Failed to load config from {config_path}: {e}")
                logger.info("Using default configuration")
    
    def _default_config(self) -> Dict[str, Any]:
        """Default configuration"""
        return {
            'system': {
                'node_id': 'gunshot_detector_001',
                'log_level': 'INFO',
                'log_path': '/var/log/gunshot_detector.log'
            },
            'timing': {
                'use_pps': True,
                'pps_device': '/dev/pps0',
                'use_ntp': True,
                'ntp_server': 'localhost',
                'ntp_sync_interval': 300
            },
            'sensors': {
                'gps': {
                    'enabled': True,
                    'host': 'localhost',
                    'port': 2947,
                    'update_interval': 1.0
                },
                'environment': {
                    'enabled': True,
                    'sensor_type': 'BME280',
                    'i2c_address': 0x76,
                    'gpio_pin': 4,
                    'update_interval': 5.0
                }
            },
            'audio': {
                'source_type': 'alsa',
                'device': 'hw:0,0',
                'sample_rate': 48000,
                'channels': 1,
                'buffer_size': 1024,
                'format': 'S32_LE'
            },
            'processing': {
                'highpass_filter': {
                    'enabled': True,
                    'cutoff_freq': 5000,
                    'order': 4,
                    'type': 'butterworth'
                },
                'gain_db': 0.0
            },
            'detection': {
                'aubio': {
                    'enabled': True,
                    'method': 'complex',
                    'hop_size': 512,
                    'threshold': 0.3,
                    'silence_threshold': -70
                },
                'ml': {
                    'enabled': False,
                    'model_path': '/models/gunshot_model.pth',
                    'confidence_threshold': 0.8,
                    'window_size': 4096
                },
                'threshold': {
                    'enabled': False,
                    'threshold_db': -15,
                    'min_duration_ms': 10
                }
            },
            'output': {
                'mqtt': {
                    'enabled': True,
                    'broker': 'localhost',
                    'port': 1883,
                    'topic': 'gunshot/detections',
                    'qos': 1,
                    'username': None,
                    'password': None
                },
                'meshtastic': {
                    'enabled': False,
                    'device': '/dev/ttyUSB0',
                    'channel': 0,
                    'send_position_updates': True,
                    'position_update_interval': 300,
                    'send_telemetry': True,
                    'telemetry_interval': 600
                },
                'lora': {
                    'enabled': False,
                    'device': '/dev/ttyUSB1',
                    'frequency': 915000000,
                    'bandwidth': 125000,
                    'spreading_factor': 7
                },
                'file_logger': {
                    'enabled': True,
                    'path': '/var/log/detections.jsonl'
                },
                'buffer_saver': {
                    'enabled': False,
                    'output_dir': '/data/detections',
                    'pre_trigger_buffers': 10,
                    'post_trigger_buffers': 20
                }
            },
            'monitoring': {
                'system': {
                    'enabled': True,
                    'update_interval': 5.0,
                    'disk_path': '/',
                    'alert_thresholds': {
                        'cpu_percent': 90.0,
                        'memory_percent': 90.0,
                        'disk_percent': 95.0,
                        'cpu_temp': 80.0
                    }
                },
                'audio_buffer': {
                    'enabled': True,
                    'report_interval': 60.0
                },
                'detection': {
                    'enabled': True,
                    'report_interval': 300.0
                }
            },
            'remote_config': {
                'enabled': False,
                'require_confirmation': True,
                'auto_save': True,
                'mqtt': {
                    'enabled': False,
                    'broker': 'localhost',
                    'port': 1883,
                    'base_topic': 'gunshot/config',
                    'username': None,
                    'password': None
                },
                'web_api': {
                    'enabled': False,
                    'host': '0.0.0.0',
                    'port': 8080
                }
            },
            'location': {
                'latitude': None,
                'longitude': None,
                'altitude': None
            }
        }
    
    def load(self, path: str):
        """Load configuration from file. Raises on error."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        if path.suffix not in ['.yaml', '.yml', '.json']:
            raise ValueError(f"Unsupported config format: {path.suffix}")

        try:
            with open(path, 'r') as f:
                if path.suffix in ['.yaml', '.yml']:
                    loaded = yaml.safe_load(f)
                    logger.debug(f"Raw YAML loaded: {loaded}")
                elif path.suffix == '.json':
                    loaded = json.load(f)
                    logger.debug(f"Raw JSON loaded: {loaded}")

            self.data = self._deep_merge(self.data, loaded)
            self.config_path = str(path)
            logger.info(f"Loaded configuration from {path}")
        except (yaml.YAMLError, json.JSONDecodeError) as e:
            logger.error(f"Error parsing config file: {e}")
            raise
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            raise
    
    def save(self, path: Optional[str] = None):
        """Save configuration to file"""
        path = Path(path or self.config_path)
        
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, 'w') as f:
                if path.suffix in ['.yaml', '.yml']:
                    yaml.dump(self.data, f, default_flow_style=False)
                elif path.suffix == '.json':
                    json.dump(self.data, f, indent=2)

            logger.info(f"Saved configuration to {path}")

        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
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
        keys = path.split('.')
        value = self.data
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def set(self, path: str, value: Any):
        """Set config value by dot-separated path"""
        keys = path.split('.')
        target = self.data
        
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]
        
        target[keys[-1]] = value
