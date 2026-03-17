#!/usr/bin/env python3
"""Setup script for strix.

Enforcement: This script prefers being run from the project's `.venv`.
If not executed with the `.venv` interpreter, the script will refuse to
proceed and will either instruct the user to re-run using `./.venv/bin/python`
or (if `.venv` is missing) offer to create it and install requirements.
"""

import os
import subprocess
import sys
from pathlib import Path

# Prefer being run from the project's .venv to avoid accidental global installs
PROJECT_ROOT = Path(__file__).resolve().parent
VENV_PATH = PROJECT_ROOT / ".venv"


def _in_project_venv():
    # Check VIRTUAL_ENV env var or sys.prefix match
    venv_env = os.environ.get("VIRTUAL_ENV")
    if venv_env:
        try:
            return Path(venv_env).resolve() == VENV_PATH.resolve()
        except Exception:
            return False
    # Fallback: compare sys.prefix to .venv path
    try:
        return Path(sys.prefix).resolve() == VENV_PATH.resolve()
    except Exception:
        return False


if not _in_project_venv():
    msg = (
        "ERROR: setup.py must be run using the project's .venv interpreter.\n"
        "Run: ./.venv/bin/python setup.py <args>\n"
    )
    sys.stderr.write(msg)
    # If .venv doesn't exist, offer to create it and install requirements
    if not VENV_PATH.exists():
        try:
            sys.stderr.write(".venv not found — creating one now...\n")
            subprocess.check_call([sys.executable, "-m", "venv", str(VENV_PATH)])
            pip_py = VENV_PATH / "bin" / "python"
            if pip_py.exists():
                req_file = PROJECT_ROOT / "requirements.txt"
                if req_file.exists():
                    sys.stderr.write("Installing requirements into .venv...\n")
                    subprocess.check_call(
                        [str(pip_py), "-m", "pip", "install", "-r", str(req_file)]
                    )
                else:
                    sys.stderr.write(
                        "No requirements.txt found; please run update_requirements.py in .venv.\n"
                    )
            sys.stderr.write("Re-run setup using: ./.venv/bin/python setup.py <args>\n")
        except subprocess.CalledProcessError:
            sys.stderr.write(
                "Failed to create .venv or install requirements. Aborting.\n"
            )
        except Exception as exc:  # pragma: no cover - defensive
            sys.stderr.write(f"Unexpected error while preparing .venv: {exc}\n")
    sys.exit(1)

from setuptools import find_packages, setup

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = (
    readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""
)

setup(
    name="strix-acoustic",  # placeholder until PyPI name resolved; strix is taken
    version="0.2.0",
    description="strix: distributed acoustic intelligence platform",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="braveness23",
    author_email="",
    url="https://github.com/braveness23/gds",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.7",
    install_requires=[
        # Core dependencies with upper bounds to prevent breaking changes
        "numpy>=1.21.0,<2.0",  # Upper bound prevents numpy 2.x breaking changes
        "scipy>=1.7.0,<2.0",  # Upper bound prevents scipy 2.x breaking changes
        # Platform-dependent packages - keep >= due to compilation/binary variations
        "aubio>=0.4.9",
        "pyaudio>=0.2.11",
        # Other core dependencies
        "soundfile~=0.10.3",
        "PyYAML~=5.4",
        "psutil~=5.8.0",
        "ntplib~=0.3.4",
    ],
    extras_require={
        "mqtt": [
            "paho-mqtt~=1.6.1",
        ],
        "sensors": [
            "gps>=3.19",
            "adafruit-circuitpython-bme280>=2.6.0",
            "adafruit-circuitpython-dht>=3.7.0",
            "adafruit-blinka>=8.0.0",
        ],
        "simulation": [
            "pytest==7.4.3",
            "pytest-mock==3.12.0",
        ],
        "ui": [
            "aiohttp>=3.9.0",
            "paho-mqtt~=1.6.1",
        ],
        "meshtastic": [
            "meshtastic>=2.0.0",
        ],
        "full": [
            "paho-mqtt~=1.6.1",
            "gps>=3.19",
            "adafruit-circuitpython-bme280>=2.6.0",
            "adafruit-circuitpython-dht>=3.7.0",
            "adafruit-blinka>=8.0.0",
            "meshtastic>=2.0.0",
        ],
        "dev": [
            # Testing dependencies (pinned for reproducibility)
            "pytest==7.4.3",
            "pytest-cov==4.1.0",
            "pytest-mock==3.12.0",
            "pytest-asyncio==0.21.1",
            "pytest-timeout==2.2.0",
            # Code quality tools (pinned for consistency)
            "black==23.12.0",
            "ruff==0.1.6",
            "mypy==1.5.1",
            # Pre-commit hooks
            "pre-commit==3.4.0",
            # MQTT needed for integration tests
            "paho-mqtt~=1.6.1",
            # NTP client needed for timing tests
            "ntplib~=0.3.4",
        ],
    },
    entry_points={
        "console_scripts": [
            "strix=strix.cli:main",
            "strix-server=strix.cli:trilateration",
            "strix-map=src.ui.parliament_map.cli:main",
            "gunshot-detector=strix.cli:main",  # kept for backwards compatibility
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
)
