"""Safety validation for remote configuration changes.

Prevents node bricking by validating configuration changes before application,
especially critical for communication settings (MQTT, network).
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from enum import Enum


class ConfigRiskLevel(Enum):
    """Risk level of a configuration change."""

    LOW = "low"  # Safe to apply (logging levels, intervals)
    MEDIUM = "medium"  # May affect performance but not connectivity
    HIGH = "high"  # Could affect connectivity but recoverable
    CRITICAL = "critical"  # Could brick node (MQTT broker, network settings)


class ValidationStatus(Enum):
    """Validation status for configuration change."""

    VALID = "valid"
    INVALID = "invalid"
    NEEDS_CONFIRMATION = "needs_confirmation"
    UNSAFE = "unsafe"


@dataclass
class ValidationResult:
    """Result of configuration validation."""

    status: ValidationStatus
    risk_level: ConfigRiskLevel
    message: str
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    requires_test: bool = False
    affected_paths: List[str] = field(default_factory=list)


class SafetyChecker:
    """
    Validates configuration changes to prevent node bricking.

    Critical paths that could brick a node:
    - output.mqtt.broker (wrong broker = no communication)
    - output.mqtt.port (wrong port = no communication)
    - output.mqtt.username/password (auth failure = no communication)
    - system.node_id (identity change issues)
    """

    # Paths that are CRITICAL (could brick node)
    CRITICAL_PATHS = {
        "output.mqtt.broker",
        "output.mqtt.port",
        "output.mqtt.username",
        "output.mqtt.password",
        "output.mqtt.use_tls",
        "output.mqtt.tls_ca_cert",
        "remote_config.mqtt.broker",
        "remote_config.mqtt.port",
        "remote_config.mqtt.username",
        "remote_config.mqtt.password",
    }

    # Paths that are HIGH risk (affect connectivity but may recover)
    HIGH_RISK_PATHS = {
        "output.mqtt.topic",
        "output.mqtt.qos",
        "audio.device",
        "audio.sample_rate",
        "sensors.gps.host",
        "sensors.gps.port",
    }

    # Paths that are MEDIUM risk (affect performance)
    MEDIUM_RISK_PATHS = {
        "detection.aubio.threshold",
        "detection.aubio.silence_threshold",
        "detection.threshold.threshold_db",
        "processing.highpass_filter.cutoff_freq",
        "processing.gain_db",
        "monitoring.system.update_interval",
        "audio.buffer_size",
    }

    def __init__(
        self,
        test_callback: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ):
        """
        Initialize safety checker.

        Args:
            test_callback: Optional function to test communication settings
                          before applying. Should return True if connection works.
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.test_callback = test_callback

    def validate_change(
        self,
        path: str,
        new_value: Any,
        current_config: Dict[str, Any],
    ) -> ValidationResult:
        """
        Validate a single configuration change.

        Args:
            path: Dot-separated config path
            new_value: New value to set
            current_config: Current configuration dictionary

        Returns:
            ValidationResult with status and risk assessment
        """
        warnings = []
        errors = []
        affected_paths = [path]

        # Determine risk level
        risk_level = self._get_risk_level(path)

        # Validate based on path type
        if path in self.CRITICAL_PATHS:
            result = self._validate_critical_path(path, new_value, current_config)
            if result:
                errors.append(result)

            # Critical paths require connection testing
            requires_test = True

            if risk_level == ConfigRiskLevel.CRITICAL:
                warnings.append(
                    f"CRITICAL: Changing {path} may disconnect node from MQTT. "
                    "Change will be tested before applying. Auto-rollback enabled."
                )

        elif path in self.HIGH_RISK_PATHS:
            requires_test = False
            warnings.append(
                f"HIGH RISK: Changing {path} may affect node operation. "
                "Change can be rolled back if health check fails."
            )
        elif path in self.MEDIUM_RISK_PATHS:
            requires_test = False
        else:
            requires_test = False
            risk_level = ConfigRiskLevel.LOW

        # Type validation
        type_error = self._validate_type(path, new_value, current_config)
        if type_error:
            errors.append(type_error)

        # Range validation for numeric values
        range_error = self._validate_range(path, new_value)
        if range_error:
            errors.append(range_error)

        # Determine final status
        if errors:
            status = ValidationStatus.INVALID
        elif risk_level in (ConfigRiskLevel.CRITICAL, ConfigRiskLevel.HIGH):
            status = ValidationStatus.NEEDS_CONFIRMATION
        else:
            status = ValidationStatus.VALID

        return ValidationResult(
            status=status,
            risk_level=risk_level,
            message=self._build_message(status, path, risk_level),
            warnings=warnings,
            errors=errors,
            requires_test=requires_test,
            affected_paths=affected_paths,
        )

    def validate_changes(
        self,
        changes: Dict[str, Any],
        current_config: Dict[str, Any],
    ) -> ValidationResult:
        """
        Validate multiple configuration changes.

        Args:
            changes: Dict of path -> new_value
            current_config: Current configuration

        Returns:
            Combined ValidationResult
        """
        all_errors = []
        all_warnings = []
        all_affected = []
        max_risk = ConfigRiskLevel.LOW
        any_requires_test = False

        for path, new_value in changes.items():
            result = self.validate_change(path, new_value, current_config)
            all_errors.extend(result.errors)
            all_warnings.extend(result.warnings)
            all_affected.extend(result.affected_paths)
            any_requires_test = any_requires_test or result.requires_test

            # Track highest risk level
            risk_order = [
                ConfigRiskLevel.LOW,
                ConfigRiskLevel.MEDIUM,
                ConfigRiskLevel.HIGH,
                ConfigRiskLevel.CRITICAL,
            ]
            if risk_order.index(result.risk_level) > risk_order.index(max_risk):
                max_risk = result.risk_level

        # Determine combined status
        if all_errors:
            status = ValidationStatus.INVALID
        elif max_risk in (ConfigRiskLevel.CRITICAL, ConfigRiskLevel.HIGH):
            status = ValidationStatus.NEEDS_CONFIRMATION
        else:
            status = ValidationStatus.VALID

        return ValidationResult(
            status=status,
            risk_level=max_risk,
            message=self._build_message(status, "multiple paths", max_risk),
            warnings=all_warnings,
            errors=all_errors,
            requires_test=any_requires_test,
            affected_paths=list(set(all_affected)),
        )

    def _get_risk_level(self, path: str) -> ConfigRiskLevel:
        """Get risk level for a config path."""
        if path in self.CRITICAL_PATHS:
            return ConfigRiskLevel.CRITICAL
        elif path in self.HIGH_RISK_PATHS:
            return ConfigRiskLevel.HIGH
        elif path in self.MEDIUM_RISK_PATHS:
            return ConfigRiskLevel.MEDIUM
        else:
            return ConfigRiskLevel.LOW

    def _validate_critical_path(
        self,
        path: str,
        value: Any,
        config: Dict[str, Any],
    ) -> Optional[str]:
        """Validate a critical path. Returns error message or None."""
        if "broker" in path:
            if not isinstance(value, str) or not value:
                return f"{path}: broker must be a non-empty string"

        elif "port" in path:
            if not isinstance(value, int) or value < 1 or value > 65535:
                return f"{path}: port must be an integer between 1-65535"

        elif path.endswith("password"):
            # Password can be None (no auth) or string
            if value is not None and not isinstance(value, str):
                return f"{path}: password must be string or None"

        return None

    def _validate_type(self, path: str, value: Any, config: Dict[str, Any]) -> Optional[str]:
        """Validate type compatibility. Returns error or None."""
        # Get current value to determine expected type
        current_value = self._get_nested_value(config, path)
        if current_value is None:
            return None  # New path, no type constraint

        current_type = type(current_value)
        new_type = type(value)

        # Allow None for optional fields
        if value is None:
            return None

        # Check basic type compatibility
        if current_type != new_type:
            # Allow int -> float conversion
            if current_type == float and new_type == int:
                return None
            # Allow numeric string conversions for special cases
            if path.endswith("port") and new_type == str:
                try:
                    int(value)
                    return None
                except ValueError:
                    return f"{path}: cannot convert {value!r} to int"

            return (
                f"{path}: type mismatch (expected {current_type.__name__}, got {new_type.__name__})"
            )

        return None

    def _validate_range(self, path: str, value: Any) -> Optional[str]:
        """Validate value is in acceptable range."""
        if not isinstance(value, (int, float)):
            return None

        # Port ranges
        if "port" in path:
            if value < 1 or value > 65535:
                return f"{path}: port must be between 1-65535"

        # Percentage values
        if "percent" in path:
            if value < 0 or value > 100:
                return f"{path}: percentage must be between 0-100"

        # Thresholds should be reasonable
        if "threshold" in path:
            if "db" in path or "silence_threshold" in path:
                if value < -100 or value > 0:
                    return f"{path}: dB threshold should be between -100 and 0"
            elif path.endswith("threshold") and (value < 0 or value > 1):
                return f"{path}: threshold should be between 0.0-1.0"

        return None

    def _get_nested_value(self, config: Dict, path: str) -> Any:
        """Get value from nested dict using dot notation."""
        keys = path.split(".")
        value = config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        return value

    def _build_message(self, status: ValidationStatus, target: str, risk: ConfigRiskLevel) -> str:
        """Build human-readable validation message."""
        if status == ValidationStatus.VALID:
            return f"Configuration change to {target} is valid (risk: {risk.value})"
        elif status == ValidationStatus.INVALID:
            return f"Configuration change to {target} is invalid"
        elif status == ValidationStatus.NEEDS_CONFIRMATION:
            return f"Configuration change to {target} requires confirmation (risk: {risk.value})"
        else:
            return f"Configuration change to {target} is unsafe"


def is_communication_critical(path: str) -> bool:
    """Check if a config path affects node communication."""
    critical_patterns = [
        "output.mqtt",
        "remote_config.mqtt",
    ]
    return any(pattern in path for pattern in critical_patterns)
