"""Configuration manager with atomic changes and rollback support.

Manages configuration state with:
- Last known good configuration storage
- Atomic configuration application
- Automatic rollback on failure
- Health check integration
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from enum import Enum
from copy import deepcopy

from src.config.config import Config
from src.core.event_bus import Event, EventBus, EventType
from src.remote_config.safety import (
    ConfigRiskLevel,
    SafetyChecker,
    ValidationResult,
    ValidationStatus,
    is_communication_critical,
)


class ConfigChangeStatus(Enum):
    """Status of a configuration change operation."""

    PENDING = "pending"
    VALIDATING = "validating"
    TESTING = "testing"
    APPLYING = "applying"
    APPLIED = "applied"
    CONFIRMED = "confirmed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass
class ConfigChangeResult:
    """Result of a configuration change attempt."""

    success: bool
    status: ConfigChangeStatus
    message: str
    previous_config: Optional[Dict[str, Any]] = None
    new_config: Optional[Dict[str, Any]] = None
    validation_result: Optional[ValidationResult] = None
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    confirmed_at: Optional[float] = None
    rollback_reason: Optional[str] = None


@dataclass
class PendingChange:
    """Tracks a pending configuration change."""

    change_id: str
    changes: Dict[str, Any]
    previous_config: Dict[str, Any]
    status: ConfigChangeStatus
    created_at: float
    timeout_seconds: float
    requires_confirmation: bool
    requires_test: bool
    tested: bool = False
    confirmed: bool = False
    rolled_back: bool = False
    error: Optional[str] = None


class ConfigManager:
    """
    Manages configuration with safety, validation, and rollback.

    Key features:
    - Applies changes atomically
    - Stores "last known good" configuration
    - Auto-rollback on failure or timeout
    - Prevents communication bricking
    """

    DEFAULT_ROLLBACK_TIMEOUT = 30.0  # seconds
    BACKUP_FILE_NAME = ".last_known_good_config.json"
    STATE_FILE_NAME = ".remote_config_state.json"

    def __init__(
        self,
        config: Config,
        backup_dir: Optional[str] = None,
        safety_checker: Optional[SafetyChecker] = None,
        health_check_callback: Optional[Callable[[], bool]] = None,
        test_connection_callback: Optional[Callable[[Dict[str, Any]], bool]] = None,
        rollback_timeout: float = DEFAULT_ROLLBACK_TIMEOUT,
        event_bus: Optional[EventBus] = None,
    ):
        """
        Initialize config manager.

        Args:
            config: The Config instance to manage
            backup_dir: Directory to store backup configs (default: config file dir)
            safety_checker: Optional custom safety checker
            health_check_callback: Function to check node health
            test_connection_callback: Function to test new MQTT settings
            rollback_timeout: Seconds to wait for confirmation before rollback
            event_bus: Optional event bus for publishing CONFIG events
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config = config
        self.event_bus = event_bus
        self.safety_checker = safety_checker or SafetyChecker(
            test_callback=test_connection_callback
        )
        self.health_check_callback = health_check_callback
        self.test_connection_callback = test_connection_callback
        self.rollback_timeout = rollback_timeout

        # Determine backup directory
        if backup_dir:
            self.backup_dir = Path(backup_dir)
        elif config.config_path:
            self.backup_dir = Path(config.config_path).parent
        else:
            self.backup_dir = Path.home() / ".gds"

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.backup_path = self.backup_dir / self.BACKUP_FILE_NAME
        self.state_path = self.backup_dir / self.STATE_FILE_NAME

        # State tracking
        self.pending_change: Optional[PendingChange] = None
        self.last_change_result: Optional[ConfigChangeResult] = None
        self.last_known_good: Optional[Dict[str, Any]] = None
        self.change_history: List[ConfigChangeResult] = []
        self.max_history = 100

        # Load saved state
        self._load_state()
        self._load_last_known_good()

        # If no last known good, save current
        if self.last_known_good is None:
            self._save_last_known_good()

    def apply_changes(
        self,
        changes: Dict[str, Any],
        change_id: Optional[str] = None,
        force: bool = False,
    ) -> ConfigChangeResult:
        """
        Apply configuration changes with full safety.

        Args:
            changes: Dict of path -> new_value
            change_id: Optional identifier for this change
            force: Skip validation (not recommended)

        Returns:
            ConfigChangeResult with outcome
        """
        change_id = change_id or f"change-{int(time.time() * 1000)}"

        self.logger.info(f"Starting configuration change {change_id}")

        # Phase 1: Validation
        current_config = deepcopy(self.config.data)

        if not force:
            validation = self.safety_checker.validate_changes(changes, current_config)

            if validation.status == ValidationStatus.INVALID:
                self.logger.error(f"Change {change_id} failed validation: {validation.errors}")
                result = ConfigChangeResult(
                    success=False,
                    status=ConfigChangeStatus.FAILED,
                    message=f"Validation failed: {'; '.join(validation.errors)}",
                    previous_config=current_config,
                    validation_result=validation,
                )
                self._record_result(result)
                return result

            # Check if we need to test connection first (CRITICAL paths)
            needs_test = validation.requires_test or any(
                is_communication_critical(path) for path in changes.keys()
            )

            # Check if we need confirmation for high-risk changes
            needs_confirmation = validation.risk_level in (
                ConfigRiskLevel.CRITICAL,
                ConfigRiskLevel.HIGH,
            )
        else:
            validation = None
            needs_test = False
            needs_confirmation = False

        # Store pending change
        self.pending_change = PendingChange(
            change_id=change_id,
            changes=changes,
            previous_config=deepcopy(current_config),
            status=ConfigChangeStatus.PENDING,
            created_at=time.time(),
            timeout_seconds=self.rollback_timeout,
            requires_confirmation=needs_confirmation,
            requires_test=needs_test,
        )
        self._save_state()

        try:
            # Phase 2: Test if needed (CRITICAL communication settings)
            if needs_test and self.test_connection_callback:
                self.pending_change.status = ConfigChangeStatus.TESTING
                self.logger.info("Testing new configuration before apply...")

                # Build test config
                test_config = deepcopy(current_config)
                self._apply_to_dict(test_config, changes)

                # Test the connection
                test_result = self.test_connection_callback(test_config)

                if not test_result:
                    self.logger.error("Configuration test failed - refusing to apply")
                    self.pending_change.tested = True
                    result = ConfigChangeResult(
                        success=False,
                        status=ConfigChangeStatus.FAILED,
                        message="Connection test failed - configuration would brick node",
                        previous_config=current_config,
                        validation_result=validation,
                        error="Connection test failed",
                    )
                    self._cleanup_pending()
                    self._record_result(result)
                    return result

                self.pending_change.tested = True
                self.logger.info("Configuration test passed")

            # Phase 3: Apply changes
            self.pending_change.status = ConfigChangeStatus.APPLYING
            self.logger.info(f"Applying changes: {changes}")

            # Apply each change
            for path, value in changes.items():
                self.config.set(path, value)

            self.pending_change.status = ConfigChangeStatus.APPLIED

            # Save config to disk
            if self.config.config_path:
                self.config.save()

            # Phase 4: Wait for confirmation if needed
            if needs_confirmation:
                self.logger.info(f"Waiting {self.rollback_timeout}s for health confirmation...")

                confirmed = self._wait_for_confirmation()

                if not confirmed:
                    self.logger.warning("Health confirmation failed - rolling back")
                    return self._rollback("Health check timeout/failure")

                self.pending_change.confirmed = True
                self.pending_change.status = ConfigChangeStatus.CONFIRMED
                self.logger.info("Change confirmed - configuration stable")

            # Success! Update last known good
            self._save_last_known_good()

            result = ConfigChangeResult(
                success=True,
                status=ConfigChangeStatus.CONFIRMED,
                message="Configuration applied and confirmed",
                previous_config=self.pending_change.previous_config,
                new_config=deepcopy(self.config.data),
                validation_result=validation,
                confirmed_at=time.time(),
            )

            self._cleanup_pending()
            self._record_result(result)
            self._publish_event("applied", change_id, changes)
            return result

        except Exception as e:
            # Intentionally broad: apply pipeline spans validation, file I/O, and config mutations
            self.logger.exception(f"Error applying configuration: {e}")
            return self._rollback(f"Exception during apply: {e}")

    def confirm_current_config(self) -> bool:
        """
        Confirm that current configuration is working.
        Called when health check passes.

        Returns:
            True if there was a pending change that needed confirmation
        """
        if self.pending_change and self.pending_change.requires_confirmation:
            self.logger.info(f"Confirming change {self.pending_change.change_id}")
            self.pending_change.confirmed = True
            self._save_state()
            return True
        return False

    def check_and_rollback_if_needed(self) -> Optional[ConfigChangeResult]:
        """
        Check if pending change has timed out and needs rollback.
        Should be called periodically (e.g., by health monitor).

        Returns:
            Rollback result if rollback occurred, None otherwise
        """
        if not self.pending_change:
            return None

        if self.pending_change.confirmed or self.pending_change.rolled_back:
            return None

        # Check timeout
        elapsed = time.time() - self.pending_change.created_at

        if elapsed > self.pending_change.timeout_seconds:
            self.logger.warning(
                f"Change {self.pending_change.change_id} timed out after {elapsed:.1f}s"
            )
            return self._rollback("Timeout waiting for confirmation")

        # Check health
        if self.pending_change.requires_confirmation and self.health_check_callback:
            if not self.health_check_callback():
                self.logger.warning("Health check failed - triggering rollback")
                return self._rollback("Health check failed")

        return None

    def rollback_to_last_known_good(self) -> ConfigChangeResult:
        """Force rollback to last known good configuration."""
        self.logger.info("Rolling back to last known good configuration")

        if self.last_known_good is None:
            return ConfigChangeResult(
                success=False,
                status=ConfigChangeStatus.FAILED,
                message="No last known good configuration available",
                error="No backup available",
            )

        return self._rollback(
            "Manual rollback to last known good",
            target_config=self.last_known_good,
            explicit=True,
        )

    def _rollback(
        self,
        reason: str,
        target_config: Optional[Dict[str, Any]] = None,
        explicit: bool = False,
    ) -> ConfigChangeResult:
        """
        Rollback configuration.

        Args:
            reason: Why rollback occurred
            target_config: Config to rollback to (default: pending.previous_config)
        """
        self.logger.info(f"Starting rollback: {reason}")

        if self.pending_change:
            self.pending_change.status = ConfigChangeStatus.ROLLING_BACK
            target_config = target_config or self.pending_change.previous_config
            previous_pending = self.pending_change
        else:
            previous_pending = None
            target_config = target_config or self.last_known_good

        try:
            # Restore configuration
            self.config.data = deepcopy(target_config)

            # Save if we have a config path
            if self.config.config_path:
                self.config.save()

            if previous_pending:
                previous_pending.rolled_back = True
                previous_pending.status = ConfigChangeStatus.ROLLED_BACK

            self._cleanup_pending()

            result = ConfigChangeResult(
                success=explicit,
                status=ConfigChangeStatus.ROLLED_BACK,
                message=f"Rolled back: {reason}",
                previous_config=target_config,
                new_config=deepcopy(self.config.data),
                rollback_reason=reason,
            )

            self._record_result(result)
            self._publish_event("rolled_back", reason=reason)
            self.logger.info("Rollback completed successfully")
            return result

        except Exception as e:
            # Intentionally broad: rollback touches file I/O and config state mutations
            self.logger.exception(f"Rollback failed: {e}")
            return ConfigChangeResult(
                success=False,
                status=ConfigChangeStatus.FAILED,
                message=f"Rollback failed: {e}",
                error=str(e),
                rollback_reason=reason,
            )

    def _wait_for_confirmation(self) -> bool:
        """
        Wait for health confirmation with timeout.

        Returns:
            True if confirmed healthy, False otherwise
        """
        check_interval = 1.0  # Check every second
        elapsed = 0.0

        while elapsed < self.rollback_timeout:
            time.sleep(check_interval)
            elapsed += check_interval

            # Check if manually confirmed
            if self.pending_change and self.pending_change.confirmed:
                self.logger.debug("Manually confirmed")
                return True

            # Check health
            if self.health_check_callback:
                if self.health_check_callback():
                    self.logger.debug(f"Health check passed at {elapsed:.1f}s")
                    # Require multiple consecutive successes
                    consecutive_successes = 0
                    required_successes = 3

                    for _ in range(required_successes - 1):
                        time.sleep(0.5)
                        if self.health_check_callback():
                            consecutive_successes += 1
                        else:
                            break

                    if consecutive_successes >= required_successes - 1:
                        return True

        return False

    def _apply_to_dict(self, target: Dict, changes: Dict[str, Any]):
        """Apply changes to a dictionary using dot notation."""
        for path, value in changes.items():
            keys = path.split(".")
            current = target
            for key in keys[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]
            current[keys[-1]] = value

    def _save_last_known_good(self):
        """Save current config as last known good."""
        self.last_known_good = deepcopy(self.config.data)
        try:
            with open(self.backup_path, "w") as f:
                json.dump(self.last_known_good, f, indent=2)
            self.logger.debug(f"Saved last known good to {self.backup_path}")
        except IOError as e:
            self.logger.error(f"Failed to save last known good: {e}")

    def _load_last_known_good(self):
        """Load last known good config from file."""
        try:
            if self.backup_path.exists():
                with open(self.backup_path, "r") as f:
                    self.last_known_good = json.load(f)
                self.logger.debug(f"Loaded last known good from {self.backup_path}")
        except (IOError, json.JSONDecodeError) as e:
            self.logger.error(f"Failed to load last known good: {e}")
            self.last_known_good = None

    def _save_state(self):
        """Save current state (pending change)."""
        try:
            state = {}
            if self.pending_change:
                state["pending_change"] = {
                    "change_id": self.pending_change.change_id,
                    "changes": self.pending_change.changes,
                    "status": self.pending_change.status.value,
                    "created_at": self.pending_change.created_at,
                    "timeout_seconds": self.pending_change.timeout_seconds,
                    "requires_confirmation": self.pending_change.requires_confirmation,
                    "requires_test": self.pending_change.requires_test,
                    "tested": self.pending_change.tested,
                    "confirmed": self.pending_change.confirmed,
                    "rolled_back": self.pending_change.rolled_back,
                    "error": self.pending_change.error,
                }
                # Save previous config separately (too large for state file)
                previous_path = self.backup_dir / f".pending_{self.pending_change.change_id}.json"
                with open(previous_path, "w") as f:
                    json.dump(self.pending_change.previous_config, f)
                state["previous_config_path"] = str(previous_path)

            with open(self.state_path, "w") as f:
                json.dump(state, f, indent=2)

        except IOError as e:
            self.logger.error(f"Failed to save state: {e}")

    def _load_state(self):
        """Load state from file."""
        try:
            if self.state_path.exists():
                with open(self.state_path, "r") as f:
                    state = json.load(f)

                if "pending_change" in state:
                    pc = state["pending_change"]
                    previous_config = None

                    if "previous_config_path" in state:
                        prev_path = Path(state["previous_config_path"])
                        if prev_path.exists():
                            with open(prev_path, "r") as f:
                                previous_config = json.load(f)

                    if previous_config:
                        self.pending_change = PendingChange(
                            change_id=pc["change_id"],
                            changes=pc["changes"],
                            previous_config=previous_config,
                            status=ConfigChangeStatus(pc["status"]),
                            created_at=pc["created_at"],
                            timeout_seconds=pc["timeout_seconds"],
                            requires_confirmation=pc["requires_confirmation"],
                            requires_test=pc["requires_test"],
                            tested=pc.get("tested", False),
                            confirmed=pc.get("confirmed", False),
                            rolled_back=pc.get("rolled_back", False),
                            error=pc.get("error"),
                        )
                        self.logger.info(f"Restored pending change {self.pending_change.change_id}")

        except (IOError, json.JSONDecodeError, KeyError) as e:
            self.logger.error(f"Failed to load state: {e}")
            self.pending_change = None

    def _cleanup_pending(self):
        """Clean up pending change state."""
        if self.pending_change:
            # Clean up backup file
            backup_file = self.backup_dir / f".pending_{self.pending_change.change_id}.json"
            try:
                if backup_file.exists():
                    backup_file.unlink()
            except OSError:
                pass

            self.pending_change = None
            self._save_state()

    def _record_result(self, result: ConfigChangeResult):
        """Record change result to history."""
        self.last_change_result = result
        self.change_history.append(result)

        # Trim history
        if len(self.change_history) > self.max_history:
            self.change_history = self.change_history[-self.max_history :]

    def _publish_event(
        self,
        action: str,
        change_id: Optional[str] = None,
        changes: Optional[Dict] = None,
        reason: Optional[str] = None,
    ):
        """Publish CONFIG event to event bus if available."""
        if not self.event_bus:
            return
        data = {"action": action}
        if change_id:
            data["change_id"] = change_id
        if changes:
            data["changes"] = changes
        if reason:
            data["reason"] = reason
        self.event_bus.publish(
            Event(
                event_type=EventType.CONFIG,
                timestamp=time.time(),
                source="ConfigManager",
                data=data,
            )
        )

    def get_status(self) -> Dict[str, Any]:
        """Get current manager status."""
        return {
            "has_pending_change": self.pending_change is not None,
            "pending_change_id": self.pending_change.change_id if self.pending_change else None,
            "pending_status": self.pending_change.status.value if self.pending_change else None,
            "last_result": (
                {
                    "success": self.last_change_result.success,
                    "status": self.last_change_result.status.value,
                    "message": self.last_change_result.message,
                }
                if self.last_change_result
                else None
            ),
            "rollback_timeout": self.rollback_timeout,
            "backup_dir": str(self.backup_dir),
            "history_count": len(self.change_history),
        }
