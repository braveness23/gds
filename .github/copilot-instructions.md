# GitHub Copilot Instructions for GDS Project

> **About This File**: This document guides how GitHub Copilot assists with this repository. It mirrors the project conventions in [CLAUDE.md](../CLAUDE.md) — keep them in sync.

---

## 📋 Project Overview

**What this project is:**

- Distributed acoustic gunshot detection system using trilateration for Raspberry Pi fleets with GPS/PPS timing

**Project type:**

- Distributed IoT/embedded system (Raspberry Pi deployment, modular event-driven audio processing pipeline)

**Tech stack:**

- **Platform:** Edge nodes are Raspberry Pi 3B+/4/5 (Raspberry Pi OS 64-bit, Linux-native); MQTT brokers can be local, remote, or cloud-hosted; cross-platform support in progress
- **Language:** Python 3.7+
- **Audio:** PyAudio, Aubio (onset detection), ALSA (Linux), soundfile
- **Detection:** Aubio onset detection, simple threshold detection
- **Sensors:** GPS (gpsd with PPS support), BME280/DHT22 environmental sensors
- **Networking:** MQTT (paho-mqtt)
- **Processing:** NumPy, SciPy (filters, trilateration algorithms)
- **Timing:** NTP (ntplib), GPS PPS for microsecond precision
- **Monitoring:** psutil (system health)
- **Testing:** pytest, pytest-cov, pytest-mock
- **Code quality:** black, flake8, mypy

**Current focus:**

- Platform abstraction (making Linux-only code cross-platform - see [docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md))
- Security hardening (credentials, TLS validation, input validation - see [docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md))
- Code quality improvements (type hints, exception handling, imports)

---

## 🤝 Working Principles

### Communication Style

- **Conciseness**: Be brief and to the point
- **Emojis**: Use freely and consistently but be reasonable
- **Explanations**: Focus on "why" when it's not obvious, skip it when it is
- **Questions**: Ask when there are multiple valid approaches, proceed when the path is clear

### Decision Making

**Ask first when:**

- Multiple valid technical approaches exist and the choice has significant implications
- Making destructive or hard-to-reverse changes
- Unclear what the user actually wants
- Adding features beyond what was explicitly requested

**Proceed autonomously when:**

- The request is clear and specific
- Following established patterns in the codebase
- Making standard, reversible changes
- The instructions in this file provide clear guidance

### Error Philosophy

- When you make a mistake, fix it immediately
- When blocked, explain why and propose alternatives (don't brute force)
- When you find a better approach mid-task, suggest it but don't silently change direction

---

## 💻 Code Standards & Conventions

### Code Style

- **Over-engineering**: Avoid it. Make only changes that are directly requested or clearly necessary
- **Comments**: Only add where logic isn't self-evident. Don't add comments to code you didn't change
- **Error handling**: Only validate at system boundaries. Don't add error handling for scenarios that can't happen
- **File creation**: Prefer editing existing files over creating new ones unless absolutely necessary

### Style Tools

- **Black** — code formatting (line length: 100)
- **Ruff** — linting and imports
- **mypy** — type checking (Python 3.7+)
- Pre-commit hooks run automatically on commit

---

## 🔄 Development Workflow

### Git Practices

**Branching Strategy:**

- **ALWAYS work on a branch** — never commit directly to main
- Branch directly off `main` and merge back to `main`
- Branch naming: `feature/sensor-calibration`, `fix/gps-timeout`, `refactor/audio-pipeline`
- Create a new branch for each commit to keep changes isolated

**Commit Messages (Angular Convention):**

```text
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`

**Examples:**

```text
feat(gps): add PPS timestamp synchronization
fix(audio): resolve buffer overflow in onset detection
docs(README): update installation instructions for Raspberry Pi 5
refactor(sensors): extract BME280 driver to separate module
```

**Subject rules:**
- Use imperative mood ("add" not "added")
- Don't capitalize first letter
- No period at the end
- Max 72 characters

### Testing

- Run `pytest tests/` after code changes
- Target > 80% coverage for new code
- Unit tests for individual components (mocked dependencies)
- Integration tests for component interactions (mocked hardware)
- See [docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md) for full testing guide

### Documentation

- Keep only the documents in `docs/` — don't create new ones ad hoc
- Update existing docs rather than creating parallel versions
- Don't duplicate content across documents — reference or link instead

---

## 📦 Dependencies & Environment

### Virtual Environment

**CRITICAL: Always use the project `.venv` — NEVER install packages globally**

```bash
# Prefer explicit interpreter
./.venv/bin/python -V

# Or activate
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

### Dependency Management

**Single Source of Truth:** `setup.py` contains all Python dependencies.

- **Edit `setup.py`** to change dependencies
- **Never edit `requirements*.txt` directly** — they are auto-generated
- After editing `setup.py`: run `python scripts/update_requirements.py`

### Adding Dependencies

1. Edit `setup.py` (`install_requires` or `extras_require`)
2. Run `python scripts/update_requirements.py`
3. Run `pip install -e .[dev]`
4. Commit both `setup.py` and regenerated `requirements*.txt`

---

## 📁 Project-Specific Context

### Architecture

- **Event-driven pipeline**: Audio → Processing → Detection → Event Bus → MQTT output
- **Event Bus** (`src/core/event_bus.py`): thread-safe pub/sub, works offline
- **MQTT output** bridges local event bus to network
- **Trilateration server** (`scripts/trilateration_server.py`): calculates gunshot position from TDOA

### Key Files

- `main.py` — application entry point and orchestrator
- `src/core/event_bus.py` — central event dispatch
- `src/audio/audio_nodes.py` — ALSA source, file source, pipeline node base
- `src/detection/detection_nodes.py` — Aubio onset, threshold, ML stub
- `src/sensors/gps.py` — GPS reader (gpsd, serial, static fallback)
- `src/output/mqtt_output.py` — MQTT publishing with TLS/reconnect
- `src/config/config.py` — YAML config with dot-notation and deep merge
- `scripts/trilateration_server.py` — TDOA positioning server (744 lines)

### Factory Patterns

Use factory functions rather than direct instantiation where they exist:
- `create_gps_reader(config, event_bus)` — selects gpsd/serial/static automatically
- `create_environmental_sensor(config, event_bus)` — selects BME280/DHT/None
- Follow these patterns when adding new sensor or audio source types

### Known Issues & Work in Progress

- Linux-specific code in `audio_nodes.py` not yet guarded by platform checks
- `SerialGPSReader` missing `__init__` (bug — crashes if instantiated)
- System monitoring module is empty (`src/monitoring/__init__.py` only)
- Remote configuration not implemented
- ML detector is stub only
- TLS certificate verification disabled in MQTT output (security issue)
- See [docs/STATUS.md](../docs/STATUS.md) for full status and [docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md) for security audit

---

## ⚡ Auto-Run Commands

**Always run automatically:**

- `python scripts/update_requirements.py` after modifying `setup.py` dependencies

**Never run without asking:**

- `git push`
- `sudo` commands
- Destructive commands (`rm -rf`, `git reset --hard`, etc.)

---

## 🎯 Current Priorities

- File logger and buffer saver output nodes (highest priority)
- System monitoring implementation
- Platform abstraction (Linux-specific code guards)
- Security hardening (TLS, credential management)
- Test coverage improvement (currently ~25–35%)

---

**Last Updated**: 2026-02-16
