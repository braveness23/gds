# Future Feature Ideas

This document tracks features that were removed from the codebase during code quality cleanup but may be valuable to implement in the future.

**Last Updated**: 2026-02-15

---

## 1. Machine Learning Detection

**Status**: Removed - Stub Implementation
**Priority**: Medium
**Complexity**: High

### Description
ML-based gunshot classifier using PyTorch or TensorFlow models. Would provide learned pattern recognition superior to simple threshold or onset detection.

### What Existed
- `MLGunShotDetectorNode` class in `src/detection/detection_nodes.py`
- Configuration section in `src/config/config.py`
- Window-based processing with configurable hop size
- Confidence thresholding
- Feature extraction placeholder

### Why Removed
- Only stub implementation - raised `NotImplementedError` when used
- No actual model loading or inference logic
- Would crash if enabled in config
- Feature extraction just returned raw waveform

### Implementation Requirements
- [ ] Train or source a gunshot classification model
- [ ] Implement model loading (PyTorch/TensorFlow/ONNX)
- [ ] Implement proper feature extraction (MFCC, mel-spectrogram, etc.)
- [ ] Add inference pipeline with GPU support
- [ ] Benchmark performance on target hardware (Raspberry Pi)
- [ ] Create model training pipeline/scripts
- [ ] Handle model versioning and updates
- [ ] Add confidence calibration

### References
- Previous config: `detection.ml.enabled`, `detection.ml.model_path`
- Recommended frameworks: PyTorch (lighter), TensorFlow Lite (RPi optimized)
- Consider: Edge Impulse for embedded ML

---

## 2. Meshtastic Output

**Status**: Removed - No Implementation
**Priority**: Medium
**Complexity**: Medium

### Description
Integration with Meshtastic mesh networking radios for off-grid, license-free long-range communication between detection nodes.

### What Existed
- Configuration section only in `src/config/config.py`
- No actual implementation code

### Why Removed
- Configuration existed but no code to use it
- Would silently fail if enabled

### Implementation Requirements
- [ ] Install and test Meshtastic Python library
- [ ] Create `MeshtasticOutputNode` class
- [ ] Handle serial/USB communication with Meshtastic device
- [ ] Implement message formatting for mesh network
- [ ] Add position update broadcasts
- [ ] Add telemetry sharing
- [ ] Handle channel configuration
- [ ] Test range and reliability in target environment
- [ ] Document radio hardware setup

### References
- Previous config: `output.meshtastic.*`
- Hardware: Meshtastic T-Beam, Heltec LoRa32
- Python library: `meshtastic` (pip installable)
- Use case: Rural/remote deployments without WiFi/cellular

---

## 3. LoRa Output

**Status**: Removed - No Implementation
**Priority**: Low
**Complexity**: High

### Description
Direct LoRa radio communication for custom mesh networking protocol. Lower-level alternative to Meshtastic.

### What Existed
- Configuration section only in `src/config/config.py`
- No actual implementation code

### Why Removed
- Configuration existed but no code to use it
- Would silently fail if enabled

### Implementation Requirements
- [ ] Select LoRa hardware (SX1276/SX1278 based)
- [ ] Install and test LoRa driver library (e.g., `pyLoRa`, `CircuitPython_RFM9x`)
- [ ] Create `LoRaOutputNode` class
- [ ] Design custom protocol for detection messages
- [ ] Implement frequency hopping or collision avoidance
- [ ] Add encryption/authentication for security
- [ ] Optimize message size for low bandwidth
- [ ] Handle regulatory compliance (frequency, power limits)
- [ ] Test range in target environment

### References
- Previous config: `output.lora.*`
- Consider using Meshtastic instead (already has protocol built)
- Use case: Custom mesh network with full protocol control

---

## 4. Buffer Saver Output

**Status**: Removed - No Implementation
**Priority**: High
**Complexity**: Low

### Description
Saves audio buffers around detected events to disk for forensic analysis, training data collection, and false positive review.

### What Existed
- Configuration section only in `src/config/config.py`
- No actual implementation code

### Why Removed
- Configuration existed but no code to use it
- Would silently fail if enabled

### Implementation Requirements
- [ ] Create `BufferSaverOutputNode` class
- [ ] Implement circular buffer for pre-trigger samples
- [ ] Save audio to WAV files with metadata
- [ ] Add post-trigger buffer capture
- [ ] Implement disk space management (cleanup old files)
- [ ] Add compression options (FLAC, Opus)
- [ ] Include metadata JSON (timestamp, GPS, detection params)
- [ ] Add configurable retention policy
- [ ] Consider privacy implications of audio recording

### References
- Previous config: `output.buffer_saver.*`
- Format: WAV + JSON sidecar with metadata
- Naming: `{timestamp}_{node_id}_{event_id}.wav`
- **HIGH VALUE**: Critical for debugging false positives and training ML models

---

## 5. I2S Raw Source

**Status**: Removed - Implemented But Unused
**Priority**: Medium
**Complexity**: Medium

### Description
Direct I2S interface audio capture bypassing ALSA for lower latency and CPU usage on Raspberry Pi and similar embedded systems.

### What Existed
- Full implementation in `src/audio/i2s_raw_source.py`
- Test files in `tests/unit/test_i2s_raw_source*.py`
- Documentation in `docs/I2S_RAW_INPUT.md`
- **Code was functional but never wired to main.py**

### Why Removed
- Complete implementation but not integrated into main application
- No configuration option to select I2S source
- Dead code taking up maintenance overhead
- ALSA source works well enough for current needs

### Implementation Requirements
- [ ] Add I2S source option to config (`audio.source_type: "i2s"`)
- [ ] Wire I2SRawSourceNode into main.py audio source selection
- [ ] Document I2S hardware setup (pins, device tree overlays)
- [ ] Test on actual I2S hardware (I2S MEMS mics, PCM1808, etc.)
- [ ] Benchmark latency vs ALSA
- [ ] Benchmark CPU usage vs ALSA
- [ ] Handle I2S-specific error cases
- [ ] Document when to use I2S vs ALSA

### References
- Previous implementation: `src/audio/i2s_raw_source.py` (saved in git history)
- Previous docs: `docs/I2S_RAW_INPUT.md` (saved in git history)
- Use case: Ultra-low latency, embedded systems with direct I2S mics
- **NOTE**: Code was complete - just needs integration

---

## Implementation Priority Recommendations

### High Priority (Implement Soon)
1. **Buffer Saver** - Critical for debugging and ML training
2. **I2S Raw Source** - Already implemented, just needs integration

### Medium Priority (Implement When Needed)
3. **Meshtastic Output** - Valuable for off-grid deployments
4. **ML Detection** - Requires significant ML expertise and training data

### Low Priority (Future Consideration)
5. **LoRa Output** - Use Meshtastic instead unless custom protocol needed

---

## Notes

- All removed code is preserved in git history (commit hash TBD after cleanup)
- Configuration examples preserved in `examples/config.example.yaml`
- Before re-implementing, review git history for previous implementation details
- Consider creating separate feature branches for each implementation
- Add comprehensive tests before merging any feature back in

---

## Related Documentation

- [FEATURES.md](FEATURES.md) - Currently implemented features
- [MVP_STATUS.md](docs/MVP_STATUS.md) - MVP completion status
- [CODE_REFERENCE.md](docs/CODE_REFERENCE.md) - Code architecture
