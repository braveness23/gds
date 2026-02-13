#!/usr/bin/env python3
"""Setup script for Gunshot Detection System."""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

setup(
    name="gunshot-detection-system",
    version="0.1.0",
    description="Distributed gunshot detection system with trilateration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Your Name",
    author_email="your.email@example.com",
    url="https://github.com/yourusername/gunshot-detection-system",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.7",
    install_requires=[
        "numpy>=1.21.0",
        "scipy>=1.7.0",
        "aubio>=0.4.9",
        "pyaudio>=0.2.11",
        "soundfile>=0.10.3",
        "PyYAML>=5.4",
        "paho-mqtt>=1.6.1",
        "psutil>=5.8.0",
        "ntplib>=0.3.4",
    ],
    extras_require={
        'sensors': [
            'gps>=3.19',
            'adafruit-circuitpython-bme280>=2.6.0',
            'adafruit-circuitpython-dht>=3.7.0',
            'adafruit-blinka>=8.0.0',
        ],
        'meshtastic': [
            'meshtastic>=2.0.0',
        ],
        'dev': [
            'pytest>=7.0.0',
            'black>=22.0.0',
            'flake8>=4.0.0',
        ],
    },
    entry_points={
        'console_scripts': [
            'gunshot-detector=main:main',
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
