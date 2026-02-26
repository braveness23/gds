"""Integration tests for remote configuration using mock MQTT."""

import json
import time
from pathlib import Path

import pytest

from src.config.config import Config
from src.remote_config.client import RemoteConfigClient
from src.remote_config.server import RemoteConfigServer, ChangeState

from tests.mocks.mock_mqtt import MockMQTTClient


class TestRemoteConfigIntegration:
    """Integration tests with mock MQTT."""

    @pytest.fixture
    def temp_config(self, tmp_path):
        """Create a temporary config file."""
        config_path = tmp_path / "integration_config.yaml"
        import yaml
        
        config_data = {
            "system": {"node_id": "integration_node", "log_level": "INFO"},
            "output": {
                "mqtt": {
                    "broker": "localhost",
                    "port": 1883,
                    "username": None,
                    "password": None,
                }
            },
            "remote_config": {
                "enabled": True,
                "mqtt": {
                    "broker": "localhost",
                    "port": 1883,
                }
            },
            "detection": {"aubio": {"threshold": 0.3}},
        }
        
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)
        
        return Config(str(config_path))

    @pytest.fixture
    def mock_mqtt_factory(self):
        """Factory for creating mock MQTT clients."""
        clients = []
        
        def create_client(*args, **kwargs):
            client = MockMQTTClient(*args, **kwargs)
            clients.append(client)
            return client
        
        yield create_client
        
        # Cleanup
        for client in clients:
            client.reset()

    def test_client_server_communication(self, temp_config, mock_mqtt_factory, monkeypatch):
        """Test client-server communication flow with mock MQTT."""
        # Monkey patch the MQTT client
        import src.remote_config.client as client_module
        import src.remote_config.server as server_module
        
        original_client_mqtt = client_module.mqtt
        original_server_mqtt = server_module.mqtt
        
        try:
            # Replace with mock factory
            client_module.mqtt = type("MockModule", (), {"Client": mock_mqtt_factory})()
            server_module.mqtt = type("MockModule", (), {"Client": mock_mqtt_factory})()
            
            # Create server
            server = RemoteConfigServer(
                broker="localhost",
                port=1883,
                response_timeout=5.0,
            )
            
            # Create client
            client = RemoteConfigClient(
                config=temp_config,
                node_id="integration_node",
            )
            
            # Both should connect
            assert server.connect()
            client.connected = True
            
            # Server should track known nodes
            server.known_nodes["integration_node"] = {
                "last_seen": time.time(),
                "payload": {},
            }
            
            # Send config change
            changes = {"system.log_level": "DEBUG"}
            change = server.set_node_config(
                "integration_node",
                changes,
                change_id="int-test-1",
            )
            
            assert change is not None
            assert change.state == ChangeState.SENT
            
        finally:
            # Restore
            client_module.mqtt = original_client_mqtt
            server_module.mqtt = original_server_mqtt

    def test_config_change_roundtrip(self, temp_config, tmp_path, monkeypatch):
        """Test full config change roundtrip with mocks."""
        import src.remote_config.client as client_module
        
        # Track messages
        published_messages = []
        
        def mock_publish(topic, payload, *args, **kwargs):
            published_messages.append({"topic": topic, "payload": payload})
            return type("Result", (), {"rc": 0})()
        
        # Create client with minimal mocking
        client = RemoteConfigClient(config=temp_config)
        client.connected = True
        client.client = type("MockClient", (), {
            "publish": mock_publish,
            "loop_start": lambda: None,
        })()
        
        # Simulate receiving set_config command
        payload = {
            "command": "set_config",
            "change_id": "roundtrip-1",
            "changes": {"system.log_level": "WARNING"},
        }
        
        client._handle_set_config(payload)
        
        # Verify response was published
        responses = [m for m in published_messages if "/response" in m["topic"]]
        assert len(responses) > 0
        
        # Parse response
        response = json.loads(responses[0]["payload"])
        assert response["change_id"] == "roundtrip-1"
        assert response["command"] == "set_config_response"

    def test_multiple_nodes_broadcast(self, temp_config, monkeypatch):
        """Test broadcasting to multiple nodes."""
        import src.remote_config.server as server_module
        
        # Create server with mock
        server = RemoteConfigServer(broker="localhost", port=1883)
        server.connected = True
        
        messages = []
        def mock_publish(topic, payload, *args, **kwargs):
            messages.append({"topic": topic, "payload": json.loads(payload)})
        
        server.client = type("MockClient", (), {"publish": mock_publish})()
        
        # Add multiple known nodes
        for i in range(3):
            server.known_nodes[f"node-{i}"] = {"last_seen": time.time()}
        
        # Broadcast
        changes = {"detection.aubio.threshold": 0.5}
        results = server.broadcast_config(changes)
        
        # Verify all nodes received
        assert len(results) == 3
        assert len(messages) == 3
        
        # All should have same change
        for msg in messages:
            assert msg["payload"]["changes"]["detection.aubio.threshold"] == 0.5

    def test_rollback_flow(self, temp_config, monkeypatch):
        """Test complete rollback flow."""
        # Create client
        client = RemoteConfigClient(config=temp_config)
        client.connected = True
        
        messages = []
        def mock_publish(topic, payload, *args, **kwargs):
            messages.append({"topic": topic, "payload": json.loads(payload)})
        
        client.client = type("MockClient", (), {"publish": mock_publish})()
        
        # First apply a change
        original_level = temp_config.get("system.log_level")
        client._handle_set_config({
            "command": "set_config",
            "change_id": "rollback-test",
            "changes": {"system.log_level": "DEBUG"},
        })
        
        # Verify change applied
        assert temp_config.get("system.log_level") == "DEBUG"
        
        # Now trigger rollback
        client._handle_rollback({"command": "rollback"})
        
        # Verify rollback response
        rollback_responses = [
            m for m in messages 
            if m["payload"].get("command") == "rollback_response"
        ]
        assert len(rollback_responses) > 0

    def test_config_retrieval_flow(self, temp_config, monkeypatch):
        """Test config retrieval from server."""
        client = RemoteConfigClient(config=temp_config)
        client.connected = True
        
        messages = []
        def mock_publish(topic, payload, *args, **kwargs):
            messages.append({"topic": topic, "payload": json.loads(payload)})
        
        client.client = type("MockClient", (), {"publish": mock_publish})()
        
        # Handle get_config
        client._handle_get_config({
            "command": "get_config",
            "request_id": "get-123",
        })
        
        # Verify response
        responses = [m for m in messages if "/response" in m["topic"]]
        assert len(responses) > 0
        
        response = responses[0]["payload"]
        assert response["command"] == "get_config_response"
        assert response["request_id"] == "get-123"
        assert "config" in response
        assert "integration_node" in response["config"]["system"]["node_id"]

    def test_timeout_simulation(self, temp_config, monkeypatch):
        """Test timeout handling in server."""
        server = RemoteConfigServer(broker="localhost", port=1883, response_timeout=0.1)
        server.connected = True
        server.client = type("MockClient", (), {"publish": lambda *a, **k: None})()
        
        # Create pending change that will timeout
        change = server.set_node_config(
            "slow_node",
            {"system.log_level": "DEBUG"},
            change_id="timeout-test",
            wait_for_response=True,
        )
        
        # Should timeout
        assert change.state == ChangeState.TIMEOUT
        assert "timeout" in change.error_message.lower()

    def test_concurrent_changes(self, temp_config, monkeypatch):
        """Test handling multiple concurrent config changes."""
        server = RemoteConfigServer(broker="localhost", port=1883)
        server.connected = True
        
        change_ids = []
        def mock_publish(topic, payload, *args, **kwargs):
            data = json.loads(payload)
            if "change_id" in data:
                change_ids.append(data["change_id"])
        
        server.client = type("MockClient", (), {"publish": mock_publish})()
        
        # Send multiple changes
        for i in range(5):
            server.set_node_config(
                f"node-{i}",
                {"system.log_level": f"LEVEL{i}"},
                change_id=f"concurrent-{i}",
            )
        
        # All should be tracked
        assert len(server.pending_changes) == 5
        
        # All change IDs should be unique
        assert len(set(change_ids)) == 5

    def test_state_recovery_after_restart(self, temp_config, tmp_path):
        """Test that pending state can be recovered after restart."""
        backup_dir = tmp_path / "recovery_test"
        backup_dir.mkdir()
        
        from src.remote_config.manager import ConfigManager
        
        manager = ConfigManager(
            config=temp_config,
            backup_dir=str(backup_dir),
            rollback_timeout=3600,  # Long timeout so it doesn't complete
        )
        
        # Start a change that's pending
        import threading
        
        def apply_async():
            manager.apply_changes(
                {"system.log_level": "DEBUG"},
                change_id="recovery-test",
            )
        
        thread = threading.Thread(target=apply_async)
        thread.start()
        thread.join(timeout=0.5)  # Let it start but not finish
        
        # State file should exist
        assert manager.state_path.exists()
        
        # Now create new manager and load state
        manager2 = ConfigManager(
            config=temp_config,
            backup_dir=str(backup_dir),
        )
        
        # Should have restored pending change
        assert manager2.pending_change is not None
        assert manager2.pending_change.change_id == "recovery-test"
        
        # Cleanup
        manager2._cleanup_pending()
        thread.join(timeout=1.0)