# Contributing to strix

Thank you for your interest in contributing to this project! This guide will help you get started.

## ⚠️ Privacy — No PII in the Repository

**Do not commit real-world location data.** This includes:
- GPS coordinates (latitude, longitude, altitude) of actual deployment sites
- Node IP addresses, hostnames, or network topology of real deployments
- Any personally identifiable information about operators or sites

Use placeholder values in config examples and test fixtures (e.g. `lat: 0.0`, `lon: 0.0`
or clearly fictional coordinates). Validation reports and deployment notes must redact
real coordinates before being committed.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Code Standards](#code-standards)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Enhancements](#suggesting-enhancements)

---

## Code of Conduct

This project follows a simple code of conduct:

- **Be respectful** - Treat all contributors with respect
- **Be constructive** - Provide helpful feedback and suggestions
- **Be collaborative** - Work together to improve the project
- **Be patient** - Remember that everyone is learning

---

## Getting Started

### Prerequisites

- Python 3.7 or higher
- Any Linux-capable hardware for hardware testing (Raspberry Pi, x86, ARM SBC — anything with audio input and GPS), or Linux/macOS/Windows for development
- Basic understanding of audio processing and Python

### Quick Start

1. **Fork the repository** on GitHub
2. **Clone your fork:**
   ```bash
   git clone https://github.com/YOUR-USERNAME/gds.git
   cd gds
   ```
3. **Set up development environment:**
   ```bash
   python scripts/setup_dev.py
   ```
4. **Create a branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

---

## Development Setup

### Automated Setup (Recommended)

```bash
# Creates .venv, installs all dependencies, sets up pre-commit hooks
python scripts/setup_dev.py
```

### Manual Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies with development tools
pip install -e .[dev]

# Install pre-commit hooks
pre-commit install

# Verify setup
pytest
```

### System Dependencies

Some features require system packages. See [docs/SETUP.md](docs/SETUP.md) for details.

**For audio/GPS testing:**
- Any Linux-capable hardware (Raspberry Pi, x86, ARM SBC, etc.) with ALSA/PortAudio
- GPS module (optional, can use mock GPS)
- MQTT broker (optional, can use test.mosquitto.org)

---

## How to Contribute

### Types of Contributions Welcome

- **Bug fixes** - Fix issues in existing code
- **New features** - Add new detection algorithms, sensors, outputs
- **Documentation** - Improve guides, add examples, fix typos
- **Tests** - Add unit tests, integration tests, hardware tests
- **Performance** - Optimize audio processing, reduce latency
- **Platform support** - Help make code cross-platform (Windows, macOS)

### Finding Work

- Check [Issues](https://github.com/braveness23/gds/issues) for open tasks
- Look for issues tagged `good-first-issue` or `help-wanted`
- Review [docs/STATUS.md](docs/STATUS.md) for planned features and future ideas

---

## Code Standards

### Style Guide

We use automated tools to maintain code quality:

- **Black** - Code formatting (line length: 100)
- **Ruff** - Fast linting (replaces flake8, isort)
- **mypy** - Type checking

**Pre-commit hooks run automatically** when you commit. They will:
- Format code with Black
- Check imports and style with Ruff
- Verify type hints with mypy

### Best Practices

1. **Write clear, simple code**
   - Prefer readability over cleverness
   - Add comments only where logic isn't self-evident
   - Use descriptive variable names

2. **Follow existing patterns**
   - Study similar code in the codebase
   - Match the style of surrounding code
   - Use the event bus architecture for new components

3. **Type hints required**
   ```python
   def process_audio(samples: np.ndarray, sample_rate: int) -> AudioBuffer:
       """Process audio samples and return buffer."""
       ...
   ```

4. **Handle errors appropriately**
   - Use specific exceptions (ValueError, TypeError, etc.)
   - Don't catch broad exceptions without re-raising
   - Clean up resources in finally blocks or use context managers

5. **Keep functions focused**
   - One function = one purpose
   - Extract complex logic into helper functions
   - Aim for functions under 50 lines

### Git Commit Messages

We follow the [Angular commit convention](https://github.com/angular/angular/blob/main/CONTRIBUTING.md#commit):

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation changes
- `test` - Adding/updating tests
- `refactor` - Code refactoring
- `perf` - Performance improvements
- `chore` - Maintenance tasks

**Examples:**
```
feat(sensors): add DHT22 temperature sensor support

fix(audio): resolve buffer overflow in onset detection

docs(README): update installation instructions for Pi 5

test(gps): add unit tests for GPS position parsing
```

**Commit message rules:**
- Use imperative mood ("add" not "added" or "adds")
- Don't capitalize first letter of subject
- No period at end of subject
- Keep subject under 72 characters
- Separate subject from body with blank line

---

## Testing

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov

# Specific test file
pytest tests/unit/test_audio.py

# Specific test
pytest tests/unit/test_audio.py::test_aubio_detection
```

### Writing Tests

1. **Unit tests** - Test individual functions/classes
   ```python
   # tests/unit/test_sensors.py
   def test_gps_parsing():
       data = parse_nmea("$GPGGA,123456.00,3747.4900,N,...")
       assert data.latitude == 37.7749
   ```

2. **Integration tests** - Test component interactions
   ```python
   # tests/integration/test_audio_pipeline.py
   def test_audio_processing_chain():
       source = FileSourceNode("test.wav")
       detector = AubioOnsetNode()
       # Test full chain...
   ```

3. **Hardware tests** - Test with real hardware (optional)
   ```python
   # tests/hardware/test_gps_hardware.py
   @pytest.mark.hardware
   def test_real_gps():
       # Requires actual GPS hardware
   ```

### Test Coverage

- Aim for >80% code coverage
- All new features must include tests
- Bug fixes should include regression tests

---

## Submitting Changes

### Pull Request Process

1. **Update your branch:**
   ```bash
   git checkout main
   git pull upstream main
   git checkout your-feature-branch
   git rebase main
   ```

2. **Ensure quality:**
   ```bash
   # Pre-commit checks
   pre-commit run --all-files

   # Run tests
   pytest --cov

   # Check types
   mypy src/
   ```

3. **Push to your fork:**
   ```bash
   git push origin your-feature-branch
   ```

4. **Create Pull Request** on GitHub:
   - Use a clear, descriptive title
   - Fill out the PR template completely
   - Link related issues with "Fixes #123" or "Relates to #456"
   - Add screenshots/videos for UI changes
   - Request review from maintainers

### PR Review Process

- Maintainers will review your PR within 1-7 days
- Address feedback by pushing new commits to your branch
- Once approved, a maintainer will merge your PR
- Don't force-push after review starts (breaks review comments)

### After Merge

- Delete your feature branch (GitHub can do this automatically)
- Update your fork's main branch:
  ```bash
  git checkout main
  git pull upstream main
  git push origin main
  ```

---

## Reporting Bugs

### Before Reporting

1. **Search existing issues** - Bug might already be reported
2. **Try latest version** - Bug might be fixed
3. **Check documentation** - Might be expected behavior

### Bug Report Template

Use the GitHub issue template. Include:

- **Description** - What happened vs what you expected
- **Steps to reproduce** - Detailed steps to trigger the bug
- **Environment:**
  - OS: Raspberry Pi OS / Ubuntu / Debian / macOS / Windows
  - Python version: `python --version`
  - Package versions: `pip list | grep -E "aubio|numpy|scipy"`
  - Hardware: board type, GPS module, microphone, etc.
- **Logs** - Error messages, stack traces, relevant log output
- **Screenshots** - If applicable

---

## Suggesting Enhancements

### Feature Requests

Use the GitHub feature request template. Include:

- **Problem** - What problem does this solve?
- **Proposed solution** - How should it work?
- **Alternatives** - Other approaches you considered
- **Use case** - Who benefits and how?

### Design Proposals

For major changes:

1. Open an issue first to discuss the approach
2. Get feedback before implementing
3. Write a design document if needed (see `docs/` for examples)
4. Break large changes into smaller PRs

---

## Additional Resources

### Documentation

- [README.md](README.md) - Project overview and quick start
- [docs/](docs/) - Detailed guides for setup, deployment, testing
- [CLAUDE.md](CLAUDE.md) - AI assistant instructions (shows project conventions)

### Community

- **Issues** - Ask questions, report bugs
- **Discussions** - General questions and ideas (coming soon)

### Learning Resources

- [aubio documentation](https://aubio.org/documentation.html) - Audio onset detection
- [gpsd documentation](https://gpsd.gitlab.io/gpsd/) - GPS daemon
- [MQTT documentation](https://mqtt.org/getting-started/) - Message protocol
- [NumPy documentation](https://numpy.org/doc/) - Array processing

---

## Development Tips

### Common Tasks

**Add a new dependency:**
```bash
# Edit setup.py (add to install_requires)
python scripts/update_requirements.py
pip install -e .[dev]
```

**Test on target hardware:**
```bash
# Copy to node
scp -r . user@hostname:~/gds

# SSH to node
ssh user@hostname
cd ~/gds

# Run tests
pytest
```

**Debug GPS issues:**
```bash
python tools/gps_test.py --check
cgps -s
```

**Monitor MQTT messages:**
```bash
mosquitto_sub -t "gunshot/#" -v
```

### Troubleshooting

**Pre-commit hooks failing:**
```bash
# Run manually to see full output
pre-commit run --all-files

# Update hooks
pre-commit autoupdate
```

**Import errors:**
```bash
# Install in development mode
pip install -e .[dev]

# Check Python path
python -c "import sys; print(sys.path)"
```

**Tests failing:**
```bash
# Verbose output
pytest -vv

# Stop on first failure
pytest -x

# Run specific test with print statements
pytest -s tests/unit/test_audio.py::test_aubio
```

---

## Adding a custom classifier

Implement `AcousticClassifier` from `src/classification/`:

```python
from src.classification import AcousticClassifier, ClassificationResult
import numpy as np

class SpectralClassifier(AcousticClassifier):
    def classify(
        self,
        audio_buffer: np.ndarray,
        sample_rate: int,
        detection_event=None,
    ) -> ClassificationResult:
        # Analyse spectral shape, attack envelope, RMS, etc.
        peak = float(np.max(np.abs(audio_buffer)))
        if peak > 0.85:
            return ClassificationResult("gunshot", confidence=0.90)
        return ClassificationResult("unknown", confidence=0.40)
```

To wire it into the pipeline, instantiate your classifier and call `classify()` inside a `DETECTION` event subscriber. A future pipeline integration hook is planned.

---

## Adding a simulation scenario

Scenarios live in `tests/simulation/scenarios.py`. Each is a `Scenario` dataclass:

```python
# In tests/simulation/scenarios.py, add to SCENARIOS dict:
"my_scenario": Scenario(
    name="my_scenario",
    nodes=[
        NodeDef(node_id="n1", latitude=37.77, longitude=-122.41, altitude=10.0),
        NodeDef(node_id="n2", latitude=37.78, longitude=-122.41, altitude=10.0),
        NodeDef(node_id="n3", latitude=37.77, longitude=-122.40, altitude=10.0),
        NodeDef(node_id="n4", latitude=37.78, longitude=-122.40, altitude=10.0),
    ],
    events=[
        EventDef(event_id="e1", latitude=37.775, longitude=-122.405, altitude=0.0, t=0.0),
    ],
    tolerance_meters=20.0,
    min_geometry_score=0.3,
    expected_num_results=1,
),
```

Run with `python tools/run_simulation.py --scenario my_scenario` or in the parametrized integration tests.

---

## Adding an output node

Subclass `AudioNode` and subscribe to `DETECTION` events on the event bus:

```python
import logging
from src.audio.audio_nodes import AudioNode
from src.core.event_bus import EventBus, EventType, Event

class MyOutputNode(AudioNode):
    def __init__(self, event_bus: EventBus = None):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.running = False
        if event_bus:
            event_bus.subscribe(EventType.DETECTION, self._on_detection)

    def _on_detection(self, event: Event):
        # handle detection event
        ...

    def start(self):
        if self.running:
            return
        self.running = True
        self.logger.info("MyOutputNode started")

    def stop(self):
        self.running = False
```

Wire it up in `main.py` (or your own script) after creating the `EventBus`.

---

## Hardware testing

Hardware tests live in `tests/hardware/`. They require real hardware and are skipped in CI.

```bash
# Run hardware tests on a node with GPS + audio
pytest tests/hardware/ -v

# Individual hardware tests
pytest tests/hardware/test_serial_gps.py -v   # GPS fix and timing
pytest tests/hardware/test_i2s_audio.py -v    # I2S audio capture
pytest tests/hardware/test_integration.py -v  # Full node integration
```

See `tests/hardware/README.md` for hardware requirements and wiring.

---

## License

By contributing to this project, you agree that your contributions will be licensed under the [MIT License](LICENSE).

---

## Questions?

- Open an issue with the `question` label
- Check [docs/](docs/) for detailed guides
- Review [CLAUDE.md](CLAUDE.md) for project conventions

Thank you for contributing!
