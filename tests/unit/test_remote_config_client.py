"""Unit tests for RemoteConfigClient."""

import json
import time
from unittest.mock import MagicMock, patch, Mock

import pytest

from src.config.config import Config
from src.remote_config.client import RemoteConfigClient, RemoteConfigStatus
from src.remote_config.manager import ConfigChangeResult, ConfigChangeStatus


class TestRemoteConfigClient:
    """Tests for RemoteConfigClient class."""

    @pytest.fixture
    def default_config(self, tmp_path):
        """Create default config."""
        config_path = tmp_path / "config.yaml"
        config_data = {
            "system": {"node_id": "test_node"},
            "remote_config": {
                "enabled": True,
                "mqtt": {
                    "broker": "localhost",
                    "port": 1883,
                }
            },
            "output": {
                "mqtt": {
                    "broker": "localhost",
                    "port": 1883,
                    "username": None,
                    "password": None,
                }
            }
        }
        
        import yaml
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)
        
        return Config(str(config_path))

    @pytest.fixture
    def mock_mqtt(self):
        """Create mock MQTT client."""
        with patch("src.remote_config.client.mqtt.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            yield mock_client

    @pytest.fixture
    def client(self, default_config, mock_mqtt):
        """Create client with mock MQTT."""
        client = RemoteConfigClient(config=default_config)
        return client

    def test_init(self, default_config):
        """Test client initialization."""
        client = RemoteConfigClient(config=default_config)
        
        assert client.node_id == "test_node"
        assert client.topic_base == "gunshot/config/test_node"
        assert client.config_manager is not None

    def test_init_custom_node_id(self, default_config):
        """Test custom node ID."""
        client = RemoteConfigClient(config=default_config, node_id="custom_id")
        
        assert client.node_id == "custom_id"
        assert client.topic_base == "gunshot/config/custom_id"

    def test_topic_structure(self, default_config):
        """Test topic names are correct."""
        client = RemoteConfigClient(config=default_config)
        
        assert client.topic_set == "gunshot/config/test_node/set"
        assert client.topic_get == "gunshot/config/test_node/get"
        assert client.topic_status == "gunshot/config/test_node/status"
        assert client.topic_response == "gunshot/config/test_node/response"

    def test_mqtt_config_loading(self, default_config):
        """Test MQTT config is loaded from config."""
        client = RemoteConfigClient(config=default_config)
        
        assert client.mqtt_config["broker"] == "localhost"
        assert client.mqtt_config["port"] == 1883
        assert client.mqtt_config["enabled"] is True

    def test_disabled_config(self, default_config):
        """Test starting when disabled."""
        default_config.set("remote_config.enabled", False)
        client = RemoteConfigClient(config=default_config)
        
        result = client.start()
        
        assert result is False

    def test_start_connects_mqtt(self, client, mock_mqtt):
        """Test start connects to MQTT."""
        client.start()
        
        assert mock_mqtt.connect.called
        mock_mqtt.connect.assert_called_with("localhost", 1883, keepalive=60)

    def test_credentials_set_when_available(self, client, mock_mqtt, default_config):
        """Test credentials are set from config."""
        default_config.set("output.mqtt.username", "testuser")
        default_config.set("output.mqtt.password", "testpass")

        client.mqtt_config = client._load_mqtt_config()
        client._connect()
        
        mock_mqtt.username_pw_set.assert_called_with("testuser", "testpass")

    def test_handle_set_config(self, client, mock_mqtt):
        """Test handling set_config command."""
        client.start()
        client.connected = True
        client.client = mock_mqtt
        
        payload = {
            "command": "set_config",
            "change_id": "test-123",
            "changes": {"system.log_level": "DEBUG"},
        }
        
        client._handle_set_config(payload)
        
        # Should publish response
        assert mock_mqtt.publish.called

    def test_handle_set_config_missing_change_id(self, client, mock_mqtt):
        """Test set_config rejects missing change_id."""
        client.start()
        client.connected = True
        client.client = mock_mqtt
        
        payload = {
            "command": "set_config",
            "changes": {"system.log_level": "DEBUG"},
        }
        
        client._handle_set_config(payload)
        
        # Should publish error response
        calls = mock_mqtt.publish.call_args_list
        assert any("error" in str(c) for c in calls)

    def test_handle_get_config(self, client, mock_mqtt):
        """Test handling get_config command."""
        client.start()
        client.connected = True
        client.client = mock_mqtt
        
        payload = {
            "command": "get_config",
            "request_id": "req-123",
        }
        
        client._handle_get_config(payload)
        
        # Should publish response
        assert mock_mqtt.publish.called
        
        # Check payload contains config
        call_args = mock_mqtt.publish.call_args
        topic = call_args[0][0]
        message = json.loads(call_args[0][1])
        
        assert topic == client.topic_response
        assert message["command"] == "get_config_response"
        assert "config" in message

    def test_get_config_sanitizes_passwords(self, client, mock_mqtt):
        """Test get_config removes passwords from response."""
        client.start()
        client.connected = True
        client.client = mock_mqtt
        
        # Set a password
        client.config.set("output.mqtt.password", "secret123")
        
        payload = {"command": "get_config", "request_id": "req-123"}
        client._handle_get_config(payload)
        
        call_args = mock_mqtt.publish.call_args
        message = json.loads(call_args[0][1])
        
        assert message["config"]["output"]["mqtt"]["password"] == "***REDACTED***"

    def test_handle_confirm(self, client, mock_mqtt):
        """Test handling confirm command."""
        client.start()
        client.connected = True
        client.client = mock_mqtt

        # Create a pending change
        client.config_manager.pending_change = MagicMock()
        client.config_manager.pending_change.change_id = "test-123"
        client.config_manager.pending_change.requires_confirmation = True

        payload = {
            "command": "confirm",
            "change_id": "test-123",
        }

        with patch.object(client.config_manager, "confirm_current_config") as mock_confirm:
            client._handle_confirm(payload)
            assert mock_confirm.called

    def test_handle_rollback(self, client, mock_mqtt):
        """Test handling rollback command."""
        client.start()
        client.connected = True
        client.client = mock_mqtt
        
        payload = {"command": "rollback"}
        client._handle_rollback(payload)
        
        # Should publish response
        assert mock_mqtt.publish.called

    def test_invalid_json_error(self, client, mock_mqtt):
        """Test error handling for invalid JSON."""
        client.start()
        client.connected = True
        client.client = mock_mqtt
        
        # Simulate invalid JSON message
        msg = MagicMock()
        msg.topic = client.topic_set
        msg.payload = b"not valid json"
        
        client._on_message(client.client, None, msg)
        
        # Should publish error
        calls = mock_mqtt.publish.call_args_list
        assert any("error" in str(c) or "invalid" in str(c).lower() for c in calls)

    def test_get_status(self, client):
        """Test status reporting."""
        status = client.get_status()
        
        assert isinstance(status, RemoteConfigStatus)
        assert hasattr(status, "connected")
        assert hasattr(status, "subscribed")

    def test_reconnect_backoff(self, client):
        """Test reconnect backoff increases."""
        client._connect_failures = 3
        client._last_connect_attempt = time.time()
        
        # Should not try to connect immediately
        result = client._connect()
        
        assert result is False

    def test_stop_cleans_up(self, client, mock_mqtt):
        """Test stop disconnects and cleans up."""
        client.start()
        client.client = mock_mqtt
        client._running = True
        
        client.stop()
        
        assert client._running is False
        mock_mqtt.loop_stop.assert_called()
        mock_mqtt.disconnect.assert_called()

    def test_event_bus_publishes(self, default_config, mock_mqtt):
        """Test that successful changes publish events."""
        event_bus = MagicMock()
        client = RemoteConfigClient(
            config=default_config,
            event_bus=event_bus
        )
        client.client = mock_mqtt
        client.connected = True
        
        payload = {
            "command": "set_config",
            "change_id": "test-123",
            "changes": {"system.log_level": "DEBUG"},
        }
        
        client._handle_set_config(payload)
        
        # Event bus should have been called
        assert event_bus.publish.called

    def test_sanitize_config_redacts_passwords(self, client):
        """Test password redaction in sanitize_config."""
        config = {
            "output": {
                "mqtt": {
                    "password": "secret123",
                    "other_password_field": "also_secret",
                },
                "other": {"nested_password": "deep_secret"}
            },
            "safe_field": "visible",
        }
        
        sanitized = client._sanitize_config(config)
        
        assert sanitized["output"]["mqtt"]["password"] == "***REDACTED***"
        assert sanitized["output"]["mqtt"]["other_password_field"] == "***REDACTED***"
        assert sanitized["output"]["other"]["nested_password"] == "***REDACTED***"
        assert sanitized["safe_field"] == "visible"

    def test_monitor_loop_checks_pending(self, client):
        """Test monitor loop checks for pending changes."""
        client._running = True
        client.config_manager = MagicMock()
        client.config_manager.check_and_rollback_if_needed.return_value = None

        def stop_after_first(*args):
            client._running = False

        with patch("time.sleep", side_effect=stop_after_first):
            client._monitor_loop()

        assert client.config_manager.check_and_rollback_if_needed.called
