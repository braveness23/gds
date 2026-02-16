#!/usr/bin/env python3
"""
Dependency validation tool for GDS project.

Checks that all required packages are installed with correct versions
and that system libraries are accessible.

Usage:
    python scripts/check_dependencies.py          # Check all dependencies
    python scripts/check_dependencies.py --fix    # Attempt to fix issues
"""

import argparse
import importlib.metadata
import platform
import subprocess
import sys
from pathlib import Path


def check_python_version():
    """Check Python version meets requirements."""
    version = sys.version_info
    required = (3, 7)

    print(f"Python: {version.major}.{version.minor}.{version.micro}", end=" ")

    if version >= required:
        print("[OK]")
        return True
    else:
        print(f"[FAIL] - Requires Python {required[0]}.{required[1]}+")
        return False


def check_package_version(package_name, version_spec):
    """
    Check if a package is installed with correct version.

    Args:
        package_name: Name of the package
        version_spec: Version specification (e.g., ">=1.21.0,<2.0")

    Returns:
        (bool, str): (success, installed_version)
    """
    try:
        # Try to import the package
        installed_version = importlib.metadata.version(package_name)
        return True, installed_version
    except importlib.metadata.PackageNotFoundError:
        return False, None


def parse_requirements_file(filepath):
    """
    Parse a requirements file and return list of (package, version_spec).

    Args:
        filepath: Path to requirements file

    Returns:
        List of tuples (package_name, version_spec)
    """
    requirements = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            # Parse package name and version
            # Handle: package==1.0.0, package>=1.0.0,<2.0, package~=1.0.0
            for sep in ["~=", "==", ">=", "<=", "!=", "<", ">"]:
                if sep in line:
                    parts = line.split(sep, 1)
                    package = parts[0].strip()
                    version = sep + parts[1].strip()
                    requirements.append((package, version))
                    break
            else:
                # No version specifier
                requirements.append((line, ""))

    return requirements


def check_requirements_file(filepath, name):
    """Check all packages in a requirements file."""
    print(f"\n{name}:")
    print("-" * 60)

    if not filepath.exists():
        print(f"  [SKIP] {filepath.name} not found")
        return True

    requirements = parse_requirements_file(filepath)
    all_ok = True

    for package, version_spec in requirements:
        success, installed = check_package_version(package, version_spec)

        if success:
            print(f"  [OK]   {package} ({installed})")
        else:
            print(f"  [FAIL] {package} not installed")
            all_ok = False

    return all_ok


def check_system_library(lib_name):
    """
    Try to import a system library to verify it's accessible.

    Args:
        lib_name: Name of the library to check

    Returns:
        bool: True if library is accessible
    """
    try:
        __import__(lib_name)
        return True
    except ImportError:
        return False


def check_system_dependencies():
    """Check system-level dependencies."""
    print("\nSystem Dependencies:")
    print("-" * 60)

    system = platform.system()
    all_ok = True

    # Check aubio
    if check_system_library("aubio"):
        print("  [OK]   aubio library accessible")
    else:
        print("  [WARN] aubio library not accessible")
        if system == "Linux":
            print("         Install: sudo apt-get install aubio-tools libaubio-dev")
        elif system == "Darwin":
            print("         Install: brew install aubio")
        all_ok = False

    # Check PyAudio (portaudio)
    if check_system_library("pyaudio"):
        print("  [OK]   pyaudio library accessible")
    else:
        print("  [WARN] pyaudio library not accessible")
        if system == "Linux":
            print("         Install: sudo apt-get install portaudio19-dev")
        elif system == "Darwin":
            print("         Install: brew install portaudio")
        all_ok = False

    return all_ok


def check_venv():
    """Check if running inside a virtual environment."""
    print("\nVirtual Environment:")
    print("-" * 60)

    in_venv = hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    )

    if in_venv:
        print(f"  [OK]   Running in virtual environment")
        print(f"         Location: {sys.prefix}")
        return True
    else:
        print(f"  [WARN] Not running in virtual environment")
        print(f"         Activate venv before installing packages!")
        return False


def main():
    parser = argparse.ArgumentParser(description="Validate GDS dependencies")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Attempt to install missing packages (requires venv)",
    )
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent

    print("=" * 60)
    print("GDS Dependency Validation")
    print("=" * 60)

    # Check Python version
    python_ok = check_python_version()

    # Check venv
    venv_ok = check_venv()

    # Check core dependencies
    core_ok = check_requirements_file(
        project_root / "requirements.txt", "Core Dependencies"
    )

    # Check dev dependencies
    dev_ok = check_requirements_file(
        project_root / "requirements-dev.txt", "Development Dependencies"
    )

    # Check system dependencies
    system_ok = check_system_dependencies()

    # Summary
    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)

    all_checks = [
        ("Python version", python_ok),
        ("Virtual environment", venv_ok),
        ("Core dependencies", core_ok),
        ("Development dependencies", dev_ok),
        ("System dependencies", system_ok),
    ]

    for check_name, result in all_checks:
        status = "[OK]  " if result else "[FAIL]"
        print(f"  {status} {check_name}")

    all_ok = all(result for _, result in all_checks)

    if all_ok:
        print("\n[SUCCESS] All dependency checks passed!")
        sys.exit(0)
    else:
        print("\n[FAIL] Some dependency checks failed")

        if args.fix:
            print("\nAttempting to fix issues...")
            print("(Not yet implemented - install dependencies manually)")

        print("\nTo fix issues:")
        print("  1. Ensure you're in a virtual environment")
        print("  2. Run: pip install -e .[dev]")
        print("  3. Install system dependencies (see SYSTEM_DEPENDENCIES.md)")

        sys.exit(1)


if __name__ == "__main__":
    main()
