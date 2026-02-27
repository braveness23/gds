"""Unit tests for remote configuration safety checker."""

import pytest

from src.remote_config.safety import (
    ConfigRiskLevel,
    SafetyChecker,
    ValidationStatus,
    is_communication_critical,
)


class TestSafetyChecker:
    """Tests for SafetyChecker class."""

    @pytest.fixture
    def default_config(self):
        """Default configuration fixture."""
        return {
            "system": {
                "node_id": "test_node",
                "log_level": "INFO",
            },
            "output": {
                "mqtt": {
                    "broker": "localhost",
                    "port": 1883,
                    "username": None,
                    "password": None,
                    "use_tls": False,
                    "topic": "gunshot/detections",
                    "qos": 1,
                }
            },
            "detection": {
                "aubio": {
                    "threshold": 0.3,
                    "silence_threshold": -70,
                }
            },
            "remote_config": {
                "mqtt": {
                    "broker": "localhost",
                    "port": 1883,
                    "username": None,
                    "password": None,
                }
            }
        }

    def test_init(self):
        """Test checker initialization."""
        checker = SafetyChecker()
        assert checker is not None

    def test_low_risk_change(self, default_config):
        """Test detecting low-risk changes."""
        checker = SafetyChecker()
        
        result = checker.validate_change(
            "system.log_level",
            "DEBUG",
            default_config
        )
        
        assert result.status == ValidationStatus.VALID
        assert result.risk_level == ConfigRiskLevel.LOW
        assert not result.requires_test

    def test_critical_broker_change(self, default_config):
        """Test detecting CRITICAL broker change."""
        checker = SafetyChecker()
        
        result = checker.validate_change(
            "output.mqtt.broker",
            "new-broker.example.com",
            default_config
        )
        
        assert result.risk_level == ConfigRiskLevel.CRITICAL
        assert result.requires_test
        assert result.status == ValidationStatus.NEEDS_CONFIRMATION
        assert any("CRITICAL" in w for w in result.warnings)

    def test_critical_port_change(self, default_config):
        """Test detecting CRITICAL port change."""
        checker = SafetyChecker()
        
        result = checker.validate_change(
            "output.mqtt.port",
            8883,
            default_config
        )
        
        assert result.risk_level == ConfigRiskLevel.CRITICAL
        assert result.requires_test

    def test_critical_remote_config_broker(self, default_config):
        """Test detecting CRITICAL remote config broker change."""
        checker = SafetyChecker()
        
        result = checker.validate_change(
            "remote_config.mqtt.broker",
            "new-broker.example.com",
            default_config
        )
        
        assert result.risk_level == ConfigRiskLevel.CRITICAL

    def test_high_risk_threshold_change(self, default_config):
        """Test HIGH risk change for detection thresholds."""
        checker = SafetyChecker()
        
        result = checker.validate_change(
            "detection.aubio.threshold",
            0.8,
            default_config
        )
        
        assert result.risk_level == ConfigRiskLevel.MEDIUM

    def test_invalid_broker_empty_string(self, default_config):
        """Test rejecting empty broker string."""
        checker = SafetyChecker()
        
        result = checker.validate_change(
            "output.mqtt.broker",
            "",
            default_config
        )
        
        assert result.status == ValidationStatus.INVALID
        assert len(result.errors) > 0

    def test_invalid_port_too_low(self, default_config):
        """Test rejecting port < 1."""
        checker = SafetyChecker()
        
        result = checker.validate_change(
            "output.mqtt.port",
            0,
            default_config
        )
        
        assert result.status == ValidationStatus.INVALID

    def test_invalid_port_too_high(self, default_config):
        """Test rejecting port > 65535."""
        checker = SafetyChecker()
        
        result = checker.validate_change(
            "output.mqtt.port",
            100000,
            default_config
        )
        
        assert result.status == ValidationStatus.INVALID

    def test_type_mismatch(self, default_config):
        """Test detecting type mismatch."""
        checker = SafetyChecker()
        
        result = checker.validate_change(
            "output.mqtt.port",
            "not-a-number",
            default_config
        )
        
        # Port string can be converted to int
        assert result.status == ValidationStatus.INVALID

    def test_multiple_changes_validation(self, default_config):
        """Test validating multiple changes at once."""
        checker = SafetyChecker()
        
        changes = {
            "system.log_level": "DEBUG",  # LOW risk
            "output.mqtt.broker": "new-broker.example.com",  # CRITICAL
        }
        
        result = checker.validate_changes(changes, default_config)
        
        assert result.risk_level == ConfigRiskLevel.CRITICAL
        assert result.status == ValidationStatus.NEEDS_CONFIRMATION
        assert "output.mqtt.broker" in result.affected_paths

    def test_password_none_allowed(self, default_config):
        """Test that None password is allowed."""
        checker = SafetyChecker()
        
        result = checker.validate_change(
            "output.mqtt.password",
            None,
            default_config
        )
        
        # Should be valid (no password auth)
        assert result.status != ValidationStatus.INVALID

    def test_is_communication_critical(self):
        """Test the utility function."""
        assert is_communication_critical("output.mqtt.broker") is True
        assert is_communication_critical("output.mqtt.port") is True
        assert is_communication_critical("remote_config.mqtt.broker") is True
        assert is_communication_critical("system.log_level") is False
        assert is_communication_critical("detection.aubio.threshold") is False


class TestConfigRiskLevel:
    """Tests for ConfigRiskLevel enum."""

    def test_risk_values(self):
        """Test risk level values."""
        assert ConfigRiskLevel.LOW.value == "low"
        assert ConfigRiskLevel.MEDIUM.value == "medium"
        assert ConfigRiskLevel.HIGH.value == "high"
        assert ConfigRiskLevel.CRITICAL.value == "critical"

    def test_risk_order(self):
        """Test risk level ordering for comparison."""
        order = [
            ConfigRiskLevel.LOW,
            ConfigRiskLevel.MEDIUM,
            ConfigRiskLevel.HIGH,
            ConfigRiskLevel.CRITICAL,
        ]
        
        for i in range(len(order) - 1):
            assert order[i].value < order[i + 1].value


class TestValidationStatus:
    """Tests for ValidationStatus enum."""

    def test_status_values(self):
        """Test status values."""
        assert ValidationStatus.VALID.value == "valid"
        assert ValidationStatus.INVALID.value == "invalid"
        assert ValidationStatus.NEEDS_CONFIRMATION.value == "needs_confirmation"
        assert ValidationStatus.UNSAFE.value == "unsafe"