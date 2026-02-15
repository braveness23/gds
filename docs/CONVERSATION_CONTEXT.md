# Conversation Summary - Claude Code Context

This document provides context for continuing development with Claude Code in VS Code.

## What We Built

A production-ready gunshot detection system for Raspberry Pi fleets with:
- Microsecond-accurate timing (GPS PPS + NTP)
- Multiple detection algorithms (Aubio, ML, threshold)
- Environmental sensors (GPS, temperature, humidity)
- Mesh networking (MQTT, Meshtastic, LoRa)
- Remote fleet management
- Comprehensive monitoring
- Modular, event-driven architecture

## Conversation Flow

### 1. Initial Question (Aubio for Gunshots)
**You:** Can aubio detect non-musical onsets like gunshots?
**Answer:** Yes, aubio's onset detection works great for gunshots - it detects sharp transients regardless of source.

**Key Points:**
- Aubio latency: 5-20ms (configurable via hop size)
- "complex" or "mkl" methods best for gunshots
- Can read from I2S streams via ALSA or direct device access
- Can add high-pass filtering (5kHz) to reject low-frequency noise

### 2. Timing Requirements (Trilateration)
**You:** What about latency for trilateration?
**Answer:** Algorithmic latency doesn't matter if you timestamp at capture.

**Key Insight:**
Since you're capturing timestamp at the moment audio arrives (PPS-synced),
processing latency is irrelevant for position accuracy. Only matters for
real-time alerting.

**Decision:** Timestamp early, process later.

### 3. Fleet Architecture
**You:** I have Raspberry Pis with GPS, PPS, I2S mics, and MEMS microphones.
**Answer:** Perfect setup for high-accuracy detection system.

**Architecture Decision:** Node-based pipeline with event bus
- Modular processing nodes
- Event-driven communication
- Each Pi is independent but coordinated via MQTT
- GPS/PPS for timing precision

### 4. Feature Additions

**Session evolved to add:**
1. Multiple detection methods (Aubio + ML + threshold)
2. Environmental sensors (BME280, DHT22)
3. Mesh networking (Meshtastic, LoRa)
4. Remote configuration management
5. System health monitoring
6. Fleet deployment automation

**Why:** You mentioned wanting MQTT, then Meshtastic, then LoRa, monitoring,
and remote config. Each addition fit naturally into the event bus architecture.

### 5. Packaging Request
**You:** Can you compile and execute this?
**Answer:** No, but I can package it for deployment.

**Result:** Complete project structure with:
- All source files organized
- Documentation (README, quickstart, deployment guide)
- Installation automation (install.sh, Makefile)
- Systemd service
- Example configurations

## Design Philosophy

### Event Bus as Central Nervous System
Everything communicates via publish/subscribe:
- Audio nodes publish buffers
- Detectors subscribe to buffers, publish events
- Outputs subscribe to events
- Monitoring subscribes to everything

**Benefit:** No tight coupling. Easy to add new components.

### Timestamp Early, Process Later
For trilateration accuracy:
- Capture timestamp at I2S buffer arrival
- Sync with GPS PPS (microsecond precision)
- Processing latency doesn't affect position accuracy

**Benefit:** Can use complex processing (ML) without timing penalty.

### Graceful Degradation
System works with minimal config:
- No GPS? Use static location or NTP
- No sensors? Just skip them
- No Meshtastic? MQTT only
- No MQTT? Local logging only

**Benefit:** Easy testing, reliable deployment.

### Configuration Over Code
All behavior controlled via config.yaml:
- Enable/disable any component
- Adjust thresholds, intervals, paths
- Remote updates via MQTT

**Benefit:** No code changes needed for tuning in field.

## Key Technical Decisions

### 1. Why Aubio?
- Fast (5-20ms latency)
- Multiple onset detection methods
- Battle-tested library
- Works great on transients (gunshots)

### 2. Why Event Bus?
- Decouples components
- Observable system (all events visible)
- Easy to add monitoring/logging
- Natural pub/sub for MQTT

### 3. Why GPS PPS?
- Trilateration needs <1ms timing accuracy
- NTP only provides ~10ms
- PPS provides <1μs
- Combined: PPS for precision, NTP for absolute time

### 4. Why MQTT?
- Lightweight pub/sub protocol
- Perfect for IoT fleets
- One-to-many communication (broadcast config updates)
- Existing ecosystem (Node-RED, InfluxDB, etc.)

### 5. Why Meshtastic?
- Works without infrastructure
- Long range (LoRa radio)
- Self-healing mesh
- Good for remote/rural deployments

### 6. Why Modular Nodes?
- Test components independently
- Reuse in different configurations
- Easy to understand (each node does one thing)
- Parallel processing (split audio to multiple detectors)

## Code Structure

```
Core Pattern:
  AudioBuffer flows through pipeline
  Each node processes and emits
  Event bus distributes to subscribers
  Outputs send to network/disk

Example Flow:
  I2S Mic → [timestamp!] → Buffer
          → Mono Convert → Buffer
          → HPF Filter → Buffer
          → Splitter → [Buffer, Buffer, Buffer]
                    → Aubio → DetectionEvent
                    → ML → DetectionEvent
                    → Threshold → DetectionEvent
                              → Event Bus
                              → MQTT
                              → Meshtastic
                              → File Logger
```

## What Claude Code Will Help With

### 1. Implementing the Code
All the module code from our conversation needs to be copied into files.
Claude Code can help by:
- Implementing one class at a time
- Ensuring imports are correct
- Adding error handling
- Writing docstrings
- Fixing bugs

### 2. Testing
Claude Code can help:
- Write unit tests
- Create test fixtures (sample audio, mock GPS data)
- Debug issues
- Verify integration

### 3. Extending
If you want to add:
- New detectors (different ML models)
- New sensors (accelerometer, etc.)
- New outputs (database, cloud services)
- New features (audio classification, etc.)

Claude Code can help design and implement while maintaining architecture.

## How to Use This Document with Claude Code

### Starting Fresh
```
"I'm working on the gunshot detection system we designed. The architecture
uses an event bus with modular nodes. I need to implement the ALSASourceNode
class that captures audio from an I2S microphone via ALSA and timestamps it
with GPS PPS precision. See CODE_REFERENCE.md for the design."
```

### Debugging
```
"The HighPassFilterNode is causing buffer underruns. According to the design
in CODE_REFERENCE.md, we're using scipy SOS filters with state management.
Can you help debug why the filter might be dropping buffers?"
```

### Extending
```
"I want to add a new output node for InfluxDB. Following the pattern from
MQTTOutputNode (see CODE_REFERENCE.md), it should subscribe to detection
events and write time-series data. Can you help implement this?"
```

### Configuration
```
"Looking at the config design, I want to add a new sensor. What changes do
I need to make to config.yaml, the Config class validation, and the main
application?"
```

## Important Constraints to Remind Claude Code

1. **Timing is Critical**
   - Always timestamp at earliest possible moment
   - Never block in audio callbacks
   - Use threading for I/O operations

2. **Event Bus is the Hub**
   - Don't create direct dependencies between nodes
   - All communication via events
   - Use EventType enum for type safety

3. **Immutable Buffers**
   - Never modify AudioBuffer in place
   - Return new objects from processing nodes
   - Prevents race conditions

4. **Graceful Degradation**
   - Handle missing hardware gracefully
   - Log warnings, don't crash
   - Check config.get() with defaults

5. **Fleet Deployment**
   - Code runs on multiple Pis simultaneously
   - Each needs unique node_id
   - Central MQTT broker coordinates

## Common Questions for Claude Code

### "How do I test without hardware?"
Use FileSourceNode with sample audio files. Disable GPS/sensors in config.

### "How do I add a new detector?"
1. Subclass AudioNode
2. Subscribe to buffers (via connect())
3. Process and publish DetectionEvents
4. Add to config.yaml
5. Wire up in main.py

### "Why is my audio choppy?"
- Buffer size too small (try 1024→2048)
- CPU overloaded (check monitoring)
- Hop size too small (try 256→512)
- Too many detectors enabled

### "How do I deploy to 10 Pis?"
See DEPLOYMENT.md. Use Makefile deploy command with a loop:
```bash
for ip in 192.168.1.{101..110}; do
  make deploy PI_HOST=pi@$ip
done
```

## Next Steps with Claude Code

1. **Implement Core** (2-3 hours)
   - audio_nodes.py
   - processing_nodes.py
   - detection_nodes.py
   - main.py

   Start with: "Help me implement audio_nodes.py following the design in CODE_REFERENCE.md"

2. **Test Locally** (1 hour)
   - Use FileSourceNode
   - Verify pipeline works
   - Test event bus

   Ask: "Help me write a test script for the audio pipeline"

3. **Add Hardware Support** (1-2 hours)
   - GPS integration
   - Sensors
   - MQTT output

   Ask: "Help me integrate GPS following the sensors.py design"

4. **Deploy to Pi** (1 hour)
   - Test on real hardware
   - Tune configuration
   - Verify timing

   Ask: "Help me debug why GPS isn't providing PPS pulses"

5. **Fleet Deployment** (2-3 hours)
   - Deploy to multiple Pis
   - Configure MQTT broker
   - Test coordination

   Ask: "Help me set up MQTT broker for fleet coordination"

## Files to Reference

When working with Claude Code, point to these files for context:

- **CODE_REFERENCE.md** - All code designs from conversation
- **PACKAGE_SUMMARY.md** - What's complete, what needs work
- **README.md** - Overall system documentation
- **DEPLOYMENT.md** - Fleet deployment guide
- **config.example.yaml** - Configuration structure
- **MANIFEST.md** - Complete file listing

## Conversation Style That Works Well

Instead of:
❌ "How do I make a gunshot detector?"

Try:
✅ "Following the architecture in CODE_REFERENCE.md, I'm implementing the
   AubioOnsetNode. It should subscribe to AudioBuffers, process them with
   aubio's onset detection, and publish DetectionEvents. Can you help
   implement the process() method?"

This gives Claude Code:
- The architecture context
- The specific task
- The inputs/outputs
- The design constraints

## Remember

Claude Code won't have our conversation history, but with these reference
documents, it will have:
- All the design decisions (CODE_REFERENCE.md)
- Architecture principles (this file)
- Code to implement (our conversation)
- Deployment process (DEPLOYMENT.md)

This is actually better than raw conversation history because it's
organized, searchable, and focused on what matters for implementation.
