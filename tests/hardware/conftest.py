"""Pytest configuration and fixtures for hardware tests."""

import os

import pytest


def _gps_device_available(device_path: str) -> bool:
    """Return True if the GPS serial device file exists."""
    return os.path.exists(device_path)


@pytest.fixture(autouse=True, scope="session")
def require_hardware(request):
    """Skip all hardware tests when physical devices are not present.

    Checks GPS serial device existence.  Pass ``--gps-device`` to override
    the default ``/dev/serial0``.  Run with ``pytest -m hardware`` to execute
    only on real Raspberry Pi hardware.
    """
    gps_device = request.config.getoption("--gps-device")
    if not _gps_device_available(gps_device):
        pytest.skip(
            f"Hardware not available: GPS device '{gps_device}' not found. "
            "Connect hardware and run with: pytest tests/hardware/"
        )


def pytest_addoption(parser):
    """Add command line options for hardware tests."""
    parser.addoption(
        "--gps-device",
        action="store",
        default="/dev/serial0",
        help="Serial GPS device path (default: /dev/serial0)",
    )
    parser.addoption(
        "--baudrate",
        action="store",
        default="9600",
        help="GPS serial baud rate (default: 9600)",
    )
    parser.addoption(
        "--audio-device",
        action="store",
        default="default",
        help="ALSA audio device (default: default)",
    )
    parser.addoption(
        "--format-bits",
        action="store",
        default="32",
        help="Audio sample format bits (default: 32)",
    )
    parser.addoption(
        "--gps-timeout",
        action="store",
        default="120",
        help="Seconds to wait for GPS fix (default: 120)",
    )


@pytest.fixture
def gps_device(request):
    """Get GPS device path from command line."""
    return request.config.getoption("--gps-device")


@pytest.fixture
def gps_baudrate(request):
    """Get GPS baud rate from command line."""
    return int(request.config.getoption("--baudrate"))


@pytest.fixture
def audio_device(request):
    """Get audio device from command line."""
    return request.config.getoption("--audio-device")


@pytest.fixture
def audio_format_bits(request):
    """Get audio format bits from command line."""
    return int(request.config.getoption("--format-bits"))


@pytest.fixture
def gps_timeout(request):
    """Get GPS fix timeout from command line."""
    return int(request.config.getoption("--gps-timeout"))
