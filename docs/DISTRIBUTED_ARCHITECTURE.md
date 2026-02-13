# Distributed Architecture Guide

## Overview

The gunshot detection system uses a **distributed event-driven architecture** where:
- Each Raspberry Pi node operates **independently**
- MQTT provides **network-level coordination**
- A central server **aggregates data** for trilateration

## Key Architectural Principles

### 1. Local Event Bus (Process-Internal)

Each node has its own **in-process event bus**:

```
Pi Node #1
┌────────────────────────────────────┐
│  Process Boundary                  │
│                                    │
│  ┌──────────────────────┐          │
│  │   Local Event Bus    │          │
│  │   (Thread-safe)      │          │
│  └──────────────────────┘          │
│      ↑    ↑    ↑    ↑              │
│      │    │    │    │              │
│   Aubio  ML  GPS  Monitor          │
│      ↓    ↓    ↓    ↓              │
│         MQTT Output ────────────────┼──→ Network
│                                    │
└────────────────────────────────────┘
```

**Why local event bus?**
- ✅ Fast (no network overhead)
- ✅ Decoupled components
- ✅ Easy to add new consumers
- ✅ Works even if network fails

### 2. MQTT as Network Layer

MQTT connects all nodes:

```
┌─────────┐     ┌─────────┐     ┌─────────┐
│ Node 1  │     │ Node 2  │     │ Node 3  │
│ (Pi #1) │     │ (Pi #2) │     │ (Pi #3) │
└────┬────┘     └────┬────┘     └────┬────┘
     │               │               │
     └───────────────┼───────────────┘
                     ↓
           ┌──────────────────┐
           │   MQTT Broker    │
           │  (Mosquitto)     │
           └──────────────────┘
                     ↓
         ┌───────────┴───────────┐
         ↓                       ↓
  ┌─────────────┐         ┌─────────────┐
  │Trilateration│         │  Dashboard  │
  │   Server    │         │   Web UI    │
  └─────────────┘         └─────────────┘
```

**Why MQTT?**
- ✅ Lightweight pub/sub protocol
- ✅ Perfect for IoT/distributed systems
- ✅ QoS levels for reliability
- ✅ One-to-many (broadcast to fleet)
- ✅ Persistent connections with auto-reconnect

### 3. Event Flow

**Detection event flow:**

```
Audio → Detection → Local Event Bus → MQTT Output → MQTT Broker
                         ↓
                   (also goes to)
                         ↓
              Local File Logger, etc.
```

**Why this architecture?**
1. Components on same node communicate via event bus (fast, local)
2. MQTT Output bridges local bus to network
3. Network failures don't affect local processing
4. Can add local consumers without network impact

## Data Flow Example

### Scenario: Gunshot Detected by 3 Nodes

**Time T=0: Gunshot occurs**

**Time T+10ms: All 3 nodes detect**

```
Node 1 (37.7749, -122.4194)
├─ Aubio detects onset
├─ Publishes to local event bus
├─ MQTTOutput receives event
└─ Publishes to broker: {
      "node_id": "node_001",
      "timestamp": 1707436789.123456,
      "location": {"lat": 37.7749, "lon": -122.4194},
      "detection": {"type": "aubio_complex", "confidence": 0.95}
    }

Node 2 (37.7750, -122.4190)
├─ Same process
└─ Publishes to broker: {
      "node_id": "node_002",
      "timestamp": 1707436789.123461,  # 5 μs later!
      "location": {"lat": 37.7750, "lon": -122.4190},
      "detection": {"type": "aubio_complex", "confidence": 0.92}
    }

Node 3 (37.7748, -122.4190)
├─ Same process
└─ Publishes to broker: {
      "node_id": "node_003",
      "timestamp": 1707436789.123458,  # 2 μs later
      "location": {"lat": 37.7748, "lon": -122.4190},
      "detection": {"type": "aubio_complex", "confidence": 0.89}
    }
```

**Time T+50ms: Broker receives all 3 messages**

```
MQTT Broker
├─ Receives message from node_001
├─ Receives message from node_002
├─ Receives message from node_003
└─ Publishes all to subscribers
```

**Time T+100ms: Trilateration server processes**

```
Trilateration Server
├─ Subscribes to "gunshot/detections"
├─ Collects all detections within 50ms window
├─ Sees 3 detections with time differences:
│  - node_001: T+0 μs
│  - node_003: T+2 μs (2 μs later)
│  - node_002: T+5 μs (5 μs later)
├─ Uses TDOA (Time Difference of Arrival) algorithm
├─ Calculates gunshot position
└─ Publishes result: {
      "timestamp": 1707436789.123456,
      "location": {"lat": 37.7749, "lon": -122.4192},
      "confidence": 0.85,
      "contributing_nodes": ["node_001", "node_002", "node_003"]
    }
```

## MQTT Topic Structure

### Publishing Topics (Nodes → Broker)

```
gunshot/
├── detections                          # All detections (for trilateration)
├── node_001/
│   ├── detections                      # Node-specific detections
│   ├── health                          # CPU, memory, disk stats
│   └── status                          # online/offline status
├── node_002/
│   ├── detections
│   ├── health
│   └── status
└── node_003/
    ├── detections
    ├── health
    └── status
```

### Subscribing Topics (Consumers)

**Trilateration Server:**
```python
# Subscribe to all detections
client.subscribe("gunshot/detections", qos=1)

# Or subscribe to all nodes
client.subscribe("gunshot/+/detections", qos=1)
```

**Fleet Monitor Dashboard:**
```python
# Subscribe to everything
client.subscribe("gunshot/#", qos=1)
```

**Individual Node Manager:**
```python
# Subscribe to specific node
client.subscribe("gunshot/node_001/#", qos=1)
```

## QoS (Quality of Service) Levels

**QoS 0 - At most once (fire and forget)**
- Fastest
- No guarantees
- Use for: Health metrics (ok to lose occasional update)

**QoS 1 - At least once (acknowledged)**
- Reliable
- May receive duplicates
- Use for: **Detection events** (recommended)

**QoS 2 - Exactly once (guaranteed)**
- Slowest but most reliable
- No duplicates
- Use for: Critical commands

**Our choice:** QoS 1 for detections
- Fast enough
- Reliable enough
- Duplicates are ok (trilateration can filter)

## Message Format

### Detection Message

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
    "buffer_index": 12345,
    "metadata": {
      "method": "complex",
      "threshold": 0.3
    }
  },
  "environment": {
    "temperature": 20.5,
    "humidity": 45.2,
    "pressure": 1013.25
  },
  "system": {
    "cpu_temp": 45.2,
    "uptime": 86400
  }
}
```

### Health Message

```json
{
  "node_id": "gunshot_001",
  "timestamp": 1707436789.0,
  "type": "health",
  "data": {
    "cpu_percent": 25.3,
    "cpu_temp": 45.2,
    "memory_percent": 42.1,
    "disk_percent": 55.0,
    "uptime": 86400
  }
}
```

## Failure Modes & Resilience

### Network Partition

**Scenario:** Node loses connection to broker

**Behavior:**
```
Node 1
├─ Local processing continues ✅
├─ Detections published to local event bus ✅
├─ Local file logger saves events ✅
├─ MQTT publish fails ❌
├─ MQTTOutput auto-reconnects in background ✅
└─ When reconnected, resumes publishing ✅
```

**Result:** No detections lost locally, just delayed to network

### Broker Failure

**Scenario:** MQTT broker crashes

**All Nodes:**
```
├─ Local processing continues ✅
├─ Local logging continues ✅
├─ MQTT publishes fail ❌
└─ Auto-reconnect when broker restarts ✅
```

**Trilateration:**
```
├─ No new detections received ❌
└─ Resumes when broker restarts ✅
```

**Result:** Temporary loss of coordination, but nodes keep working

### Single Node Failure

**Scenario:** One Pi crashes

**Healthy Nodes:**
```
├─ Continue normal operation ✅
├─ Trilateration still works with remaining nodes ✅
└─ (3+ nodes recommended for accuracy)
```

**Failed Node:**
```
├─ Stops publishing "online" status
├─ Fleet monitor detects absence
└─ Sends alert to admin
```

**Result:** Graceful degradation, fleet continues working

## Deployment Patterns

### Pattern 1: Single MQTT Broker

```
All Nodes → Single Broker → All Consumers
```

**Pros:**
- Simple
- Easy to manage
- Low cost

**Cons:**
- Single point of failure
- Limited scalability

**Use when:** <20 nodes, reliable network

### Pattern 2: Clustered Broker

```
All Nodes → Broker Cluster → All Consumers
           (3-5 brokers)
```

**Pros:**
- High availability
- Load balancing
- Auto-failover

**Cons:**
- More complex
- Higher cost

**Use when:** >20 nodes, mission-critical

### Pattern 3: Hierarchical (Edge + Cloud)

```
Nodes 1-10 → Edge Broker 1 ─┐
Nodes 11-20 → Edge Broker 2 ─┼→ Cloud Broker → Consumers
Nodes 21-30 → Edge Broker 3 ─┘
```

**Pros:**
- Scalable to 100s of nodes
- Local resilience
- Reduced cloud bandwidth

**Cons:**
- Most complex
- Multiple failure points

**Use when:** >50 nodes, geographically distributed

## Testing the Distributed System

### Local Testing (Single Machine)

```bash
# Terminal 1: Start Mosquitto broker
mosquitto -v

# Terminal 2: Start coordinator
python examples/distributed_example.py coordinator localhost

# Terminal 3: Start node 1
python examples/distributed_example.py node node_001 test.wav localhost

# Terminal 4: Start node 2
python examples/distributed_example.py node node_002 test.wav localhost

# Terminal 5: Start node 3
python examples/distributed_example.py node node_003 test.wav localhost
```

You'll see:
- Nodes publishing detections
- Coordinator receiving from all nodes
- Trilateration candidates identified

### Network Testing (Multiple Machines)

```bash
# Server: Start broker
mosquitto -v

# Pi 1:
python main.py --config config.yaml

# Pi 2:
python main.py --config config.yaml

# Pi 3:
python main.py --config config.yaml

# Each Pi has config.yaml with:
# - Unique node_id
# - Same broker IP
# - GPS coordinates
```

### Monitoring Tools

**MQTT Explorer (GUI):**
- Download: http://mqtt-explorer.com/
- Connect to broker
- See all topics and messages in real-time

**Mosquitto CLI:**
```bash
# Subscribe to all topics
mosquitto_sub -h broker_ip -t '#' -v

# Subscribe to just detections
mosquitto_sub -h broker_ip -t 'gunshot/detections' -v

# Publish test message
mosquitto_pub -h broker_ip -t 'test' -m 'Hello'
```

## Security Considerations

### Basic Security (Minimum)

```yaml
# config.yaml
output:
  mqtt:
    username: "gunshot_node"
    password: "secure_password_here"
```

```bash
# Broker: Add password file
mosquitto_passwd -c /etc/mosquitto/passwd gunshot_node

# Restart broker
sudo systemctl restart mosquitto
```

### TLS/SSL Encryption

```yaml
# config.yaml
output:
  mqtt:
    port: 8883  # TLS port instead of 1883
    tls:
      ca_certs: "/path/to/ca.crt"
      certfile: "/path/to/client.crt"
      keyfile: "/path/to/client.key"
```

### Best Practices

1. ✅ Always use authentication (username/password minimum)
2. ✅ Use TLS for production deployments
3. ✅ Unique credentials per node
4. ✅ Firewall MQTT port (1883/8883)
5. ✅ Use VPN for inter-site communication
6. ✅ Regular credential rotation

## Performance Tuning

### Broker Configuration

```conf
# /etc/mosquitto/mosquitto.conf

# Increase max connections
max_connections 1000

# Increase message queue
max_queued_messages 1000

# Optimize for small messages
max_packet_size 1024

# Enable persistence
persistence true
persistence_location /var/lib/mosquitto/
```

### Node Configuration

```yaml
# config.yaml
output:
  mqtt:
    qos: 1              # Good balance
    keepalive: 60       # Heartbeat interval
    reconnect_delay: 5  # Seconds between reconnect attempts
```

## Summary

**Local Event Bus:**
- In-process communication
- Fast, reliable
- Works offline

**MQTT:**
- Network coordination
- Pub/sub architecture
- Auto-reconnect
- QoS for reliability

**Result:**
- Resilient to network failures
- Scales to 100+ nodes
- Easy to add consumers
- Simple to monitor and debug
