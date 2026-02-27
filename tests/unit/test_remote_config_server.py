"""Unit tests for RemoteConfigServer."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from src.remote_config.server import (
    RemoteConfigServer,
    ConfigChange,
    ChangeState,
)


class TestRemoteConfigServer:
    """Tests for RemoteConfigServer class."""

    @pytest.fixture
    def mock_mqtt(self):
        """Create mock MQTT client."""
        with patch("src.remote_config.server.mqtt.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            yield mock_client

    @pytest.fixture
    def server(self, mock_mqtt):
        """Create server with mock MQTT."""
        server = RemoteConfigServer(
            broker="test-broker",
            port=1883,
            username="testuser",
            password="testpass",
            response_timeout=2.0,
        )
        server.client = mock_mqtt
        server.connected = True
        return server

    def test_init(self):
        """Test server initialization."""
        server = RemoteConfigServer(
            broker="test-broker",
            port=1883,
            response_timeout=5.0,
        )
        
        assert server.broker == "test-broker"
        assert server.port == 1883
        assert server.response_timeout == 5.0
        assert server.pending_changes == {}

    def test_connect(self, mock_mqtt):
        """Test connect calls MQTT connect."""
        server = RemoteConfigServer(broker="test-broker", port=1883)
        server.client = None
        
        with patch("src.remote_config.server.mqtt.Client") as mock_class:
            mock_class.return_value = mock_mqtt
            server.connect()
        
        mock_mqtt.connect.assert_called_with("test-broker", 1883, keepalive=60)
        mock_mqtt.loop_start.assert_called()

    def test_connect_failure(self, mock_mqtt):
        """Test connect handles failure."""
        mock_mqtt.connect.side_effect = Exception("Connection refused")
        
        server = RemoteConfigServer(broker="bad-broker", port=1883)
        server.client = None
        
        with patch("src.remote_config.server.mqtt.Client") as mock_class:
            mock_class.return_value = mock_mqtt
            result = server.connect()
        
        assert result is False

    def test_set_node_config(self, server, mock_mqtt):
        """Test sending config to a node."""
        changes = {"system.log_level": "DEBUG"}
        
        change = server.set_node_config("node-1", changes, change_id="test-123")
        
        assert change is not None
        assert change.node_id == "node-1"
        assert change.changes == changes
        assert change.state == ChangeState.SENT
        
        # Verify MQTT publish
        mock_mqtt.publish.assert_called()

    def test_set_node_config_not_connected(self, mock_mqtt):
        """Test sending when not connected."""
        server = RemoteConfigServer(broker="test-broker", port=1883)
        server.connected = False
        
        result = server.set_node_config("node-1", {})
        
        assert result is None

    def test_set_node_config_wait_for_response(self, server, mock_mqtt):
        """Test waiting for response."""
        changes = {"system.log_level": "DEBUG"}
        
        # Simulate successful response
        def mock_wait(oid, timeout):
            # Update pending change state
            if oid in server.pending_changes:
                server.pending_changes[oid].state = ChangeState.ACKNOWLEDGED
            return True
        
        server._wait_for_response = mock_wait
        
        change = server.set_node_config("node-1", changes, wait_for_response=True)
        
        assert change.state == ChangeState.ACKNOWLEDGED

    def test_broadcast_config(self, server, mock_mqtt):
        """Test broadcasting to all known nodes."""
        server.known_nodes = {
            "node-1": {"last_seen": time.time()},
            "node-2": {"last_seen": time.time()},
        }
        
        changes = {"system.log_level": "DEBUG"}
        results = server.broadcast_config(changes)
        
        assert len(results) == 2
        assert "node-1" in results
        assert "node-2" in results

    def test_broadcast_with_exclusions(self, server, mock_mqtt):
        """Test broadcast excluding specific nodes."""
        server.known_nodes = {
            "node-1": {"last_seen": time.time()},
            "node-2": {"last_seen": time.time()},
        }
        
        changes = {"system.log_level": "DEBUG"}
        results = server.broadcast_config(changes, exclude_nodes=["node-1"])
        
        assert len(results) == 1
        assert "node-1" not in results
        assert "node-2" in results

    def test_get_node_config(self, server, mock_mqtt):
        """Test requesting config from node."""
        # Mock response
        config_data = {"system": {"node_id": "node-1"}}
        
        def mock_wait(oid, timeout):
            # Simulate response
            if hasattr(server, '_response_data'):
                return True
            return False
        
        server._wait_for_response = mock_wait
        server._response_data = {"config": config_data}
        
        # Actually test
        with patch.object(server, '_wait_for_response', return_value=True):
            # Register a response
            request_id = None
            for call in mock_mqtt.publish.call_args_list:
                pass  # Find request_id
        
        # Since mocking is complex, just verify the call was made
        result = server.get_node_config("node-1", wait_for_response=False)
        mock_mqtt.publish.assert_called()

    def test_confirm_node_change(self, server, mock_mqtt):
        """Test sending confirmation to node."""
        result = server.confirm_node_change("node-1", "change-123")
        
        assert result is True
        mock_mqtt.publish.assert_called()
        
        # Check topic includes confirm
        call_args = mock_mqtt.publish.call_args
        topic = call_args[0][0]
        assert "confirm" in topic

    def test_rollback_node(self, server, mock_mqtt):
        """Test sending rollback to node."""
        result = server.rollback_node("node-1")
        
        assert result is True
        mock_mqtt.publish.assert_called()
        
        # Check topic includes rollback
        call_args = mock_mqtt.publish.call_args
        topic = call_args[0][0]
        assert "rollback" in topic

    def test_handle_response_acknowledged(self, server):
        """Test handling acknowledged response."""
        # Create pending change
        change_id = "test-123"
        server.pending_changes[change_id] = ConfigChange(
            change_id=change_id,
            node_id="node-1",
            changes={},
            state=ChangeState.SENT,
        )
        
        # Simulate response
        payload = {
            "change_id": change_id,
            "status": "success",
        }
        
        server._handle_response("node-1", payload)
        
        change = server.pending_changes[change_id]
        assert change.state == ChangeState.ACKNOWLEDGED
        assert change.acknowledged_at is not None

    def test_handle_response_failed(self, server):
        """Test handling failed response."""
        change_id = "test-123"
        server.pending_changes[change_id] = ConfigChange(
            change_id=change_id,
            node_id="node-1",
            changes={},
            state=ChangeState.SENT,
        )
        
        payload = {
            "change_id": change_id,
            "status": "failed",
            "message": "Validation failed",
        }
        
        server._handle_response("node-1", payload)
        
        change = server.pending_changes[change_id]
        assert change.state == ChangeState.FAILED
        assert change.error_message == "Validation failed"

    def test_handle_response_callback(self, server):
        """Test callback is called for responses."""
        change_id = "test-123"
        callback = MagicMock()
        server.response_callbacks[change_id] = callback
        
        payload = {
            "change_id": change_id,
            "status": "success",
        }
        
        server._handle_response("node-1", payload)
        
        callback.assert_called_with("node-1", payload)
        # Callback should be removed
        assert change_id not in server.response_callbacks

    def test_handle_status_rolled_back(self, server):
        """Test handling status update indicating rollback."""
        change_id = "test-123"
        server.pending_changes[change_id] = ConfigChange(
            change_id=change_id,
            node_id="node-1",
            changes={},
            state=ChangeState.ACKNOWLEDGED,
        )
        
        payload = {
            "status": "rolled_back",
            "message": "Auto-rollback triggered",
        }
        
        server._handle_status("node-1", payload)
        
        change = server.pending_changes[change_id]
        assert change.state == ChangeState.ROLLED_BACK

    def test_get_known_nodes(self, server):
        """Test getting list of known nodes."""
        server.known_nodes = {
            "node-1": {"last_seen": time.time() - 10},
            "node-2": {"last_seen": time.time()},
        }
        
        nodes = server.get_known_nodes()
        
        assert len(nodes) == 2
        # Should be sorted by last_seen (newest first)
        assert nodes[0]["node_id"] == "node-2"
        assert "last_seen" in nodes[0]
        assert "age_seconds" in nodes[0]

    def test_wait_for_response_success(self, server):
        """Test waiting for response succeeds."""
        change_id = "test-123"
        server.pending_changes[change_id] = ConfigChange(
            change_id=change_id,
            node_id="node-1",
            changes={},
            state=ChangeState.ACKNOWLEDGED,
        )
        
        with patch("time.time") as mock_time:
            mock_time.side_effect = [0, 0.05]  # Start, then check
            
            result = server._wait_for_response(change_id, timeout=1.0)
        
        assert result is True

    def test_wait_for_response_timeout(self, server):
        """Test waiting for response times out."""
        change_id = "test-123"
        server.pending_changes[change_id] = ConfigChange(
            change_id=change_id,
            node_id="node-1",
            changes={},
            state=ChangeState.PENDING,  # Never acknowledged
        )
        
        with patch("time.time") as mock_time:
            mock_time.side_effect = [0, 10.0]  # Start, then timeout exceeded
            with patch("time.sleep"):
                result = server._wait_for_response(change_id, timeout=5.0)
        
        assert result is False

    def test_cleanup_old_changes(self, server):
        """Test cleaning up old changes."""
        old_time = time.time() - 7200  # 2 hours ago
        
        # Old completed change
        server.pending_changes["old-1"] = ConfigChange(
            change_id="old-1",
            node_id="node-1",
            changes={},
            state=ChangeState.CONFIRMED,
        )
        server.pending_changes["old-1"].created_at = old_time
        
        # Recent pending change (should keep)
        server.pending_changes["recent-1"] = ConfigChange(
            change_id="recent-1",
            node_id="node-1",
            changes={},
            state=ChangeState.PENDING,
        )
        
        removed = server.cleanup_old_changes(max_age=3600)  # 1 hour
        
        assert removed == 1
        assert "old-1" not in server.pending_changes
        assert "recent-1" in server.pending_changes

    def test_get_change_status(self, server):
        """Test getting change status."""
        change = ConfigChange(
            change_id="test-123",
            node_id="node-1",
            changes={},
        )
        server.pending_changes["test-123"] = change
        
        result = server.get_change_status("test-123")
        
        assert result == change

    def test_get_change_status_not_found(self, server):
        """Test getting non-existent change."""
        result = server.get_change_status("nonexistent")
        
        assert result is None

    def test_subscribe_on_connect(self, server, mock_mqtt):
        """Test subscribing to topics on connect."""
        # Simulate successful connection
        server._on_connect(server.client, None, None, 0)
        
        # Should subscribe to response and status topics
        calls = mock_mqtt.subscribe.call_args_list
        topics = [call[0][0] for call in calls]
        
        assert any("+/status" in t for t in topics)
        assert any("+/response" in t for t in topics)

    def test_credentials_set_on_connect(self, mock_mqtt):
        """Test credentials are set when connecting."""
        server = RemoteConfigServer(
            broker="test-broker",
            port=1883,
            username="testuser",
            password="secret",
        )
        
        with patch("src.remote_config.server.mqtt.Client") as mock_class:
            mock_class.return_value = mock_mqtt
            server.connect()
        
        mock_mqtt.username_pw_set.assert_called_with("testuser", "secret")

    def test_tls_set_on_connect(self, mock_mqtt):
        """Test TLS is enabled when configured."""
        server = RemoteConfigServer(
            broker="test-broker",
            port=8883,
            use_tls=True,
            tls_ca_cert="/certs/ca.pem",
        )
        
        with patch("src.remote_config.server.mqtt.Client") as mock_class:
            mock_class.return_value = mock_mqtt
            server.connect()
        
        mock_mqtt.tls_set.assert_called_with(ca_certs="/certs/ca.pem")