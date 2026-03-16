# Quickstart

Get a parliament running in 10 minutes — no hardware needed.

---

## 1. Clone and install

```bash
git clone https://github.com/braveness23/gds.git
cd gds
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

Or with the one-command setup:

```bash
python scripts/setup_dev.py
```

---

## 2. Run the simulation

```bash
python tools/run_simulation.py
```

This starts a simulated 4-node parliament. You'll see output like:

```
[Simulation] Firing event at (37.7745, -122.4190) t=0.000s
[Node node_sw] Detection at t=0.023s  (23ms after event)
[Node node_ne] Detection at t=0.041s  (41ms after event)
[Node node_nw] Detection at t=0.056s  (56ms after event)
[Node node_se] Detection at t=0.063s  (63ms after event)

==================================================
✅ TRILATERATION SUCCESS
Location:   (37.774501, -122.418998)
True:       (37.774500, -122.419000)
Error:      0.3m
Confidence: 87.4%
Geometry:   0.81
==================================================
```

The simulation uses synthetic timestamps with realistic jitter — no microphone or GPS needed.

---

## 3. Try different scenarios

```bash
# 20-node network
python tools/run_simulation.py --scenario large_network

# Node dropout (one dead node)
python tools/run_simulation.py --scenario node_dropout

# Semi-automatic burst (5 rapid shots)
python tools/run_simulation.py --scenario semi_auto_burst

# Poor geometry (collinear nodes — shows graceful degradation)
python tools/run_simulation.py --scenario poor_geometry

# List all scenarios
python tools/run_simulation.py --list
```

---

## 4. Run the test suite

```bash
pytest tests/ -q
```

Should show 459+ passing. The integration tests (tagged `@pytest.mark.integration`) run the full simulation → trilateration pipeline.

---

## 5. What you're seeing

The simulation exercises the exact same code that runs on real hardware:

- `tests/simulation/acoustic_simulator.py` — generates synthetic detection timestamps using Haversine distance + speed of sound + configurable jitter
- `src/trilateration/engine.py` — `TrilaterationEngine` solves the TDOA system (identical code runs on real nodes)
- `tests/simulation/scenarios.py` — scenario definitions with expected accuracy tolerances

The only difference from real hardware: timestamps come from the simulator instead of GPS-disciplined system clocks.

---

## 6. Next steps

| Goal | Where to go |
|------|-------------|
| Deploy on real hardware | [SETUP.md](SETUP.md) |
| Understand the code | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Add a custom classifier | [CONTRIBUTING.md](../CONTRIBUTING.md#adding-a-custom-classifier) |
| Add a simulation scenario | [CONTRIBUTING.md](../CONTRIBUTING.md#adding-a-simulation-scenario) |
| Check project status | [STATUS.md](STATUS.md) |
