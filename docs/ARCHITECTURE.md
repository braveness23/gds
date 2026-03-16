# Architecture

> **TL;DR:** A strix node is a self-contained acoustic sensor that detects events and timestamps them with GPS-disciplined precision. A parliament is a network of nodes. A central fusion server collects TDOA measurements from all nodes and computes the sound source location.

*A single node is a strix. A network is a parliament.*

---

## What strix does

strix turns any collection of audio-capable devices into a distributed acoustic intelligence system. Each node:

1. Captures audio continuously
2. Detects acoustic events (gunshots, explosions, thunder)
3. Timestamps the detection with GPS-disciplined precision (< 1μs with PPS)
4. Publishes the timestamp and location to a shared MQTT broker

A parliament fusion server:
1. Collects detections from all nodes
2. Groups detections by time proximity
3. Solves the TDOA system to find the sound source
4. Publishes a `TriangulationResult` with coordinates and confidence

---

## System overview

```
┌─────────────────────────────────────────────────────────────┐
│  SENSOR LAYER — each strix node                             │
│                                                             │
│  Microphone ──▶ Audio Pipeline ──▶ Detector ──▶ Event Bus  │
│                                                    │        │
│  GPS/PPS ──▶ NTPClock ──▶ MQTT Output ────────────┘        │
│              (stratum 1)                                    │
└───────────────────────────┬─────────────────────────────────┘
                            │ MQTT  (gunshot/detections)
┌───────────────────────────▼─────────────────────────────────┐
│  FUSION LAYER — parliament server                           │
│                                                             │
│  TrilaterationServer ──▶ group by time window               │
│                        ──▶ TDOA solve                       │
│                        ──▶ TriangulationResult              │
│                        ──▶ publish result                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Single-node process boundary

```
┌────────────────────────────────────────────────────────────────┐
│  strix Node Process                                            │
│                                                                │
│  ALSASourceNode ──▶ HighPassFilter ──▶ BufferSplitter         │
│                                              │                 │
│                              ┌───────────────┴──────────┐     │
│                              ▼                          ▼     │
│                       AubioOnsetNode          ThresholdNode   │
│                              │                          │     │
│                              └─────────┬────────────────┘     │
│                                        ▼                      │
│                                    EventBus                   │
│                              (queue + dispatch thread)        │
│                                        │                      │
│                     ┌──────────────────┼──────────────┐      │
│                     ▼                  ▼               ▼      │
│               MQTTOutputNode   SystemMonitor   FileLoggerNode  │
│                     │                                          │
└─────────────────────┼──────────────────────────────────────────┘
                      │ paho-mqtt (network)
                      ▼
                 MQTT Broker
```

**Why two layers?**
- **Local event bus:** Zero network overhead; works when MQTT is down; decouples detectors from outputs
- **MQTT:** Fleet-wide broadcast; auto-reconnect; QoS delivery guarantees

---

## Package structure

| Package | What it does |
|---------|-------------|
| `src/core/` | `EventBus`, `EventType`, `Event` — the in-process pub/sub backbone |
| `src/audio/` | Audio sources (`ALSASourceNode`, `FileSourceNode`) and the `AudioNode` base |
| `src/processing/` | Signal filters: HPF, gain, mono conversion, buffer splitter |
| `src/detection/` | `AubioOnsetNode` (primary detector), `ThresholdDetectorNode` |
| `src/output/` | `MQTTOutputNode`, `FileLoggerNode`, `BufferSaverNode` |
| `src/sensors/` | `GPSReader`, `StaticGPSDevice`, `MockGPSDevice`, environmental sensors |
| `src/timing/` | `NTPClock` — monitors NTP offset, fires TIMING events when drift is high |
| `src/monitoring/` | `SystemMonitorNode` — CPU, memory, disk, temperature via psutil |
| `src/remote_config/` | MQTT-based remote configuration with HMAC auth and safety checks |
| `src/trilateration/` | `TrilaterationEngine` (pure math), `TrilaterationServer` (MQTT integration) — coming from `feat/framework-extraction` |
| `src/classification/` | `AcousticClassifier` plugin interface — coming from `feat/framework-extraction` (not yet merged) |
| `src/config/` | `Config` — YAML/JSON config with dot-notation and deep merge |

---

## Full event flow

1. **Audio callback** (`ALSASourceNode._audio_callback`) — timestamp captured first, samples normalized, buffer passed directly to the next pipeline node via method call (no event bus; audio flows through pipeline nodes via direct calls, not events)
2. **High-pass filter** (`HighPassFilterNode`) — attenuates frequencies below ~5kHz, preserving impulsive energy
3. **Buffer splitter** (`BufferSplitterNode`) — fans out audio buffer to all detector subscribers in parallel
4. **Aubio detector** (`AubioOnsetNode`) — detects onset in `hop_size=512` chunks, publishes `DETECTION` event
5. **Event bus** dispatches to all `DETECTION` subscribers
6. **MQTT output** (`MQTTOutputNode`) — enriches with GPS + environmental data, publishes JSON to:
   - `gunshot/detections` (fleet-wide)
   - `gunshot/<node_id>/detections` (node-specific)
7. **Trilateration server** (`TrilaterationServer`) — groups arrivals by time window, solves TDOA, publishes `TriangulationResult` to `gunshot/trilateration/results`

---

## MQTT topic structure

```
gunshot/
├── detections                       # All detections (input to trilateration)
├── trilateration/results            # Solved positions from fusion server
├── <node_id>/
│   ├── detections                   # Node-specific detections
│   ├── health                       # CPU, memory, disk, temperature
│   └── status                       # online / offline
│
└── config/                          # Remote configuration (remote_config module)
    ├── <node_id>/set
    ├── <node_id>/status
    └── <node_id>/confirm
```

### Detection message format

```json
{
  "node_id": "strix-001",
  "timestamp": 1707436789.123456,
  "location": {
    "latitude": 37.7749,
    "longitude": -122.4194,
    "altitude": 10.5,
    "fix_quality": 2,
    "satellites": 8
  },
  "detection": {
    "detector_type": "aubio_complex",
    "confidence": 0.95,
    "buffer_index": 12345
  },
  "environment": {
    "temperature": 20.5,
    "humidity": 45.2,
    "pressure": 1013.25
  }
}
```

---

## TDOA trilateration algorithm

> **TL;DR:** Nodes timestamp detections with GPS-synchronized clocks. Time differences between nodes constrain the source to a hyperboloid for each pair. With 3+ nodes, the intersection gives source position.

**Why time differences, not absolute distances?**
We don't know when the sound was created — only when each node heard it. The *differences* between arrival times define relative distances.

```
Speed of sound: v = 343 m/s (varies with temperature)
Time difference: Δtᵢ = tᵢ - t_ref
Distance diff:   Δdᵢ = Δtᵢ × v

Constraint: |S - Pᵢ| - |S - P_ref| = Δdᵢ
```

**Implementation steps:**

1. **Coordinate conversion** — GPS lat/lon → local XY meters (equirectangular, origin at first node)
2. **Augmented TDOA system** — builds matrix equation `A·[x,d0]ᵀ = b` treating unknown reference distance `d0` as extra variable; solve with `np.linalg.lstsq`
3. **Geometry evaluation** — convex hull area of sensor array; collinear/clustered nodes score < 0.1 and are rejected
4. **Event classification** by time window:

   | Window | Event Type |
   |--------|------------|
   | < 100ms | Gunshot |
   | < 500ms | Explosion |
   | < 2s | Thunder (near) |
   | < 10s | Thunder (distant) |
   | > 10s | Thunder (very distant) |

5. **Confidence score** — weighted: node count (20%), detection confidence (30%), geometry (20%), residual error (20%), timing (10%)

**Accuracy factors:**

| Factor | Impact | Mitigation |
|--------|--------|------------|
| Clock sync | 1ms error = 0.34m position error | GPS PPS → < 1μs |
| Temperature | 20°C error = 36m/km | Environmental sensors |
| Audio buffer timing | 1–10ms (dominant) | Timestamp at callback entry |
| GPS position | ±2–5m CEP | RTK GPS for < 1cm |

**Practical accuracy with GPS PPS:** 10–50m for gunshots (validated to 17ns clock offset on Pi 3B+).

---

## Timing architecture

GPS PPS is the foundation of trilateration accuracy. Without synchronized clocks, TDOA is meaningless.

```
GPS Module (NMEA + PPS pulse)
    │
    ▼
gpsd (parses NMEA, exposes PPS)
    │
    ▼
chrony (uses PPS as refclock, locks system clock)
    │
    ▼
System clock: < 1μs offset from UTC   ← strix reads this for timestamps
    │
    ▼
NTPClock (monitors offset, fires TIMING events if drift > threshold)
```

**What "stratum 1" means:** A clock disciplined directly by a hardware reference (GPS PPS) is stratum 1. Nodes with GPS PPS are stratum 1. Nodes using NTP-only are stratum 2–4. Only stratum 1 nodes provide the microsecond timing required for meter-level trilateration.

See [GPS_PPS_TIMING.md](GPS_PPS_TIMING.md) for setup, verification commands, and accuracy analysis.

---

## Extension points

### Custom classifier

> `AcousticClassifier` and `ClassificationResult` are being added in the `feat/framework-extraction` branch. After merge they will live in `src/classification/base.py`.

```python
# Available after feat/framework-extraction merges:
# from src.classification.base import AcousticClassifier, ClassificationResult
import numpy as np

class GunVsFireworksClassifier:  # will subclass AcousticClassifier after merge
    def classify(self, audio_buffer: np.ndarray, sample_rate: int,
                 detection_event=None):
        peak = np.max(np.abs(audio_buffer))
        event_type = "gunshot" if peak > 0.8 else "fireworks"
        return {"event_type": event_type, "confidence": 0.75}
```

### Custom output node

Subscribe to `DETECTION` events on the event bus (do not subclass `AudioNode` unless you need raw audio buffer access — see `CONTRIBUTING.md` for both patterns):

```python
from src.core.event_bus import EventBus, EventType

class WebhookOutputNode:
    def __init__(self, url: str, event_bus: EventBus = None):
        self.url = url
        self.logger = logging.getLogger(self.__class__.__name__)
        if event_bus:
            event_bus.subscribe(EventType.DETECTION, self._on_detection)

    def _on_detection(self, event):
        # POST to webhook
        ...
```

### Custom sensor

Subclass `BaseSensor` from `src/sensors/base.py`. See `GPSReader` or `BME280Sensor` for the full pattern.

### Custom simulation scenario

Add an entry to `tests/simulation/scenarios.py` — see the `SCENARIOS` dict. Each scenario needs `nodes`, `events`, `tolerance_meters`, `min_geometry_score`, and `expected_num_results`.

---

## Failure resilience

| Failure | Impact | Recovery |
|---------|--------|----------|
| Network partition | MQTT publish fails | Auto-reconnect; local detection continues |
| Broker crash | No fleet coordination | All nodes resume when broker restarts |
| Single node crash | Reduced trilateration accuracy | Remaining 3+ nodes continue |
| GPS loss | Timestamp accuracy degrades | Falls back to NTP; trilateration less accurate |
| Bad geometry | Engine rejects solve | Returns None; logged; waits for better configuration |

---

## Security

| Layer | Minimum | Production |
|-------|---------|------------|
| MQTT auth | Username/password | TLS + client certificates |
| Per-node credentials | Unique per node | PKI with rotation |
| Remote config | HMAC-SHA256 message authentication | + rate limiting |
| Network | Firewall MQTT port | VPN for inter-site |

See `docs/DEVELOPMENT.md` for open security items.
