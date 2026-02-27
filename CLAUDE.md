# Claude Instructions for GDS Project

> **About This File**: This document guides how Claude Code assists with this repository. It's a living document - ask Claude to update, clarify, or reorganize as needed. When Claude makes decisions, you can ask "was this based on my instructions?" and Claude will reference specific sections here.

---

## 📋 Project Overview

**What this project is:**

- Distributed acoustic gunshot detection system using trilateration for Raspberry Pi fleets with GPS/PPS timing

**Project type:**

- Distributed IoT/embedded system (Raspberry Pi deployment, modular event-driven audio processing pipeline)

**Tech stack:**

- **Platform:** Edge nodes are Raspberry Pi 3B+/4/5 (Raspberry Pi OS 64-bit, Linux-native); MQTT brokers can be local, remote, or cloud-hosted (public/private clouds); trilateration, dashboards, configuration management, centralized processing and storage will run on various cloud platforms; cross-platform support in progress
- **Language:** Python 3.7+
- **Audio:** PyAudio, Aubio (onset detection), ALSA (Linux), soundfile
- **Detection:** Aubio onset detection, simple threshold detection
- **Sensors:** GPS (gpsd with PPS support), BME280/DHT22 environmental sensors
- **Networking:** MQTT (paho-mqtt)
- **Processing:** NumPy, SciPy (filters, trilateration algorithms)
- **Timing:** NTP (ntplib), GPS PPS for microsecond precision
- **Monitoring:** psutil (system health)
- **Testing:** pytest, pytest-cov, pytest-mock
- **Code quality:** black, ruff, mypy

**Current focus:**

- Platform abstraction (making Linux-only code cross-platform - see [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md))
- Security hardening (credentials, TLS validation, input validation - see [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md))
- Code quality improvements (type hints, exception handling, imports)

---

## 🤝 Working Principles

### Communication Style

- **Conciseness**: Be brief and to the point
- **Emojis**: Use freely and consistantly but be reasonable.
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

### Command Execution

- **Default behavior**: Show commands and offer to run commands rather than showing them for the user to type
- Unless we're working tightly together on something iterative, execute commands directly.  Try to strike a good balance here.  I will let you know if you are being too agressive.
- Maintain a list of commands to auto-run (see Auto-Run Commands section below)

---

## 💻 Code Standards & Conventions

### Code Style

- [To be filled in: formatting preferences, naming conventions, etc.]
- **Over-engineering**: Avoid it. Make only changes that are directly requested or clearly necessary
- **Comments**: Only add where logic isn't self-evident. Don't add comments to code you didn't change
- **Error handling**: Only validate at system boundaries. Don't add error handling for scenarios that can't happen

### File Organization

- [To be filled in: directory structure preferences, file naming, etc.]
- **File creation**: Prefer editing existing files over creating new ones unless absolutely necessary

### Dependencies & Tools

- [To be filled in: preferred libraries, tools to avoid, package manager preferences]

---

## 🔄 Development Workflow

### Git Practices

**Branching Strategy:**

- **ALWAYS work on a branch** - never commit directly to main
- Branch directly off `main` and merge back to `main` (until repo goes public)
- Branch naming: use descriptive names like `feature/sensor-calibration`, `fix/gps-timeout`, `refactor/audio-pipeline`
- When repo becomes public, we'll adopt a more sophisticated branching strategy
 - Create a new branch for each commit to keep changes isolated and history granular (e.g., `git checkout -b fix/gps-timeout`).

**Commit Messages (Angular Convention):**

All commits MUST follow the [Angular commit message format](https://github.com/angular/angular/blob/main/CONTRIBUTING.md#commit):

```text
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, missing semicolons, etc.)
- `refactor`: Code refactoring (neither fixes a bug nor adds a feature)
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `build`: Changes to build system or dependencies
- `ci`: Changes to CI configuration
- `chore`: Other changes that don't modify src or test files

**Examples:**

```text
feat(gps): add PPS timestamp synchronization
fix(audio): resolve buffer overflow in onset detection
docs(README): update installation instructions for Raspberry Pi 5
refactor(sensors): extract BME280 driver to separate module
chore(deps): update numpy to 1.24.0
```

**Scope:** Optional, but recommended. Use module/component name (e.g., `gps`, `audio`, `mqtt`, `sensors`)

**Subject:**

- Use imperative mood ("add" not "added" or "adds")
- Don't capitalize first letter
- No period at the end
- Max 72 characters

**Cleanup Workflow:**

When user requests "cleanup", "commit changes", or similar:

1. **Analyze changes:**
   ```bash
   git status
   git diff
   ```

0. **Create a branch for this cleanup:**
   ```bash
   git checkout -b cleanup/<short-description>
   ```

2. **Stage and commit by logical concern:**
   - Group related changes into separate commits
   - Use `git add -p` to stage parts of files when needed
   - Each commit should represent ONE logical change
   - Use judgment to decide what to bundle together

3. **Run pre-commit checks BEFORE showing summary:**

   ```bash
   git add <files>
   pre-commit run --files <staged-files>
   ```

   - Fix any issues that pre-commit identifies
   - Re-stage fixed files
   - Only show approval summary after pre-commit passes
   - This avoids fix loops after user approval

4. **Example cleanup sequence:**

   ```bash
   # Fix in one file
   git add src/sensors/gps.py
   pre-commit run --files src/sensors/gps.py
   # Fix any issues, re-stage if needed
   # THEN show approval summary

   # Feature across multiple files
   git add src/audio/processor.py src/audio/filters.py
   pre-commit run --files src/audio/processor.py src/audio/filters.py
   # Fix any issues, re-stage if needed
   # THEN show approval summary
   ```

**Pre-commit Hooks:**

- **MUST run pre-commit checks BEFORE showing approval summary**
- This is critical to avoid fix loops after user approval
- Workflow:
  1. Stage files (`git add`)
  2. Run `pre-commit run --files <staged-files>`
  3. Fix any issues and re-stage
  4. Only proceed to approval summary after pre-commit passes
- Since pre-commit already ran successfully, use `--no-verify` on actual commit to skip redundant checks

**Commit & Merge Approval:**

- **ALWAYS show a summary** of what will be committed/merged
- **ALWAYS provide an approval button** - never ask user to type "Yes"
- Include in summary:
  - Files changed
  - Brief description of changes
  - Proposed commit message
  - Pre-commit status (should always be ✅ passed)
  - For merges: source and target branches
- Wait for user approval before executing `git commit --no-verify` or `git merge`
 - Before committing, create a new branch for the commit if one does not already exist: `git checkout -b <branch-name>`.

Post-commit: After making the commit(s), begin the merge-to-main process by showing the same approval summary and asking the user "Merge to main now?"; only proceed on explicit approval.

**Pull Requests:**

- [To be defined when repo goes public - likely will include PR templates, review requirements, etc.]

### Testing

- [To be filled in: when to write tests, testing frameworks, coverage expectations]

### Documentation

- **Frequency**: Document things constantly as you work
- **Style**: Be concise - get to the point quickly
- **Don't duplicate code**: Never rewrite the source code in documentation - reference it instead
- **In-depth explanations**: Always preface with a TL;DR summary before diving into details
- **Document management**: Keep only a handful of well-defined documents, not a filing cabinet full
- **New documents**: Don't create new documents ad hoc - only when the user explicitly requests them
- **Maintain existing**: Update and maintain the documents we have rather than creating new ones
- **Avoid duplication**: Don't duplicate information across documents - reference or link instead

---

## 📦 Dependencies & Environment

### Virtual Environment Philosophy

**CRITICAL: Always use the project virtualenv named `.venv` - NEVER install packages globally**

- The application is intended to run in the project's `.venv` directory
- Development MUST take place using `./.venv/bin/python` or an activated `.venv`
- Production on Raspberry Pi uses `.venv`
- DO NOT install packages globally (no `sudo pip install`)

**Windows (Git Bash / Claude Code shell):**

The `.venv` was created in WSL and its symlinks resolve only in Linux. When running on Windows, **prefix all Python commands with `wsl`**:

```bash
# Instead of: ./.venv/bin/python ...
wsl bash -c "cd /mnt/e/Gits/github.com/braveness23/gds && .venv/bin/python ..."
```

Development and the interactive terminal should be done inside WSL, where `.venv/bin/python` works normally.

**Agent enforcement:**

- All automation, CLI helpers, CI scripts, editors, and assistant actions MUST prefer the explicit interpreter path `./.venv/bin/python`.
- On Windows (Claude Code / Git Bash): prefix with `wsl bash -c "cd /mnt/e/Gits/github.com/braveness23/gds && ..."`.
- If an automated script detects that the current Python interpreter is not the project's `.venv`, it should either:
   - fail fast with a clear message instructing the user to run `./.venv/bin/python <command>` or activate the venv, or
   - create `.venv` and install required packages before continuing only if explicitly allowed by the user.
- Do not rely on shell activation alone (`source .venv/bin/activate`) for automation; prefer explicit interpreter invocation.

**Enforcement guidance:**

- Automation, CI, and tools should prefer the explicit interpreter path `./.venv/bin/python` rather than relying solely on activation in an interactive shell. This is the most reliable approach for scripts and editors.

**Checking venv activation:**

```bash
# Prefer explicit interpreter invocation to avoid relying on activation
./.venv/bin/python -V || echo "No .venv found; create with: python3 -m venv .venv"

# If you prefer activation (interactive use):
if [ -z "$VIRTUAL_ENV" ]; then
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
fi

# VSCode integrated terminal should use the workspace interpreter (see .vscode/settings.json)
```

### Dependency Management Philosophy

**Single Source of Truth:** `setup.py` contains all Python dependencies. Requirements files are auto-generated.

**Version Strategy:**
- Production: Use `~=` for controlled updates (e.g., `numpy~=1.21.0` allows 1.21.x)
- Production (risky packages): Use `>=X,<Y` with upper bounds (e.g., `numpy>=1.21.0,<2.0`)
- Development: Pin exact versions (e.g., `pytest==7.4.3`)
- System packages: Documented in [docs/SETUP.md](docs/SETUP.md)

**Files:**
- `setup.py` - **EDIT THIS** to change dependencies
- `requirements*.txt` - **AUTO-GENERATED** (DO NOT EDIT)
- `scripts/update_requirements.py` - Regenerates requirements files
- `scripts/check_dependencies.py` - Validates installed dependencies

### Adding Dependencies

**Process (ALWAYS follow this):**

1. Ensure venv is activated (VSCode does this automatically)
2. Edit `setup.py` (`install_requires` or `extras_require`)
3. Run `python scripts/update_requirements.py` to regenerate requirements files
4. Test: `pip install -e .[dev]` and run `pytest`
5. Commit both `setup.py` and regenerated `requirements*.txt`
6. Pre-commit hook will verify sync automatically

0. **Create a branch for dependency changes before editing**
   ```bash
   git checkout -b chore/deps/<short-description>
   ```

**Example:**

```python
# setup.py - Add new package here
install_requires=[
    "new-package~=1.2.0",  # Add with version constraint
]
```

```bash
# In venv (VSCode terminal auto-activates)
python scripts/update_requirements.py  # Regenerate requirements.txt
pip install -e .[dev]                   # Install updated deps
pytest                                  # Validate
git add setup.py requirements*.txt
git commit -m "Add new-package dependency"
```

### Developer Setup

**Quick Start (one command - creates venv automatically):**

```bash
python scripts/setup_dev.py
```

**Manual setup:**

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -e .[dev]
pre-commit install
pytest  # Validate setup
```

**Production (Raspberry Pi - creates venv in /home/pi/gunshot-detection-system/venv):**

```bash
sudo bash scripts/setup_production.sh
```

### System Dependencies

See [docs/SETUP.md](docs/SETUP.md) for platform-specific requirements.

**Quick reference:**
- **Raspberry Pi/Linux:** `portaudio19-dev`, `aubio-tools`, `libsndfile1-dev`, `gpsd`
- **macOS:** `brew install portaudio aubio libsndfile` (future)
- **Windows:** Binary wheels or conda (future)

### VSCode Setup

**VSCode automatically:**

- Detects the `.venv/` directory
- Activates venv in integrated terminal
- Uses venv Python for linting, testing, debugging
- Prompts to install recommended extensions

**Recommended extensions (auto-prompted):**
- Python (ms-python.python)
- Pylance (ms-python.vscode-pylance)
- Black Formatter (ms-python.black-formatter)
- Ruff (charliermarsh.ruff)
- GitLens (eamodio.gitlens)

### Maintenance

**When you add a library, extension, or system dependency:**

1. Ensure venv is activated
2. Update `setup.py` (Python packages) or `docs/SETUP.md` (system packages)
3. Regenerate requirements: `python scripts/update_requirements.py`
4. Update `.vscode/extensions.json` if adding VSCode extension
5. Commit all changes together

**Monthly dependency updates (in venv):**

```bash
pip list --outdated                    # Check for updates
# Test updates in branch
pip install --upgrade -e .[dev]
pytest                                 # Validate
python scripts/update_requirements.py  # Regenerate
git commit -m "chore: update dependencies"
```

**This is religiously maintained - never skip the regeneration step!**

### Common Mistakes to Avoid

❌ **NEVER:** `sudo pip install package` (global install)
✅ **ALWAYS:** `pip install package` (in activated venv)

❌ **NEVER:** Edit `requirements.txt` directly
✅ **ALWAYS:** Edit `setup.py` then run `update_requirements.py`

❌ **NEVER:** Run `python` when venv not activated (check `$VIRTUAL_ENV`)
✅ **ALWAYS:** Let VSCode auto-activate, or manually activate first

---

## 📁 Project-Specific Context

### Key Files & Directories

- [To be filled in: important files Claude should know about]
- [To be filled in: what different directories are for]

### Architecture Notes

- [To be filled in: important architectural decisions, patterns used, etc.]

### Known Issues & Quirks

- [To be filled in: footguns to avoid, workarounds in place, technical debt]

---

## ⚡ Auto-Run Commands

*Commands that Claude should automatically execute without asking first*

**Always run automatically:**

- `./.venv/bin/python scripts/update_requirements.py` after modifying `setup.py` dependencies

**Context-specific auto-run:**

- `pip install -e .[dev]` when dependencies change (in venv)
- `pytest tests/` after making code changes (to validate)

When specifying commands in automation or documentation, always show the `.venv`-prefixed interpreter (or the `tools/py` wrapper) to avoid ambiguity.

**Never auto-run (always ask first):**

- `git push` (always confirm before pushing)
- `sudo` commands (system-level changes require approval)
- Destructive commands (`rm -rf`, `git reset --hard`, etc.)

---

## 🎯 Current Priorities

*This section can change frequently - update as project focus shifts*

**Active goals:**

- ✅ Security hardening — COMPLETED (GPS validation, MQTT authentication, all critical/high-priority issues resolved - 2026-02-20)
- ✅ Test coverage to >70% — COMPLETED (currently 72%, comprehensive test suite with 2900+ lines - 2026-02-20)
- Platform abstraction (making Linux-only code cross-platform - see [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md))
- Code quality improvements (type hints, exception handling, imports)
- System monitoring implementation (CPU, memory, disk, temperature via psutil)

**Deferred/On hold:**

- [To be filled in as priorities shift]

**Blocked:**

- [To be filled in as issues arise]

---

## 📝 Meta: Instruction Evolution

### How to Update This File

- **Add**: "Add [X] to [section name]"
- **Remove**: "Remove the rule about [X]" or "Delete the [section name] section"
- **Modify**: "Change [X] to [Y]" or "Update the [section name] to say [Z]"
- **Reorganize**: "Move [X] under [section name]" or "Restructure the [topic] section"

### Instruction History

*Track major changes to help both of us understand how our working relationship evolves*

- **2026-02-15**: Initial CLAUDE.md created
- **2026-02-15**: Added comprehensive Dependencies & Environment section with venv workflow, dependency management practices, and cross-platform setup guidance
- **2026-02-15**: Added comprehensive Git Practices section with branching strategy, Angular commit conventions, cleanup workflow, and approval process
- **2026-02-15**: Added pre-commit hook requirements to Git Practices - must run before showing approval summary to avoid fix loops
- **2026-02-16**: Major docs restructuring — 12 old docs replaced with 4 focused files (ARCHITECTURE.md, DEVELOPMENT.md, SETUP.md, STATUS.md); README rewritten to reflect actual project status; copilot-instructions.md rewritten with project-specific content; linter updated from flake8 → ruff throughout
- **2026-02-20**: Comprehensive test suite overhaul — test coverage 55% → 72% with 2900+ lines of unit/integration/hardware tests; all critical/high-priority security issues resolved (GPS validation, MQTT authentication with HMAC + rate limiting)

### Improvement Ideas

*Suggestions for making these instructions more effective - from either of us*

- [Claude and user can add suggestions here as we discover gaps or friction]

---

## ❓ Decision Reference Log

*When you ask Claude "why did you do X?", Claude can reference decisions here by number*

1. [Decisions will be logged here as we establish patterns, e.g., "Use React hooks over class components - discussed 2026-02-15"]

---

**Last Updated**: 2026-02-20 (Test coverage 55% → 72%, security hardening complete)
