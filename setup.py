#!/usr/bin/env python3
"""Setup script for Gunshot Detection System."""

from pathlib import Path

from setuptools import find_packages, setup

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = (
    readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""
)

setup(
    name="gunshot-detection-system",
    version="0.1.0",
    description="Distributed gunshot detection system with trilateration",
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
        "paho-mqtt~=1.6.1",
        "psutil~=5.8.0",
        "ntplib~=0.3.4",
    ],
    extras_require={
        "sensors": [
            "gps>=3.19",
            "adafruit-circuitpython-bme280>=2.6.0",
            "adafruit-circuitpython-dht>=3.7.0",
            "adafruit-blinka>=8.0.0",
        ],
        "meshtastic": [
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
            "isort==5.12.0",
            "mypy==1.5.1",
            "flake8==6.1.0",
            # Pre-commit hooks
            "pre-commit==3.4.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "gunshot-detector=main:main",
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
