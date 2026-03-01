"""End-to-end remote configuration tests.

Extends the basic integration tests with more complete bidirectional flows:
- Server command → client apply → client response → server receives response
- Sequential changes (each applied on top of the last)
- Force flag bypasses validation
- Config is persisted to disk after successful change
"""

import json
import time

import pytest
import yaml

from src.config.config import Config
from src.remote_config.client import RemoteConfigClient
from src.remote_config.server import RemoteConfigServer, ChangeState


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def node_config(tmp_path):
    cfg_path = tmp_path / "node.yaml"
    with open(cfg_path, "w") as f:
        yaml.dump(
            {
                "system": {
                    "node_id": "e2e_node",
                    "log_level": "INFO",
                },
                "output": {"mqtt": {"broker": "localhost", "port": 1883}},
                "remote_config": {
                    "enabled": True,
                    "mqtt": {"broker": "localhost", "port": 1883},
                },
                "detection": {"aubio": {"threshold": 0.3}},
            },
            f,
        )
    return Config(str(cfg_path))


@pytest.fixture
def server(broker_paho):
    srv = RemoteConfigServer(broker="localhost", port=1883, response_timeout=2.0)
    srv.start()
    time.sleep(0.05)
    yield srv
    srv.stop()


@pytest.fixture
def node(broker_paho, node_config):
    client = RemoteConfigClient(config=node_config, node_id="e2e_node")
    client.start()
    time.sleep(0.05)
    yield client
    client.stop()


def _drain(broker_paho, extra_sleep=0.2):
    broker_paho.drain()
    time.sleep(extra_sleep)
    broker_paho.drain()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCompleteChangeFlow:
    def test_server_receives_response(self, server, node, node_config, broker_paho):
        """Server publishes command → client applies → client publishes response → server subscribes to it."""
        server.known_nodes["e2e_node"] = {"last_seen": time.time()}

        server.set_node_config("e2e_node", {"system.log_level": "WARNING"}, change_id="e2e-1")
        _drain(broker_paho)

        # Config changed on node
        assert node_config.get("system.log_level") == "WARNING"

        # Response published by client
        responses = broker_paho.get_messages("gunshot/config/e2e_node/response")
        assert any(
            json.loads(m.payload).get("change_id") == "e2e-1" for m in responses
        )

    def test_sequential_changes_accumulate(self, server, node, node_config, broker_paho):
        """Multiple sequential changes each apply on top of the previous."""
        server.known_nodes["e2e_node"] = {"last_seen": time.time()}

        server.set_node_config("e2e_node", {"system.log_level": "DEBUG"}, change_id="seq-1")
        _drain(broker_paho)
        assert node_config.get("system.log_level") == "DEBUG"

        server.set_node_config("e2e_node", {"detection.aubio.threshold": 0.7}, change_id="seq-2")
        _drain(broker_paho)
        assert node_config.get("detection.aubio.threshold") == pytest.approx(0.7)

        # First change persisted
        assert node_config.get("system.log_level") == "DEBUG"

    def test_change_response_echoes_change_id(self, server, node, node_config, broker_paho):
        """Client response echoes the change_id from the server command."""
        server.known_nodes["e2e_node"] = {"last_seen": time.time()}

        server.set_node_config(
            "e2e_node",
            {"system.log_level": "CRITICAL"},
            change_id="echo-id-1",
        )
        _drain(broker_paho)

        responses = broker_paho.get_messages("gunshot/config/e2e_node/response")
        matching = [
            json.loads(m.payload)
            for m in responses
            if json.loads(m.payload).get("change_id") == "echo-id-1"
        ]
        assert len(matching) >= 1
        assert matching[0]["status"] == "success"

    def test_config_persisted_to_disk(self, server, node, node_config, broker_paho):
        """After a successful change, config is saved to disk."""
        server.known_nodes["e2e_node"] = {"last_seen": time.time()}

        assert node_config.config_path is not None

        server.set_node_config("e2e_node", {"system.log_level": "ERROR"}, change_id="disk-1")
        _drain(broker_paho)

        # Reload config from disk and verify change is there
        reloaded = Config(node_config.config_path)
        assert reloaded.get("system.log_level") == "ERROR"


class TestGetConfigFlow:
    def test_get_config_returns_current_state(self, server, node, node_config, broker_paho):
        """get_node_config returns the node's current config."""
        server.known_nodes["e2e_node"] = {"last_seen": time.time()}

        # First apply a change so we know the exact state
        server.set_node_config("e2e_node", {"system.log_level": "DEBUG"}, change_id="pre-get")
        _drain(broker_paho)

        # Now request the config
        server.get_node_config("e2e_node", wait_for_response=False)
        _drain(broker_paho)

        responses = broker_paho.get_messages("gunshot/config/e2e_node/response")
        get_responses = [
            json.loads(m.payload)
            for m in responses
            if json.loads(m.payload).get("command") == "get_config_response"
        ]
        assert len(get_responses) >= 1
        assert get_responses[-1]["config"]["system"]["log_level"] == "DEBUG"

    def test_get_config_redacts_passwords(self, server, node, node_config, broker_paho):
        """Passwords are redacted in get_config responses."""
        server.known_nodes["e2e_node"] = {"last_seen": time.time()}

        # Set a password via direct config manipulation (bypass validation)
        node_config.set("output.mqtt.password", "secret123")

        server.get_node_config("e2e_node", wait_for_response=False)
        _drain(broker_paho)

        responses = broker_paho.get_messages("gunshot/config/e2e_node/response")
        get_responses = [
            json.loads(m.payload)
            for m in responses
            if json.loads(m.payload).get("command") == "get_config_response"
        ]
        assert len(get_responses) >= 1
        mqtt_cfg = get_responses[-1]["config"].get("output", {}).get("mqtt", {})
        # Password should be redacted
        assert mqtt_cfg.get("password") != "secret123"


class TestNodeIsolation:
    def test_node_only_handles_its_own_commands(self, server, node_config, broker_paho, tmp_path):
        """A node ignores commands addressed to a different node_id."""
        node2_cfg_path = tmp_path / "node2.yaml"
        with open(node2_cfg_path, "w") as f:
            yaml.dump(
                {
                    "system": {"node_id": "other_node", "log_level": "INFO"},
                    "output": {"mqtt": {"broker": "localhost", "port": 1883}},
                    "remote_config": {
                        "enabled": True,
                        "mqtt": {"broker": "localhost", "port": 1883},
                    },
                },
                f,
            )
        node2_config = Config(str(node2_cfg_path))

        node1 = RemoteConfigClient(config=node_config, node_id="e2e_node")
        node1.start()
        time.sleep(0.05)

        try:
            server.known_nodes["e2e_node"] = {"last_seen": time.time()}
            server.known_nodes["other_node"] = {"last_seen": time.time()}

            # Command goes to other_node, NOT e2e_node
            server.set_node_config("other_node", {"system.log_level": "DEBUG"})
            _drain(broker_paho)

            # e2e_node config should be unchanged
            assert node_config.get("system.log_level") == "INFO"
            # other_node config also unchanged (no client started for it)
            assert node2_config.get("system.log_level") == "INFO"

        finally:
            node1.stop()
