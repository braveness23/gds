# Trilateration Algorithm Guide

## Overview

The trilateration server calculates the location of sound sources (gunshots, thunder, explosions) by analyzing the **time differences** in which different sensors detect the same event.

## Key Concepts

### TDOA (Time Difference of Arrival)

Unlike GPS trilateration which uses absolute distances, we use **time differences**:

```
Gunshot at unknown location
        ↓
    (sound wave travels)
        ↓
    ┌───┴───┬───────┐
    ↓       ↓       ↓
Node 1   Node 2   Node 3
T+0ms    T+5ms    T+3ms
```

**Why time differences?**
- We don't know the exact time the sound was created
- We only know when each sensor heard it
- The **differences** between arrival times tell us relative distances

### The Math

Given:
- Sensor positions: P₁, P₂, P₃, ... Pₙ
- Detection times: t₁, t₂, t₃, ... tₙ
- Speed of sound: v = 343 m/s

Find:
- Source position: S

The time difference between sensor i and sensor 1:
```
Δtᵢ = tᵢ - t₁
```

The distance difference:
```
Δdᵢ = Δtᵢ × v
```

This means:
```
|S - Pᵢ| - |S - P₁| = Δdᵢ
```

This defines a **hyperbola** in 2D (hyperboloid in 3D) where the source could be located.

With multiple sensors, the hyperbolas intersect at the source location.

## Implementation Details

### 1. Coordinate Conversion

**Problem:** GPS gives lat/lon, but math needs meters.

**Solution:** Convert to local XYZ coordinates:

```python
# Meters per degree
lat_m = 111132.92  # ~constant
lon_m = 111132.92 * cos(latitude)  # varies with latitude

# Convert (using first sensor as origin)
x = (lon - lon_ref) * lon_m
y = (lat - lat_ref) * lat_m
z = alt - alt_ref
```

**Accuracy:** Good for ~100km radius. For larger areas, use proper map projection (UTM).

### 2. Least Squares Solution

We have more equations than unknowns → use **least squares**.

Build matrix equation: **A × x = b**

Where:
- x = source position [x, y, z]
- A = matrix of sensor differences
- b = vector of distance differences

```python
# For each sensor pair (i, ref):
A[i] = 2 * (Pᵢ - P_ref)
b[i] = Δdᵢ² - |Pᵢ - P_ref|² + |P_ref|² - |Pᵢ|²

# Solve
x = (AᵀA)⁻¹Aᵀb
```

**Why least squares?**
- Handles noise in measurements
- Uses all sensors (not just 3)
- Gives best fit when data is imperfect

### 3. Geometry Evaluation

**Good geometry:**
```
    Node 2
      ↑
      |
Node 1 ← → Node 3
```
Sensors spread out in different directions.

**Bad geometry:**
```
Node 1 — Node 2 — Node 3
```
Sensors in a line (poor precision perpendicular to line).

**How we measure:**
```python
# Calculate convex hull area
# Larger area = better geometry
geometry_score = hull_area / (avg_sensor_spacing²)
```

Score ranges 0-1:
- < 0.1: Poor (reject)
- 0.1-0.5: Acceptable
- 0.5-0.8: Good
- 0.8-1.0: Excellent

### 4. Event Classification

Based on **time window** (time between first and last detection):

```
< 100ms:    Gunshot (local, ~34m max distance)
< 500ms:    Explosion (nearby, ~170m)
< 2s:       Thunder (near, ~680m)
< 10s:      Thunder (distant, ~3.4km)
> 10s:      Thunder (very distant, >3.4km)
```

**Why this matters:**
- Different events need different time windows
- Gunshot: expect tight timing (few ms)
- Thunder: can be many seconds apart at distant nodes

### 5. Confidence Calculation

Overall confidence is weighted average of:

**Number of sensors (20%):**
```
3 sensors: 0.5
4 sensors: 0.75
5+ sensors: 1.0
```

**Detection confidence (30%):**
```
Average of individual detector confidences
```

**Geometry score (20%):**
```
Quality of sensor arrangement (0-1)
```

**Residual error (20%):**
```
residual_factor = 1 / (1 + error/10m)
```

**Time consistency (10%):**
```
< 100ms: 1.0 (excellent)
< 1s: 0.9 (good)
< 5s: 0.8 (acceptable)
> 5s: 0.7 (long window - thunder)
```

## Configurable Time Window

### Why It Matters

**Speed of sound:** ~343 m/s

**Example scenarios:**

**Gunshot (close range):**
```
Sensor spacing: 100m
Max time difference: 100m / 343m/s = 0.29s
Window needed: ~0.5s (with margin)
```

**Thunder (distant):**
```
Sensor spacing: 1000m
Lightning 5km away
Max time difference: (5000m + 1000m) / 343m/s = 17.5s
Window needed: ~30s (with margin)
```

**Setting the window:**
```bash
# For gunshots only (local events)
python trilateration_server.py --time-window 2.0

# For thunder and distant events (default)
python trilateration_server.py --time-window 30.0

# For very distant thunder (10km+)
python trilateration_server.py --time-window 60.0
```

### How It Works

**Detection grouping algorithm:**

```python
# Sort all detections by time
sorted_detections = sorted(buffer, key=lambda d: d.timestamp)

# Find groups within time window
for detection in sorted_detections:
    group = [detection]

    # Find all detections within window
    for other in sorted_detections:
        time_diff = abs(other.timestamp - detection.timestamp)

        if time_diff <= time_window:
            if other.node_id not in group.node_ids:
                group.append(other)

    # Process group if enough nodes
    if len(group) >= min_nodes:
        trilaterate(group)
```

**Key points:**
- Same node can't contribute twice to same event
- Window slides to find all possible groups
- Groups are processed independently

## Error Sources & Mitigation

### 1. Timing Errors

**Source:** Clock sync between nodes

**Impact:**
- 1ms error = 0.34m position error
- 10ms error = 3.4m position error

**Mitigation:**
- GPS PPS for <1μs sync
- System clock already GPS-disciplined
- Use multiple nodes (errors average out)

### 2. Speed of Sound Variation

**Temperature effect:**
```
0°C:  v = 331 m/s
20°C: v = 343 m/s
40°C: v = 355 m/s
```

**Impact:**
- 20°C error = 3.6% distance error
- At 1km: ~36m position error

**Mitigation:**
```python
# Update speed based on temperature
engine.update_speed_of_sound(temperature=25.0)

# Or calculate from environmental data
v = 331.3 + (0.606 * temp_celsius)
```

### 3. Multipath Reflections

**Problem:** Sound bounces off buildings/terrain

**Effect:**
- Delayed arrival times
- Appear to come from wrong direction

**Mitigation:**
- Use earliest detection (direct path usually first)
- Geometry score filters bad configurations
- Residual error indicates multipath (high error = reject)

### 4. Wind

**Effect:** Sound travels faster downwind, slower upwind

**Impact:**
- 10 m/s wind = ~3% speed change
- At 1km: ~30m error

**Mitigation:**
- For precision, measure wind
- Adjust speed of sound per direction
- Or accept as inherent limitation

### 5. Node Position Errors

**GPS accuracy:** ±2-5m typical

**Impact:**
- Position error propagates to result
- Multiple nodes average out some error

**Mitigation:**
- Use RTK GPS for <0.1m accuracy
- Survey node positions precisely
- Or accept GPS accuracy as limit

## Practical Example

### Scenario: Thunder Strike

**Setup:**
```
Node 1: (37.7749, -122.4194, 10m)  [San Francisco]
Node 2: (37.7750, -122.4190, 10m)  [50m east]
Node 3: (37.7748, -122.4190, 10m)  [50m south-east]

Lightning strikes at: (37.7755, -122.4185, 500m)  [~700m away]
```

**Detection times:**
```
Sound travel time to each node:
Node 1: 700m / 343m/s = 2.041s
Node 2: 670m / 343m/s = 1.953s
Node 3: 680m / 343m/s = 1.982s

If thunder occurred at T=0:
Node 2 detects at T+1.953s (earliest)
Node 3 detects at T+1.982s (+29ms)
Node 1 detects at T+2.041s (+88ms)
```

**Time window needed:**
```
Δt = 2.041s - 1.953s = 88ms

With margin: 500ms window is sufficient
But we use 30s to be safe for distant thunder
```

**Trilateration:**
```python
detections = [
    Detection(node_2, t=100.000, lat=37.7750, lon=-122.4190),
    Detection(node_3, t=100.029, lat=37.7748, lon=-122.4190),
    Detection(node_1, t=100.088, lat=37.7749, lon=-122.4194)
]

result = engine.trilaterate(detections)

# Result:
# Location: (37.7755, -122.4185, 500m)
# Confidence: 0.85
# Event type: "thunder_near"
# Time window: 0.088s
# Geometry score: 0.65
# Residual error: 12.3m
```

## Advanced: 3D Trilateration

Currently we solve in 3D (x, y, z) but altitude is less reliable because:

1. **Most sensors at similar altitude** (ground level)
   - Poor vertical geometry
   - Altitude has higher uncertainty

2. **Sound speed varies with altitude** (temperature, pressure change)

**For ground events** (gunshots): altitude is approximately sensor altitude

**For aerial events** (thunder, aircraft): altitude can be estimated but with high uncertainty

**To improve altitude accuracy:**
- Deploy sensors at different elevations
- Use atmospheric model for sound speed variation
- Cross-check with other data (radar, visual)

## Performance Characteristics

**Computational complexity:**
- O(n) for each sensor
- Matrix solve: O(n³) but n is small (<10)
- Fast enough for real-time

**Typical processing time:**
- 3 nodes: <1ms
- 10 nodes: <5ms
- 100 nodes: <100ms

**Accuracy (theoretical):**
```
Sensor spacing: 100m
Clock sync: 1μs
Geometry: good (score > 0.5)

Expected accuracy: <10m
```

**Accuracy (practical):**
```
With GPS PPS timing
Environmental factors
Typical geometry

Expected accuracy: 10-50m
```

## Tuning for Your Deployment

### Gunshot Detection (Close Range)

```bash
python trilateration_server.py \
    --time-window 2.0 \
    --min-nodes 3 \
    --max-nodes 5 \
    --speed-of-sound 343.0
```

Settings:
- Short window (2s) for local events
- Minimum 3 nodes for basic trilateration
- Use best 5 nodes if more available

### Thunder Detection (Long Range)

```bash
python trilateration_server.py \
    --time-window 30.0 \
    --min-nodes 4 \
    --max-nodes 10 \
    --speed-of-sound 343.0
```

Settings:
- Long window (30s) for distant events
- Prefer more nodes for distant events
- Use up to 10 nodes for best accuracy

### Mixed Deployment

```bash
python trilateration_server.py \
    --time-window 30.0 \
    --min-nodes 3 \
    --max-nodes 8
```

Settings:
- Long window catches both local and distant
- Algorithm classifies event type automatically
- Works for gunshots AND thunder

## Validation & Testing

### Synthetic Data Test

```python
# Create known positions
nodes = [
    (37.7749, -122.4194, 10),
    (37.7750, -122.4190, 10),
    (37.7748, -122.4190, 10)
]

# Known source
source = (37.7755, -122.4185, 100)

# Calculate expected times
for node in nodes:
    distance = haversine(node, source)
    time = distance / 343.0
    create_detection(node, time)

# Run trilateration
result = trilaterate(detections)

# Compare result to source
error = haversine(result.position, source)
print(f"Error: {error:.1f}m")
```

### Field Testing

1. **Known location test:** Shoot at surveyed position, verify result
2. **Multiple shot test:** Fire from different locations, verify accuracy
3. **Range test:** Measure accuracy vs distance
4. **Geometry test:** Add/remove nodes, measure impact

## Future Enhancements

**Kalman filtering:** Track moving sources (vehicles, aircraft)

**Bayesian estimation:** Incorporate prior knowledge of likely locations

**Machine learning:** Learn corrections for local environment

**Sensor fusion:** Combine with video, radar, seismic data

**Atmospheric modeling:** Accurate sound speed vs altitude/temperature

**Multipath mitigation:** Advanced filtering of reflected signals
