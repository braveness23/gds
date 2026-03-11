# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive contribution guidelines (CONTRIBUTING.md)
- GitHub issue and PR templates
- CI/CD workflow with GitHub Actions (lint, test matrix 3.7-3.12, integration, dep check, build)
- Status badges in README
- System monitoring module (`src/monitoring/system_monitor.py`) — CPU, memory, disk, temperature via psutil
- Remote configuration system (`src/remote_config/`) — MQTT-based client/server with safety checks, risk assessment, HMAC-SHA256 authentication
- GPS coordinate validation with type/range checks; rejects dangerous defaults
- MQTT Fleet Coordinator security — node allowlist, HMAC message signing, per-node rate limiting
- CODE_OF_CONDUCT.md (Contributor Covenant v2.1)
- SECURITY.md (vulnerability reporting policy)

### Changed
- Moved trilateration server to scripts/ directory for better organization
- Consolidated GPS documentation into single comprehensive guide
- Test coverage improved from ~60% to 77% (397 tests passing)
- Consolidated CI workflows (removed redundant ci-lint.yml)

### Security
- All critical and high-priority security issues resolved
- TLS certificate verification enforced (removed insecure fallback)
- Credentials managed via environment variables (config.yaml removed from version control)
- HMAC-SHA256 message authentication for fleet coordination

## [0.1.0] - 2026-02-16

### Added
- Initial public release
- Event-driven audio processing pipeline with modular nodes
- Multiple detection algorithms:
  - Aubio onset detection for fast transient detection
  - Threshold-based detection for simple amplitude triggers
  - ML detection framework (stub for future models)
- GPS integration with PPS timing support (<1μs accuracy)
- Environmental sensors (BME280, DHT22)
- MQTT output for distributed fleet coordination
- Trilateration server for sound source localization
- Static and mock GPS implementations for testing
- Configuration management with YAML
- System health monitoring with psutil
- Comprehensive documentation:
  - Setup guides for GPS, sensors, deployment
  - Testing guide with unit and integration tests
  - Architecture documentation with diagrams
  - Trilateration algorithm explanation
- Development tools:
  - Automated dependency management (setup.py as source of truth)
  - Pre-commit hooks (black, ruff, mypy)
  - Test framework with pytest
  - Coverage reporting
- Example configurations and scripts
- Systemd service for production deployment

### Security
- Removed credentials from git history
- Added config.yaml to .gitignore
- Input validation for MQTT topics and configuration

### Fixed
- Exception handling improvements (specific exceptions instead of bare except)
- MQTT base topic validation to reject empty/wildcard topics
- Import statement organization and unused import removal

### Changed
- Enforced .venv usage for consistent development environment
- Repository cleaned up (removed 40.5MB of unnecessary files from history)
- Documentation consolidated (19 files → 14 files)
- Branch structure simplified (single main branch)

### Performance
- Repository size reduced from 41MB to 556KB (.git directory)
- Optimized audio buffer processing

## Project Status

**Current Version:** 0.1.0 (Initial Public Release)
**Status:** Alpha - Core functionality working, platform abstraction in progress

### What's Working
- ✅ Audio capture and processing (ALSA, file input)
- ✅ Aubio onset detection
- ✅ GPS positioning with gpsd
- ✅ MQTT fleet coordination
- ✅ Trilateration algorithm
- ✅ Environmental sensors
- ✅ System monitoring
- ✅ Configuration management

### Known Limitations

- Platform support: Linux/Raspberry Pi only (Windows/macOS in progress)
- ML detection: Framework present, but no trained models yet
- Mesh networking: Meshtastic/LoRa deferred to post-MVP
- NTP/PPS clock classes not yet implemented (OS clock used via gpsd)

### Roadmap

See [docs/STATUS.md](docs/STATUS.md) for detailed component status and roadmap.

---

## Version History

### Version Numbering

- **Major (X.0.0)** - Breaking changes, major new features
- **Minor (0.X.0)** - New features, backwards compatible
- **Patch (0.0.X)** - Bug fixes, minor improvements

### Release Process

1. Update CHANGELOG.md with version and date
2. Update version in setup.py
3. Create git tag: `git tag -a v0.1.0 -m "Release v0.1.0"`
4. Push tag: `git push origin v0.1.0`
5. Create GitHub release with changelog excerpt

---

## Links

- [GitHub Repository](https://github.com/braveness23/gds)
- [Issue Tracker](https://github.com/braveness23/gds/issues)
- [Pull Requests](https://github.com/braveness23/gds/pulls)
- [Documentation](https://github.com/braveness23/gds/tree/main/docs)
