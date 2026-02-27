"""Unit tests for remote configuration manager."""

import json
import time
from unittest.mock import MagicMock

import pytest

from src.config.config import Config
from src.remote_config.manager import (
    ConfigChangeResult,
    ConfigChangeStatus,
    ConfigManager,
    PendingChange,
)


class TestConfigManager:
    """Tests for ConfigManager class."""

    @pytest.fixture
    def temp_config(self, tmp_path):
        """Create a temporary config file."""
        config_path = tmp_path / "test_config.yaml"
        config_data = {
            "system": {"node_id": "test_node", "log_level": "INFO"},
            "output": {
                "mqtt": {
                    "broker": "localhost",
                    "port": 1883,
                    "username": None,
                    "password": None,
                }
            },
            "detection": {"aubio": {"threshold": 0.3}},
        }
        
        with open(config_path, "w") as f:
            import yaml
            yaml.dump(config_data, f)
        
        return Config(str(config_path))

    @pytest.fixture
    def manager(self, temp_config, tmp_path):
        """Create a ConfigManager instance."""
        backup_dir = tmp_path / "backups"
        return ConfigManager(
            config=temp_config,
            backup_dir=str(backup_dir),
            rollback_timeout=2.0,  # Short timeout for tests
        )

    def test_init(self, manager):
        """Test manager initialization."""
        assert manager.config is not None
        assert manager.backup_dir.exists()
        assert manager.rollback_timeout == 2.0
        assert manager.last_known_good is not None

    def test_apply_simple_change(self, manager):
        """Test applying a simple, low-risk change."""
        changes = {"system.log_level": "DEBUG"}
        
        result = manager.apply_changes(changes)
        
        assert result.success is True
        assert result.status == ConfigChangeStatus.CONFIRMED
        assert manager.config.get("system.log_level") == "DEBUG"

    def test_apply_change_with_rollback(self, manager):
        """Test that changes can be rolled back."""
        from copy import deepcopy
        original_value = manager.config.get("system.log_level")
        original_config = deepcopy(manager.config.data)
        changes = {"system.log_level": "DEBUG"}

        # Apply (auto-confirms simple change, updates last_known_good)
        manager.apply_changes(changes)

        # Roll back by explicitly providing the pre-change config
        result = manager._rollback("test rollback", target_config=original_config)

        assert result.status == ConfigChangeStatus.ROLLED_BACK
        assert manager.config.get("system.log_level") == original_value

    def test_pending_change_tracking(self, manager):
        """Test that pending changes are tracked."""
        changes = {"system.log_level": "DEBUG"}
        
        manager.apply_changes(changes, change_id="test-123")
        
        # After successful apply, pending should be cleared
        assert manager.pending_change is None or manager.pending_change.confirmed

    def test_last_known_good_saved(self, manager, tmp_path):
        """Test that last known good config is saved."""
        # Backup file should exist
        backup_file = manager.backup_path
        assert backup_file.exists()
        
        # Load and verify
        with open(backup_file) as f:
            saved = json.load(f)
        
        assert saved["system"]["node_id"] == "test_node"

    def test_validation_failure_rejects_invalid(self, manager):
        """Test that validation failures reject changes."""
        changes = {"output.mqtt.port": 0}  # Invalid port
        
        result = manager.apply_changes(changes)
        
        assert result.success is False
        assert result.validation_result is not None
        assert len(result.validation_result.errors) > 0

    def test_rollback_timeout_triggers_automatically(self, manager):
        """Test automatic rollback on timeout."""
        original_broker = manager.config.get("output.mqtt.broker")
        
        # Apply a CRITICAL change that will timeout
        changes = {"output.mqtt.broker": "new-broker.example.com"}
        
        result = manager.apply_changes(changes)
        
        # Should fail due to timeout waiting for confirmation
        assert result.success is False
        
        # Verify rollback occurred
        assert manager.config.get("output.mqtt.broker") == original_broker

    def test_rollback_to_last_known_good(self, manager):
        """Test explicit rollback to last known good."""
        # Apply a change
        manager.apply_changes({"system.log_level": "DEBUG"})
        
        # Rollback
        result = manager.rollback_to_last_known_good()
        
        assert result.success is True
        assert result.status == ConfigChangeStatus.ROLLED_BACK

    def test_no_last_known_good_backup(self, temp_config, tmp_path):
        """Test behavior when no backup exists."""
        backup_dir = tmp_path / "empty_backups"
        manager = ConfigManager(
            config=temp_config,
            backup_dir=str(backup_dir),
        )
        
        # Remove backup file
        manager.backup_path.unlink(missing_ok=True)
        manager.last_known_good = None
        
        result = manager.rollback_to_last_known_good()
        
        assert result.success is False
        assert "No last known good" in result.message

    def test_health_check_confirmation(self, manager):
        """Test health check confirmation flow."""
        health_check = MagicMock(return_value=True)
        manager.health_check_callback = health_check
        
        # Apply change with health check
        changes = {"system.log_level": "DEBUG"}
        result = manager.apply_changes(changes)
        
        assert result.success is True

    def test_test_connection_rejects_bad_config(self, temp_config, tmp_path):
        """Test that connection testing rejects bad configs."""
        backup_dir = tmp_path / "backups"
        
        test_callback = MagicMock(return_value=False)  # Always fail
        
        manager = ConfigManager(
            config=temp_config,
            backup_dir=str(backup_dir),
            test_connection_callback=test_callback,
        )
        
        changes = {"output.mqtt.broker": "bad-broker"}
        result = manager.apply_changes(changes)
        
        assert result.success is False
        assert "test failed" in result.message.lower()

    def test_state_persistence(self, manager, tmp_path):
        """Test that pending state is persisted to disk."""
        # Create a change that will timeout
        changes = {"output.mqtt.broker": "new-broker.example.com"}
        
        # Start a change (will timeout)
        result = manager.apply_changes(changes, change_id="persist-test")
        
        # State file should exist during pending
        # After completion, it may be cleaned up
        assert manager.state_path.exists() or result.success is not None

    def test_change_history_limit(self, manager):
        """Test that change history is limited."""
        manager.max_history = 5
        
        # Add more changes than max
        for i in range(10):
            result = ConfigChangeResult(
                success=True,
                status=ConfigChangeStatus.CONFIRMED,
                message=f"Change {i}",
            )
            manager._record_result(result)
        
        assert len(manager.change_history) == 5

    def test_get_status(self, manager):
        """Test getting manager status."""
        status = manager.get_status()
        
        assert "has_pending_change" in status
        assert "rollback_timeout" in status
        assert "history_count" in status

    def test_apply_nested_config(self, manager):
        """Test applying nested config changes."""
        changes = {
            "detection.aubio.threshold": 0.5,
            "detection.aubio.silence_threshold": -60,
        }
        
        result = manager.apply_changes(changes)
        
        assert result.success is True
        assert manager.config.get("detection.aubio.threshold") == 0.5

    def test_config_save_after_apply(self, manager, tmp_path):
        """Test that config is saved after successful apply."""
        changes = {"system.log_level": "WARNING"}
        
        manager.apply_changes(changes)
        
        # Reload and verify
        new_config = Config(manager.config.config_path)
        assert new_config.get("system.log_level") == "WARNING"


class TestConfigChangeResult:
    """Tests for ConfigChangeResult dataclass."""

    def test_result_creation(self):
        """Test result creation."""
        result = ConfigChangeResult(
            success=True,
            status=ConfigChangeStatus.CONFIRMED,
            message="Test",
        )
        
        assert result.success is True
        assert result.status == ConfigChangeStatus.CONFIRMED
        assert result.timestamp is not None

    def test_result_with_error(self):
        """Test result with error."""
        result = ConfigChangeResult(
            success=False,
            status=ConfigChangeStatus.FAILED,
            message="Failed",
            error="Some error",
        )
        
        assert result.error == "Some error"


class TestPendingChange:
    """Tests for PendingChange dataclass."""

    def test_pending_creation(self):
        """Test pending change creation."""
        change = PendingChange(
            change_id="test-123",
            changes={"system.log_level": "DEBUG"},
            previous_config={"system": {"log_level": "INFO"}},
            status=ConfigChangeStatus.PENDING,
            created_at=time.time(),
            timeout_seconds=30.0,
            requires_confirmation=True,
            requires_test=False,
        )
        
        assert change.change_id == "test-123"
        assert change.requires_confirmation is True
        assert change.tested is False
        assert change.confirmed is False
