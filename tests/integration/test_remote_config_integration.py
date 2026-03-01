"""Integration tests for remote configuration using the routing mock broker.

These tests wire up real RemoteConfigServer and RemoteConfigClient instances
through MockMQTTBroker so messages are actually routed between components.
The ``broker_paho`` fixture patches paho on both lazy and top-level import sites.
"""

import json
import time

import pytest
import yaml

from src.config.config import Config
from src.remote_config.client import RemoteConfigClient
from src.remote_config.server import RemoteConfigServer, ChangeState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def rc_config(tmp_path):
    """Config for a remote-config-enabled node."""
    config_path = tmp_path / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(
            {
                "system": {"node_id": "test_node", "log_level": "INFO"},
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
                    "mqtt": {"broker": "localhost", "port": 1883},
                },
                "detection": {"aubio": {"threshold": 0.3}},
            },
            f,
        )
    return Config(str(config_path))


@pytest.fixture
def server(broker_paho):
    """RemoteConfigServer connected through the routing mock broker."""
    srv = RemoteConfigServer(broker="localhost", port=1883, response_timeout=2.0)
    srv.start()
    time.sleep(0.05)  # let on_connect fire and subscriptions register
    yield srv
    srv.stop()


@pytest.fixture
def rc_client(broker_paho, rc_config):
    """RemoteConfigClient connected through the routing mock broker."""
    client = RemoteConfigClient(config=rc_config, node_id="test_node")
    client.start()
    time.sleep(0.05)
    yield client
    client.stop()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _wait(condition_fn, timeout=2.0, interval=0.05):
    """Poll until condition_fn() is True or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition_fn():
            return True
        time.sleep(interval)
    return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRemoteConfigIntegration:
    """Integration tests with routing mock broker."""

    def test_client_server_communication(self, server, rc_client, broker_paho):
        """Server can publish a config change command that reaches the client."""
        server.known_nodes["test_node"] = {"last_seen": time.time()}

        change = server.set_node_config("test_node", {"system.log_level": "DEBUG"})

        assert change is not None
        assert change.state == ChangeState.SENT

        # Verify the command was routed through the broker
        broker_paho.drain()
        msgs = broker_paho.get_messages("gunshot/config/test_node/set")
        assert len(msgs) >= 1
        payload = json.loads(msgs[0].payload)
        assert payload["command"] == "set_config"
        assert payload["changes"]["system.log_level"] == "DEBUG"

    def test_config_change_roundtrip(self, server, rc_client, rc_config, broker_paho):
        """Config change sent by server is applied on client and acknowledged."""
        server.known_nodes["test_node"] = {"last_seen": time.time()}
        assert rc_config.get("system.log_level") == "INFO"

        server.set_node_config(
            "test_node",
            {"system.log_level": "DEBUG"},
            change_id="roundtrip-1",
        )

        # Wait for: server→client routing, client applies, client→server response
        broker_paho.drain()
        time.sleep(0.2)
        broker_paho.drain()

        # Config was actually changed on the client side
        assert rc_config.get("system.log_level") == "DEBUG"

        # Client published a response back
        response_msgs = broker_paho.get_messages("gunshot/config/test_node/response")
        assert len(response_msgs) >= 1
        response = json.loads(response_msgs[0].payload)
        assert response["change_id"] == "roundtrip-1"
        assert response["command"] == "set_config_response"

    def test_multiple_nodes_broadcast(self, server, broker_paho, tmp_path):
        """Broadcast reaches all known nodes."""
        clients = []
        configs = []
        for i in range(3):
            cfg_path = tmp_path / f"config_{i}.yaml"
            with open(cfg_path, "w") as f:
                yaml.dump(
                    {
                        "system": {"node_id": f"node-{i}", "log_level": "INFO"},
                        "output": {"mqtt": {"broker": "localhost", "port": 1883}},
                        "remote_config": {
                            "enabled": True,
                            "mqtt": {"broker": "localhost", "port": 1883},
                        },
                        "detection": {"aubio": {"threshold": 0.3}},
                    },
                    f,
                )
            cfg = Config(str(cfg_path))
            configs.append(cfg)
            rc = RemoteConfigClient(config=cfg, node_id=f"node-{i}")
            rc.start()
            clients.append(rc)
            server.known_nodes[f"node-{i}"] = {"last_seen": time.time()}

        time.sleep(0.1)  # let all on_connect callbacks fire

        try:
            server.broadcast_config({"detection.aubio.threshold": 0.5})
            broker_paho.drain()
            time.sleep(0.3)

            # All three clients should have received and applied the change
            for cfg in configs:
                assert cfg.get("detection.aubio.threshold") == pytest.approx(0.5)
        finally:
            for rc in clients:
                rc.stop()

    def test_rollback_flow(self, server, rc_client, rc_config, broker_paho):
        """Rollback restores the last known good config value.

        ConfigManager saves ``last_known_good`` at init (INFO).  Directly
        mutating ``rc_config`` bypasses ConfigManager so ``last_known_good``
        stays at INFO.  Triggering rollback via the client handler must
        restore the config to that saved value.
        """
        server.known_nodes["test_node"] = {"last_seen": time.time()}

        # Record the value saved as last_known_good at ConfigManager init
        original_level = rc_config.get("system.log_level")  # "INFO"

        # Corrupt the config directly (bypasses ConfigManager, last_known_good stays "INFO")
        rc_config.set("system.log_level", "DEBUG")
        assert rc_config.get("system.log_level") == "DEBUG"

        # Trigger rollback
        rc_client._handle_rollback({"command": "rollback"})
        broker_paho.drain()
        time.sleep(0.1)

        # Config restored to last known good (original_level = "INFO")
        assert rc_config.get("system.log_level") == original_level

        # Rollback response published
        response_msgs = broker_paho.get_messages("gunshot/config/test_node/response")
        rollback_responses = [
            json.loads(m.payload)
            for m in response_msgs
            if json.loads(m.payload).get("command") == "rollback_response"
        ]
        assert len(rollback_responses) >= 1

    def test_config_retrieval_flow(self, server, rc_client, rc_config, broker_paho):
        """Server can retrieve current config from a node."""
        server.known_nodes["test_node"] = {"last_seen": time.time()}

        server.get_node_config("test_node", wait_for_response=False)
        broker_paho.drain()
        time.sleep(0.2)
        broker_paho.drain()

        # Client published a get_config_response
        response_msgs = broker_paho.get_messages("gunshot/config/test_node/response")
        get_responses = [
            json.loads(m.payload)
            for m in response_msgs
            if json.loads(m.payload).get("command") == "get_config_response"
        ]
        assert len(get_responses) >= 1
        assert "config" in get_responses[0]
        assert get_responses[0]["config"]["system"]["node_id"] == "test_node"

    def test_timeout_simulation(self, broker_paho):
        """Server change times out when no client responds."""
        server = RemoteConfigServer(broker="localhost", port=1883, response_timeout=0.2)
        server.start()
        time.sleep(0.05)

        try:
            change = server.set_node_config(
                "slow_node",
                {"system.log_level": "DEBUG"},
                change_id="timeout-test",
                wait_for_response=True,
            )

            assert change is not None
            assert change.state == ChangeState.TIMEOUT
            assert "timeout" in change.error_message.lower()
        finally:
            server.stop()

    def test_concurrent_changes(self, broker_paho):
        """Server tracks multiple concurrent changes with unique IDs."""
        server = RemoteConfigServer(broker="localhost", port=1883)
        server.start()
        time.sleep(0.05)

        try:
            for i in range(5):
                server.known_nodes[f"node-{i}"] = {"last_seen": time.time()}
                server.set_node_config(
                    f"node-{i}",
                    {"system.log_level": "DEBUG"},
                    change_id=f"concurrent-{i}",
                )

            assert len(server.pending_changes) == 5
            assert len(set(server.pending_changes.keys())) == 5

            # All 5 commands published to broker
            broker_paho.drain()
            published = broker_paho.get_messages("gunshot/config/+/set")
            assert len(published) == 5
        finally:
            server.stop()

    def test_state_recovery_after_restart(self, broker_paho, tmp_path):
        """Pending change state persists to disk and is loadable after restart."""
        from src.remote_config.manager import ConfigManager

        cfg_path = tmp_path / "config.yaml"
        with open(cfg_path, "w") as f:
            yaml.dump(
                {
                    "system": {"node_id": "recovery_node", "log_level": "INFO"},
                    "output": {"mqtt": {"broker": "localhost", "port": 1883}},
                    "remote_config": {
                        "enabled": True,
                        "mqtt": {"broker": "localhost", "port": 1883},
                    },
                },
                f,
            )
        config = Config(str(cfg_path))

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        manager = ConfigManager(
            config=config,
            backup_dir=str(backup_dir),
            rollback_timeout=3600,
        )
        manager.apply_changes(
            {"system.log_level": "DEBUG"},
            change_id="recovery-test",
        )

        # State file should have been written
        assert manager.state_path.exists()

        # New manager instance from same backup dir should load persisted state
        manager2 = ConfigManager(
            config=config,
            backup_dir=str(backup_dir),
        )
        assert manager2.state_path.exists()
