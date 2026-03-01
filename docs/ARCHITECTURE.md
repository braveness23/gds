# Architecture Guide

> **TL;DR:** Each Pi node runs an independent event-driven pipeline (Audio → Detect → Event Bus → MQTT). A central trilateration server collects timestamps from all nodes and computes gunshot position using TDOA (Time Difference of Arrival).

---

## System Overview

The system is **distributed** and **event-driven**:

- Each Raspberry Pi operates independently — network failures don't stop local detection
- MQTT provides fleet coordination between nodes
- A central trilateration server aggregates detections for positioning

```
┌─────────────────┐
│  Audio Source   │  (I2S/ALSA microphone)
│  + GPS/PPS      │
│  + Env Sensors  │
└────────┬────────┘
         ▼
┌─────────────────┐
│   Processing    │  (HPF filter, mono conversion, gain)
└────────┬────────┘
         ▼
┌─────────────────┐
│   Detectors     │  (Aubio onset, threshold)
└────────┬────────┘
         ▼
┌─────────────────┐
│   Event Bus     │  (in-process pub/sub, thread-safe)
└────────┬────────┘
         ▼
┌─────────────────┐
│    Outputs      │  (MQTT)
└─────────────────┘
         │ MQTT
         ▼
┌──────────────────────────────────────┐
│              MQTT Broker             │
└──────────┬───────────────────────────┘
           ▼                       ▼
  ┌─────────────────┐    ┌──────────────────┐
  │ Trilateration   │    │  Dashboard /     │
  │    Server       │    │  Fleet Monitor   │
  └─────────────────┘    └──────────────────┘
```

---

## Local Event Bus

Each node has an in-process event bus (`src/core/event_bus.py`) that decouples components:

- **Fast** — no network overhead
- **Resilient** — works even when MQTT is down
- **Extensible** — add new consumers (file loggers, monitors) without modifying producers

**Event types:** `DETECTION`, `SYSTEM`, `TIMING`, `HEALTH`, `CONFIG`

The MQTT output node bridges the local event bus to the network.

---

## MQTT Network Layer

MQTT connects all nodes to central services:

```
Node 1 ──┐
Node 2 ──┼──→  MQTT Broker  ──→  Trilateration Server
Node 3 ──┘                  └──→  Dashboard
```

**QoS levels in use:**
- QoS 0 — Health metrics (ok to lose occasional update)
- QoS 1 — Detection events (reliable, duplicates tolerated)
- QoS 2 — Critical commands (exactly once)

### Topic Structure

```
gunshot/
├── detections                      # All detections (for trilateration)
├── <node_id>/
│   ├── detections                  # Node-specific detections
│   ├── health                      # CPU, memory, disk stats
│   └── status                      # online/offline
```

### Detection Message Format

```json
{
  "node_id": "gunshot_001",
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

## Failure Resilience

| Failure | Impact | Recovery |
|---------|--------|----------|
| Network partition | MQTT publish fails | Auto-reconnect; local detection continues |
| Broker crash | No fleet coordination | All nodes resume when broker restarts |
| Single node crash | Reduced trilateration accuracy | Remaining nodes continue; fleet monitor detects absence |

---

## Deployment Patterns

| Pattern | Nodes | Use When |
|---------|-------|----------|
| Single broker | < 20 | Reliable local network |
| Clustered broker | 20–100 | Mission-critical, HA required |
| Hierarchical (edge + cloud) | > 50 | Geographically distributed |

---

## TDOA Trilateration Algorithm

> **TL;DR:** Nodes timestamp detections with GPS-synchronized clocks. Time differences between nodes define hyperbolas. Intersections give gunshot position.

### Key Concepts

**Why time differences, not absolute distances?**
We don't know when the sound was created — only when each node heard it. The *differences* between arrival times define relative distances.

**Math:**
```
Speed of sound: v = 343 m/s (varies with temperature)
Time difference:  Δtᵢ = tᵢ - t_ref
Distance diff:    Δdᵢ = Δtᵢ × v

Constraint:  |S - Pᵢ| - |S - P_ref| = Δdᵢ
```

Each node pair defines a **hyperbola** (2D) or **hyperboloid** (3D). With 3+ nodes, intersections converge on the source.

### Implementation

**1. Coordinate conversion** — GPS lat/lon → local XY meters (uses first node as origin)

**2. Least-squares solution** — build matrix equation `A×x = b` for all node pairs, solve with `(AᵀA)⁻¹Aᵀb`

**3. Geometry evaluation** — convex hull area of sensor array; good geometry (spread out) increases accuracy; linear arrangements are poor

**4. Event classification by time window:**

| Window | Event Type |
|--------|------------|
| < 100ms | Gunshot (local, ~34m max distance) |
| < 500ms | Explosion (nearby) |
| < 2s | Thunder (near) |
| < 10s | Thunder (distant) |
| > 10s | Thunder (very distant) |

**5. Confidence score** — weighted average of: sensor count (20%), detection confidence (30%), geometry score (20%), residual error (20%), time consistency (10%)

### Accuracy

| Factor | Impact | Mitigation |
|--------|--------|------------|
| Clock sync | 1ms error = 0.34m position error | GPS PPS → < 1μs |
| Temperature | 20°C error = 36m/km | Environmental sensors |
| Audio buffer timing | 1–10ms (dominant error) | Timestamp at callback |
| GPS position | ±2–5m | RTK GPS for < 1cm |
| Multipath | Delayed arrivals | Use earliest detection; filter by residual error |

**Practical accuracy with GPS PPS:** 10–50m

### Trilateration Server Config

```bash
# Gunshot detection (close range)
python scripts/trilateration_server.py --time-window 2.0 --min-nodes 3

# Thunder detection (long range)
python scripts/trilateration_server.py --time-window 30.0 --min-nodes 4

# Mixed deployment
python scripts/trilateration_server.py --time-window 30.0 --min-nodes 3
```

### Speed of Sound Correction

```python
# Update based on environmental sensor data
v = 331.3 + (0.606 * temp_celsius)            # simple
v = 331.3 * sqrt(1 + temp/273.15) * sqrt(1 + 0.0124 * humidity/100)  # accurate

engine.update_speed_of_sound(temperature=25.0)
```

---

## Security

| Layer | Minimum | Production |
|-------|---------|------------|
| MQTT auth | Username/password | TLS + client certificates |
| Per-node credentials | Unique credentials per node | PKI with rotation |
| Network | Firewall MQTT port (1883/8883) | VPN for inter-site |

See `docs/DEVELOPMENT.md` → Security Audit for open items.
