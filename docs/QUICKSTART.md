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
python tools/run_simulation.py --scenario basic_4node
```

This runs a simulated 4-node parliament against a single shot at the centre. You'll see output like:

```
╔══════════════════════════════════════════════════════════╗
║          Gunshot Detection — Simulation Runner           ║
╚══════════════════════════════════════════════════════════╝
Seed: 42  |  Scenarios: 1

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📡 Scenario : basic_4node
   4 static nodes ~200m apart in square, single shot at centre
   Nodes    : 4
   Events   : 1
   Tolerance: 5.0 m
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ✅ PASS  shot_001
    True location  : (37.774900, -122.419400)
    Estimated      : (37.774900, -122.419400)
    Position error : 0.00 m  (tolerance: 5.0 m)
    Geometry score : 0.100
    Confidence     : 73.83%
    Nodes used     : 4 (node_beta, node_alpha, node_delta, node_gamma)
    Residual error : 0.00 m
    Event type     : gunshot

  Summary: 1 trilaterated, 0 skipped

════════════════════════════════════════════════════════════
✅  All scenarios PASSED
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

# See all available scenarios
python tools/run_simulation.py --help
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
