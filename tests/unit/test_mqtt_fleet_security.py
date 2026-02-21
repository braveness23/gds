"""Unit tests for MQTT Fleet Coordinator security features."""

import hashlib
import hmac
import json
import time

import pytest

from src.output.mqtt_output import MQTTFleetCoordinator


@pytest.fixture
def coordinator_no_auth():
    """Fleet coordinator with no authentication (insecure, for testing)."""
    return MQTTFleetCoordinator(
        broker="localhost",
        port=1883,
        allowed_nodes=None,  # No allowlist
        hmac_secret=None,  # No HMAC
    )


@pytest.fixture
def coordinator_with_allowlist():
    """Fleet coordinator with node allowlist."""
    return MQTTFleetCoordinator(
        broker="localhost",
        port=1883,
        allowed_nodes=["node1", "node2", "node3"],
        hmac_secret=None,
    )


@pytest.fixture
def coordinator_with_hmac():
    """Fleet coordinator with HMAC authentication."""
    return MQTTFleetCoordinator(
        broker="localhost",
        port=1883,
        allowed_nodes=None,
        hmac_secret="test_secret_key_12345",
    )


@pytest.fixture
def coordinator_full_security():
    """Fleet coordinator with all security features enabled."""
    return MQTTFleetCoordinator(
        broker="localhost",
        port=1883,
        allowed_nodes=["node1", "node2"],
        hmac_secret="test_secret_key_12345",
        rate_limit_window=10.0,
        rate_limit_max_messages=5,
    )


# ============================================================================
# Node Allowlist Tests
# ============================================================================


class TestNodeAllowlist:
    """Tests for node allowlist validation."""

    def test_no_allowlist_accepts_all(self, coordinator_no_auth):
        """No allowlist should accept any node_id."""
        assert coordinator_no_auth._verify_node_allowed("node1") is True
        assert coordinator_no_auth._verify_node_allowed("unknown_node") is True
        assert coordinator_no_auth._verify_node_allowed("attacker_node") is True

    def test_allowlist_accepts_authorized_nodes(self, coordinator_with_allowlist):
        """Allowlist should accept authorized nodes."""
        assert coordinator_with_allowlist._verify_node_allowed("node1") is True
        assert coordinator_with_allowlist._verify_node_allowed("node2") is True
        assert coordinator_with_allowlist._verify_node_allowed("node3") is True

    def test_allowlist_rejects_unauthorized_nodes(self, coordinator_with_allowlist):
        """Allowlist should reject unauthorized nodes."""
        assert coordinator_with_allowlist._verify_node_allowed("node4") is False
        assert coordinator_with_allowlist._verify_node_allowed("unknown") is False
        assert coordinator_with_allowlist._verify_node_allowed("attacker") is False


# ============================================================================
# HMAC Signature Tests
# ============================================================================


class TestHMACAuthentication:
    """Tests for HMAC message authentication."""

    def test_no_hmac_accepts_all(self, coordinator_no_auth):
        """No HMAC secret should accept messages without signature."""
        payload = {"node_id": "test", "data": "value"}
        assert coordinator_no_auth._verify_hmac(payload, None) is True
        assert coordinator_no_auth._verify_hmac(payload, "invalid_sig") is True

    def test_hmac_rejects_missing_signature(self, coordinator_with_hmac):
        """HMAC enabled should reject messages without signature."""
        payload = {"node_id": "test", "data": "value"}
        assert coordinator_with_hmac._verify_hmac(payload, None) is False

    def test_hmac_accepts_valid_signature(self, coordinator_with_hmac):
        """HMAC should accept messages with valid signature."""
        payload = {"node_id": "test", "data": "value"}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        valid_sig = hmac.new(
            b"test_secret_key_12345",
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        assert coordinator_with_hmac._verify_hmac(payload, valid_sig) is True

    def test_hmac_rejects_invalid_signature(self, coordinator_with_hmac):
        """HMAC should reject messages with invalid signature."""
        payload = {"node_id": "test", "data": "value"}
        invalid_sig = "0" * 64  # Wrong signature

        assert coordinator_with_hmac._verify_hmac(payload, invalid_sig) is False

    def test_hmac_ignores_signature_field_in_hash(self, coordinator_with_hmac):
        """HMAC should exclude 'hmac' field from signed data."""
        # Create payload without hmac field
        payload = {"node_id": "test", "data": "value"}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        valid_sig = hmac.new(
            b"test_secret_key_12345",
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # Add hmac field to payload (should be ignored during verification)
        payload["hmac"] = valid_sig

        assert coordinator_with_hmac._verify_hmac(payload, valid_sig) is True

    def test_hmac_canonical_json_ordering(self, coordinator_with_hmac):
        """HMAC should use canonical JSON (sorted keys) for consistent hashing."""
        # Two payloads with same data but different key order
        payload1 = {"z_field": "value", "a_field": "data", "node_id": "test"}
        payload2 = {"a_field": "data", "node_id": "test", "z_field": "value"}

        # Both should produce the same canonical representation
        canonical1 = json.dumps(payload1, sort_keys=True, separators=(",", ":"))
        canonical2 = json.dumps(payload2, sort_keys=True, separators=(",", ":"))
        assert canonical1 == canonical2

        # Sign payload1
        sig1 = hmac.new(
            b"test_secret_key_12345",
            canonical1.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # Signature should validate for both payloads
        assert coordinator_with_hmac._verify_hmac(payload1, sig1) is True
        assert coordinator_with_hmac._verify_hmac(payload2, sig1) is True


# ============================================================================
# Rate Limiting Tests
# ============================================================================


class TestRateLimiting:
    """Tests for per-node rate limiting."""

    def test_rate_limit_allows_within_limit(self, coordinator_full_security):
        """Rate limit should allow messages within the limit."""
        # Send 5 messages (at the limit)
        for i in range(5):
            assert coordinator_full_security._check_rate_limit("node1") is True

    def test_rate_limit_blocks_over_limit(self, coordinator_full_security):
        """Rate limit should block messages over the limit."""
        # Fill the quota
        for i in range(5):
            coordinator_full_security._check_rate_limit("node1")

        # Next message should be blocked
        assert coordinator_full_security._check_rate_limit("node1") is False

    def test_rate_limit_per_node_independent(self, coordinator_full_security):
        """Rate limits should be independent per node."""
        # Fill quota for node1
        for i in range(5):
            coordinator_full_security._check_rate_limit("node1")

        # node1 should be blocked
        assert coordinator_full_security._check_rate_limit("node1") is False

        # node2 should still be allowed
        assert coordinator_full_security._check_rate_limit("node2") is True

    def test_rate_limit_window_expiration(self, coordinator_full_security):
        """Rate limit should reset after time window expires."""
        # Use a shorter window for faster testing
        coordinator = MQTTFleetCoordinator(
            broker="localhost",
            port=1883,
            rate_limit_window=0.5,  # 500ms window
            rate_limit_max_messages=2,
        )

        # Send 2 messages (at limit)
        assert coordinator._check_rate_limit("node1") is True
        assert coordinator._check_rate_limit("node1") is True

        # Should be blocked now
        assert coordinator._check_rate_limit("node1") is False

        # Wait for window to expire
        time.sleep(0.6)

        # Should be allowed again
        assert coordinator._check_rate_limit("node1") is True

    def test_rate_limit_default_values(self):
        """Rate limiting should have sensible defaults."""
        coordinator = MQTTFleetCoordinator(
            broker="localhost",
            port=1883,
        )

        assert coordinator.rate_limit_window == 60.0  # 60 seconds
        assert coordinator.rate_limit_max_messages == 100


# ============================================================================
# Combined Security Tests
# ============================================================================


class TestCombinedSecurity:
    """Tests for combined security features."""

    def test_full_security_coordinator_initialization(self, coordinator_full_security):
        """Coordinator should initialize with all security features."""
        assert coordinator_full_security.allowed_nodes == {"node1", "node2"}
        assert coordinator_full_security.hmac_secret == "test_secret_key_12345"
        assert coordinator_full_security.rate_limit_window == 10.0
        assert coordinator_full_security.rate_limit_max_messages == 5

    def test_all_checks_must_pass(self, coordinator_full_security):
        """All security checks must pass for message to be accepted."""
        # Valid payload for node1
        payload = {"node_id": "node1", "data": "value"}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        valid_sig = hmac.new(
            b"test_secret_key_12345",
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # All checks pass
        assert coordinator_full_security._verify_node_allowed("node1") is True
        assert coordinator_full_security._check_rate_limit("node1") is True
        assert coordinator_full_security._verify_hmac(payload, valid_sig) is True

    def test_unauthorized_node_rejected_even_with_valid_hmac(self, coordinator_full_security):
        """Unauthorized node should be rejected even with valid HMAC."""
        # Unauthorized node
        payload = {"node_id": "node3", "data": "value"}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        valid_sig = hmac.new(
            b"test_secret_key_12345",
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # Node check fails
        assert coordinator_full_security._verify_node_allowed("node3") is False

        # HMAC would pass if checked
        assert coordinator_full_security._verify_hmac(payload, valid_sig) is True

    def test_rate_limited_node_rejected_even_when_authorized(self, coordinator_full_security):
        """Rate-limited node should be rejected even if authorized."""
        # Fill rate limit quota for node1
        for i in range(5):
            coordinator_full_security._check_rate_limit("node1")

        # Node is authorized but rate limited
        assert coordinator_full_security._verify_node_allowed("node1") is True
        assert coordinator_full_security._check_rate_limit("node1") is False
