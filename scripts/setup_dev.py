#!/usr/bin/env python3
"""
Cross-platform development environment setup script.

This script automates the setup of a development environment for the
Gunshot Detection System project. It works on Windows, macOS, and Linux.

Features:
- Creates Python virtual environment
- Installs all development dependencies
- Configures pre-commit hooks
- Validates installation
- Runs tests
- Provides platform-specific guidance for system dependencies

Usage:
    python scripts/setup_dev.py              # Full interactive setup
    python scripts/setup_dev.py --minimal    # Skip optional dependencies
    python scripts/setup_dev.py --check      # Validation only (no install)
"""

import argparse
import os
import platform
import subprocess
import sys
from pathlib import Path


class Colors:
    """ANSI color codes for terminal output."""

    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"

    @classmethod
    def disable(cls):
        """Disable colors for Windows compatibility."""
        cls.HEADER = ""
        cls.OKBLUE = ""
        cls.OKCYAN = ""
        cls.OKGREEN = ""
        cls.WARNING = ""
        cls.FAIL = ""
        cls.ENDC = ""
        cls.BOLD = ""
        cls.UNDERLINE = ""


# Disable colors on Windows unless ANSICON is set
if platform.system() == "Windows" and not os.environ.get("ANSICON"):
    Colors.disable()


def print_header(message):
    """Print a section header."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{message}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")


def print_success(message):
    """Print a success message."""
    print(f"{Colors.OKGREEN}[OK]{Colors.ENDC} {message}")


def print_error(message):
    """Print an error message."""
    print(f"{Colors.FAIL}[ERROR]{Colors.ENDC} {message}", file=sys.stderr)


def print_warning(message):
    """Print a warning message."""
    print(f"{Colors.WARNING}[WARNING]{Colors.ENDC} {message}")


def print_info(message):
    """Print an info message."""
    print(f"{Colors.OKCYAN}[INFO]{Colors.ENDC} {message}")


def run_command(cmd, cwd=None, check=True, capture_output=False):
    """Run a shell command."""
    try:
        if capture_output:
            result = subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)
            return result.returncode == 0, result.stdout
        else:
            result = subprocess.run(cmd, cwd=cwd, check=check)
            return result.returncode == 0, None
    except subprocess.CalledProcessError:
        return False, None
    except FileNotFoundError:
        return False, None


def detect_platform():
    """Detect the current platform."""
    system = platform.system()
    if system == "Windows":
        return "windows"
    elif system == "Darwin":
        return "macos"
    elif system == "Linux":
        return "linux"
    else:
        return "unknown"


def check_python_version():
    """Check if Python version is sufficient."""
    print_header("Checking Python Version")

    version = sys.version_info
    print_info(f"Python {version.major}.{version.minor}.{version.micro}")

    if version < (3, 7):
        print_error(f"Python 3.7+ required, but you have {version.major}.{version.minor}")
        return False

    if version < (3, 11):
        print_warning("Python 3.11+ recommended for best compatibility")

    print_success("Python version is acceptable")
    return True


def check_venv_exists(project_root):
    """Check if virtual environment already exists."""
    venv_path = project_root / "venv"
    return venv_path.exists()


def create_venv(project_root):
    """Create virtual environment."""
    print_header("Creating Virtual Environment")

    venv_path = project_root / "venv"

    if venv_path.exists():
        print_info("Virtual environment already exists at venv/")
        return True

    print_info("Creating virtual environment...")
    success, _ = run_command([sys.executable, "-m", "venv", "venv"], cwd=project_root)

    if success:
        print_success("Virtual environment created at venv/")
        return True
    else:
        print_error("Failed to create virtual environment")
        return False


def get_venv_python(project_root, plat):
    """Get path to Python executable in venv."""
    if plat == "windows":
        return project_root / "venv" / "Scripts" / "python.exe"
    else:
        return project_root / "venv" / "bin" / "python"


def get_venv_pip(project_root, plat):
    """Get path to pip executable in venv."""
    if plat == "windows":
        return project_root / "venv" / "Scripts" / "pip.exe"
    else:
        return project_root / "venv" / "bin" / "pip"


def upgrade_pip(project_root, plat):
    """Upgrade pip in virtual environment."""
    print_info("Upgrading pip...")
    pip_path = get_venv_pip(project_root, plat)

    success, _ = run_command(
        [str(pip_path), "install", "--upgrade", "pip", "setuptools", "wheel"],
        cwd=project_root,
    )

    if success:
        print_success("pip upgraded successfully")
        return True
    else:
        print_warning("Failed to upgrade pip (continuing anyway)")
        return True  # Non-fatal


def install_dependencies(project_root, plat, minimal=False):
    """Install project dependencies."""
    print_header("Installing Dependencies")

    pip_path = get_venv_pip(project_root, plat)

    # Install main package with dev extras
    print_info("Installing package with development dependencies...")
    success, _ = run_command([str(pip_path), "install", "-e", ".[dev]"], cwd=project_root)

    if not success:
        print_error("Failed to install development dependencies")
        return False

    print_success("Development dependencies installed")

    # Install optional sensor dependencies
    if not minimal:
        response = input("\nInstall optional sensor dependencies (GPS, BME280, DHT)? [y/N]: ")
        if response.lower() in ("y", "yes"):
            print_info("Installing sensor dependencies...")
            success, _ = run_command(
                [str(pip_path), "install", "-e", ".[sensors]"], cwd=project_root
            )
            if success:
                print_success("Sensor dependencies installed")
            else:
                print_warning("Failed to install sensor dependencies (continuing)")

    return True


def install_precommit_hooks(project_root, plat):
    """Install pre-commit hooks."""
    print_header("Setting Up Pre-Commit Hooks")

    venv_python = get_venv_python(project_root, plat)

    print_info("Installing pre-commit hooks...")
    success, _ = run_command([str(venv_python), "-m", "pre_commit", "install"], cwd=project_root)

    if success:
        print_success("Pre-commit hooks installed")
        return True
    else:
        print_warning("Failed to install pre-commit hooks")
        return False


def run_validation(project_root, plat):
    """Run validation checks."""
    print_header("Running Validation")

    venv_python = get_venv_python(project_root, plat)

    # Check if check_dependencies.py exists
    check_deps_script = project_root / "scripts" / "check_dependencies.py"
    if check_deps_script.exists():
        print_info("Validating dependencies...")
        success, _ = run_command(
            [str(venv_python), str(check_deps_script)], cwd=project_root, check=False
        )
        if success:
            print_success("Dependency validation passed")
        else:
            print_warning("Some dependency checks failed (see above)")
    else:
        print_info("Dependency checker not yet available (skipping)")

    return True


def run_tests(project_root, plat):
    """Run test suite."""
    print_header("Running Tests")

    venv_python = get_venv_python(project_root, plat)

    print_info("Running pytest...")
    success, _ = run_command(
        [str(venv_python), "-m", "pytest", "tests/", "-v", "--tb=short"],
        cwd=project_root,
        check=False,
    )

    if success:
        print_success("All tests passed")
        return True
    else:
        print_warning("Some tests failed (see above)")
        return False


def print_system_dependencies(plat):
    """Print platform-specific system dependency installation instructions."""
    print_header("System Dependencies")

    if plat == "linux":
        print_info("On Debian/Ubuntu/Raspberry Pi OS, install system packages:")
        print("\n  sudo apt-get update")
        print("  sudo apt-get install -y \\")
        print("    python3-dev build-essential \\")
        print("    portaudio19-dev libsndfile1-dev \\")
        print("    aubio-tools libaubio-dev \\")
        print("    gpsd gpsd-clients python3-gps \\")
        print("    libgpiod2")

    elif plat == "macos":
        print_info("On macOS, install system packages with Homebrew:")
        print("\n  brew install portaudio aubio libsndfile")

    elif plat == "windows":
        print_info("On Windows:")
        print("\n  - PyAudio and Aubio will use pre-compiled wheels if available")
        print("  - GPS functionality is typically not used on Windows")
        print("  - For audio development, consider using Windows Subsystem for Linux (WSL)")

    print()


def print_next_steps(plat):
    """Print next steps for the user."""
    print_header("Setup Complete!")

    print(f"{Colors.OKGREEN}Your development environment is ready!{Colors.ENDC}\n")

    print("Next steps:")
    print("  1. Activate your virtual environment:")
    if plat == "windows":
        print(f"     {Colors.BOLD}venv\\Scripts\\activate{Colors.ENDC}")
    else:
        print(f"     {Colors.BOLD}source venv/bin/activate{Colors.ENDC}")

    print("\n  2. Start developing:")
    print(f"     {Colors.BOLD}python main.py --help{Colors.ENDC}")

    print("\n  3. Run tests:")
    print(f"     {Colors.BOLD}pytest tests/{Colors.ENDC}")

    print("\n  4. Format code before committing:")
    print(f"     {Colors.BOLD}black src/ tests/{Colors.ENDC}")

    print("\nIf using VSCode:")
    print("  - VSCode will automatically detect and activate the venv")
    print("  - Install recommended extensions when prompted")

    print()


def main():
    parser = argparse.ArgumentParser(description="Set up development environment for GDS project")
    parser.add_argument("--minimal", action="store_true", help="Skip optional dependencies")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only validate existing setup, don't install",
    )
    args = parser.parse_args()

    # Detect platform
    plat = detect_platform()
    project_root = Path(__file__).parent.parent

    print_header("GDS Development Environment Setup")
    print_info(f"Platform: {plat}")
    print_info(f"Project root: {project_root}")

    # Check Python version
    if not check_python_version():
        sys.exit(1)

    # Print system dependencies info
    print_system_dependencies(plat)

    # Check-only mode
    if args.check:
        print_header("Validation Mode")

        if not check_venv_exists(project_root):
            print_error("Virtual environment not found")
            print_info("Run without --check to create it")
            sys.exit(1)

        print_success("Virtual environment exists")

        if not run_validation(project_root, plat):
            sys.exit(1)

        print_success("Validation complete")
        sys.exit(0)

    # Create venv
    if not create_venv(project_root):
        sys.exit(1)

    # Upgrade pip
    if not upgrade_pip(project_root, plat):
        sys.exit(1)

    # Install dependencies
    if not install_dependencies(project_root, plat, args.minimal):
        sys.exit(1)

    # Install pre-commit hooks
    install_precommit_hooks(project_root, plat)

    # Run validation
    run_validation(project_root, plat)

    # Run tests
    run_tests(project_root, plat)

    # Print next steps
    print_next_steps(plat)


if __name__ == "__main__":
    main()
