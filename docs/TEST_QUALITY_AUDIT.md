# Test Suite Quality Audit

**Generated:** 2026-02-27
**Question asked:** Are we testing to build correct software, or to check a box that says we tested?
**Honest answer:** Unit tests are genuinely good. Integration tests are largely a façade.

---

## Overall Grade: B−

The unit layer is real and would catch real bugs. The integration layer is mostly theater — it tests components in isolation with manually-set state, bypassing the actual communication mechanisms it claims to test. The most critical code path in the system (audio capture) is essentially untested. And 18 tests are permanently broken, which means developers have learned to ignore test failures.

---

## The Damning Evidence First

### 1. 18 Tests Always Fail

This is the most corrosive problem. When tests fail constantly, developers stop treating failures as signal. Red becomes the new green.

**`test_mqtt_real.py` — 7 failures:** Require a live MQTT broker. Run without a skip guard. No environment check, no `@pytest.mark.skip`. They just fail, every time, on every machine without a broker. These were written but never successfully ran in this environment.

**`test_remote_config_integration.py` — 7 failures:** Also fail every run. The irony: these tests *do* use `MockMQTTClient`. They fail because they try to monkey-patch `client_module.mqtt` — an attribute that doesn't exist at module level (it's imported inside a function). These were written but not run to confirm they worked.

**Others:**
- `test_permission_error` (config + logging) — fail because the test environment runs as root, so `PermissionError` is never raised
- `test_risk_order` — logic regression nobody caught
- `test_cpu_temperature_raspberry_pi` — Pi-specific `/sys/class/thermal` path, not guarded

**The problem isn't that they fail. It's that they've clearly been failing for a long time and nobody fixed them.** That means the test suite has been producing noise, not signal.

---

### 2. The Integration Tests Don't Integrate

This is the core quality issue. Most of the integration tests don't test integration — they test units with manually-set state in a different directory.

**`test_client_server_communication` — the worst offender:**
```python
# "Both should connect"
assert server.connect()
client.connected = True  # ← Bypass actual connection logic entirely

# "Send config change"
change = server.set_node_config("integration_node", changes, change_id="int-test-1")
assert change.state == ChangeState.SENT
```
The client never receives anything. The test verifies the server sent a message, not that the client received and processed it. This is a unit test wearing integration clothes.

**`test_rollback_flow` — doesn't verify the rollback:**
```python
client._handle_set_config({..., "changes": {"system.log_level": "DEBUG"}})
assert temp_config.get("system.log_level") == "DEBUG"  # Change applied ✓

client._handle_rollback({"command": "rollback"})

# What does it actually assert?
rollback_responses = [m for m in messages if m["payload"].get("command") == "rollback_response"]
assert len(rollback_responses) > 0  # ← Only checks a response was published
```
It never checks that the config was actually restored to "INFO". A rollback handler that publishes a response but doesn't restore the value would pass this test.

**`test_multiple_nodes_broadcast` and `test_concurrent_changes`:** Test that the server calls `publish()` the right number of times. No subscriber ever receives these messages. These are publish-call-count tests, not integration tests.

**The fundamental architectural problem:** `MockMQTTClient` records published messages but doesn't route them to subscribers. Real client-server communication requires that when the server publishes to `gds/nodes/node1/set_config`, the client's subscription handler fires. That never happens in any integration test. The full round-trip — server publishes → MQTT routes → client receives → applies → responds → server acknowledges — is never tested anywhere outside of hardware.

---

### 3. The Most Critical Code is Untested

`ALSASourceNode._audio_callback()` is where all audio enters the system. It converts raw bytes from PyAudio into the `AudioBuffer` objects that flow through the entire pipeline. It handles bit-depth conversion (16/24/32-bit), stereo reshaping, and timestamp capture. The code comment says "CRITICAL: Capture timestamp FIRST for trilateration accuracy."

Coverage: **0%.**

The test file has three explicitly skipped ALSA tests:
```python
@pytest.mark.skip(reason="ALSA tests require hardware integration - tested in integration tests")
def test_alsa_start_success(self):
    pass  # ← Literally just pass
```

But `_audio_callback` doesn't require ALSA hardware. You call it directly with a bytes object:
```python
in_data = struct.pack('<1024h', *[32767] * 1024)  # 16-bit samples
node._audio_callback(in_data, 1024, None, 0)
```

The decision to skip these as "hardware tests" was wrong. The audio callback logic is pure computation — it deserves unit tests, and it has none.

---

### 4. `test_message_format` Doesn't Test the Message Format

```python
def test_message_format(self, event_bus, mqtt_node):
    """Test published message has correct format."""
    # ...publish a detection...

    # Verify it was published
    assert mqtt_node.messages_published > 0   # ← Verifies count
    assert mqtt_node.messages_failed == 0     # ← Verifies no failure
```

The test is named "test message format." It tests neither the message structure, nor the JSON schema, nor the topic name, nor any field. A detection handler that publishes `{"x": 1}` would pass this test. This is the purest form of box-checking.

---

### 5. `test_all_checks_must_pass` Tests Them Separately

```python
def test_all_checks_must_pass(self, coordinator_full_security):
    """All security checks must pass for message to be accepted."""
    assert coordinator_full_security._verify_node_allowed("node1") is True
    assert coordinator_full_security._check_rate_limit("node1") is True
    assert coordinator_full_security._verify_hmac(payload, valid_sig) is True
```

This tests each check individually. It does **not** test the combined enforcement path — the actual `_handle_message` callback that invokes all three in sequence and rejects the message if any fail. If someone commented out the rate-limit check in the handler, this test would still pass. There is no test for: "send a message from an unauthorized node and verify the system rejects it end-to-end."

---

### 6. Timing Dependencies That Will Flake

Many tests use bare `time.sleep()` instead of polling with a timeout:

```python
# test_mqtt_real.py (×many)
time.sleep(2)
assert mqtt_node.connected is True

# test_audio_nodes.py
node.start()
time.sleep(0.2)  # Let thread run
node.stop()
assert receiver.call_count >= 1
```

The detection tests use the right pattern (`wait_for_dispatch()` polls until the queue is empty). Most other tests don't. On a loaded CI machine, these will occasionally produce false failures.

---

## What's Genuinely Good

To be fair, some of the work here is legitimately high quality.

### `test_detection_nodes.py` — Excellent

This is what good testing looks like. The `_MockAubio` and `_MockOnsetDetector` implementations are minimal and behavioral. The `wait_for_dispatch()` helper is the right way to handle async testing. The tests cover:
- State machine transitions (in_event, event_start_sample)
- Residual sample accumulation across buffers (the hard part of hop-based processing)
- Debouncing logic with precise timing expectations
- Multi-buffer events spanning more than one call to `process()`
- Graceful degradation when aubio is unavailable

If the threshold detector broke, these tests would catch it.

### `test_mqtt_fleet_security.py` — Good

The HMAC tests compute their own reference signatures independently of the production code, which is the right way to test cryptography — you're verifying a contract, not just that `hmac.verify(hmac.sign(x)) == True`. The rate-limit window expiration test uses a real `time.sleep()` to verify actual time-based behavior. These tests would catch real security regressions.

### `test_processing_nodes.py` — Good

Tests verify actual DSP properties: that a high-pass filter attenuates low frequencies by the right amount, that a gain node produces the correct dB-to-linear conversion, that DC removal actually reduces DC offset. Not just "it ran without error."

### `tests/mocks/mock_mqtt.py` — Good Infrastructure

The MockMQTTClient is well-built: it simulates async callbacks, supports failure injection, and has proper cleanup. The limitation (no message routing) is a design gap, not a quality gap.

---

## Summary: What Breaks the Guarantee

The promise of a test suite is: "if these pass, the software works." Here's where that promise breaks:

| Concern | Verdict |
|---|---|
| Unit tests catch regressions in individual components | ✅ Yes, mostly |
| Integration tests verify components work together | ❌ No — they don't route messages between components |
| End-to-end audio pipeline is exercised | ⚠️ Partially — detection nodes are tested, audio capture is not |
| Message format contracts are verified | ❌ No — `test_message_format` doesn't test format |
| Security enforcement is tested end-to-end | ⚠️ Partially — individual checks yes, combined handler no |
| Failing tests are treated as failures | ❌ No — 18 tests have been allowed to fail |
| Tests were run before being committed | ⚠️ Questionable — 14 integration tests fail on first run |

---

## Recommended Fixes (Priority Order)

1. **Fix or delete the 18 failing tests.** Nothing else matters until the suite is green. Mark real-broker tests with `@pytest.mark.mqtt` and exclude them by default in `pytest.ini`.

2. **Test `ALSASourceNode._audio_callback`** with direct invocation using `struct.pack` bytes. This is the most important untested code.

3. **Give integration tests a message bus.** The `MockMQTTClient` needs to route messages between publisher and subscriber, or tests need to call subscriber handlers directly after publishing. Otherwise they're unit tests with extra steps.

4. **Rewrite `test_message_format`** to actually inspect the message structure — JSON fields, topic, required keys.

5. **Rewrite `test_rollback_flow`** to assert the config value was actually restored, not just that a response was published.

6. **Add `test_all_checks_combined`** that calls the actual `_handle_message` path with an unauthorized node and verifies the message is rejected.

7. **Replace `time.sleep()` with polling waits** in tests that have flaky timing.
