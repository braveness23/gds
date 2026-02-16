#!/usr/bin/env python3
"""
Generate requirements files from setup.py.

This script parses setup.py to extract dependencies and generates
standardized requirements files. This ensures setup.py remains the
single source of truth for all dependencies.

Generated files:
- requirements.txt - Production dependencies (install_requires)
- requirements-dev.txt - Development dependencies (extras_require['dev'])
- requirements-sensors.txt - Optional sensor dependencies (extras_require['sensors'])
- requirements-all.txt - All dependencies combined

Usage:
    python scripts/update_requirements.py              # Generate all files
    python scripts/update_requirements.py --check      # Validate sync (CI mode)
    python scripts/update_requirements.py --stdout     # Print to stdout (testing)
"""

import argparse
import ast
import sys
from pathlib import Path
from typing import Dict, List

HEADER = """# AUTO-GENERATED from setup.py - DO NOT EDIT MANUALLY
# To update: python scripts/update_requirements.py
# To modify dependencies: edit setup.py
"""


def parse_setup_py(setup_path: Path) -> Dict[str, List[str]]:
    """
    Parse setup.py to extract dependencies.

    Returns:
        Dict with keys: 'install_requires', 'dev', 'sensors', 'meshtastic'
    """
    content = setup_path.read_text()
    tree = ast.parse(content)

    dependencies = {"install_requires": [], "dev": [], "sensors": [], "meshtastic": []}

    # Find the setup() call
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "setup":
                # Parse keyword arguments
                for keyword in node.keywords:
                    # Extract install_requires
                    if keyword.arg == "install_requires":
                        if isinstance(keyword.value, ast.List):
                            for item in keyword.value.elts:
                                if isinstance(item, ast.Constant):
                                    dependencies["install_requires"].append(item.value)

                    # Extract extras_require
                    elif keyword.arg == "extras_require":
                        if isinstance(keyword.value, ast.Dict):
                            for key, value in zip(
                                keyword.value.keys, keyword.value.values
                            ):
                                if isinstance(key, ast.Constant):
                                    extra_name = key.value
                                    if extra_name in dependencies:
                                        if isinstance(value, ast.List):
                                            for item in value.elts:
                                                if isinstance(item, ast.Constant):
                                                    dependencies[extra_name].append(
                                                        item.value
                                                    )

    return dependencies


def generate_requirements_content(deps: List[str], header: str = HEADER) -> str:
    """Generate requirements file content with header."""
    if not deps:
        return header + "\n# No dependencies\n"
    return header + "\n" + "\n".join(deps) + "\n"


def write_requirements_file(path: Path, content: str, check_mode: bool = False) -> bool:
    """
    Write requirements file or check if it matches.

    Returns:
        True if file matches (in check mode) or was written successfully
    """
    if check_mode:
        if not path.exists():
            print(f"[FAIL] {path.name} does not exist", file=sys.stderr)
            return False

        existing_content = path.read_text()
        if existing_content != content:
            print(f"[FAIL] {path.name} is out of sync with setup.py", file=sys.stderr)
            print(f"       Run: python scripts/update_requirements.py", file=sys.stderr)
            return False

        print(f"[OK] {path.name} is in sync")
        return True
    else:
        path.write_text(content)
        print(f"[OK] Generated {path.name}")
        return True


def main():
    parser = argparse.ArgumentParser(
        description="Generate requirements files from setup.py"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if requirements files are in sync (exit 1 if not)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print to stdout instead of writing files (for testing)",
    )
    args = parser.parse_args()

    # Get project root (parent of scripts/)
    project_root = Path(__file__).parent.parent
    setup_py_path = project_root / "setup.py"

    if not setup_py_path.exists():
        print(f"[ERROR] setup.py not found at {setup_py_path}", file=sys.stderr)
        sys.exit(1)

    # Parse setup.py
    try:
        deps = parse_setup_py(setup_py_path)
    except Exception as e:
        print(f"[ERROR] Failed to parse setup.py: {e}", file=sys.stderr)
        sys.exit(1)

    # Generate requirements files
    requirements_files = {
        "requirements.txt": generate_requirements_content(deps["install_requires"]),
        "requirements-dev.txt": generate_requirements_content(deps["dev"]),
        "requirements-sensors.txt": generate_requirements_content(deps["sensors"]),
        "requirements-meshtastic.txt": generate_requirements_content(
            deps["meshtastic"]
        ),
    }

    # Generate requirements-all.txt (everything combined)
    all_deps = (
        deps["install_requires"] + deps["dev"] + deps["sensors"] + deps["meshtastic"]
    )
    # Remove duplicates while preserving order
    seen = set()
    all_deps_unique = []
    for dep in all_deps:
        if dep not in seen:
            seen.add(dep)
            all_deps_unique.append(dep)

    requirements_files["requirements-all.txt"] = generate_requirements_content(
        all_deps_unique
    )

    # Output mode
    if args.stdout:
        for filename, content in requirements_files.items():
            print(f"\n{'='*60}")
            print(f"=== {filename}")
            print(f"{'='*60}")
            print(content)
        sys.exit(0)

    # Write or check files
    all_synced = True
    for filename, content in requirements_files.items():
        filepath = project_root / filename
        if not write_requirements_file(filepath, content, args.check):
            all_synced = False

    if args.check:
        if all_synced:
            print("\n[SUCCESS] All requirements files are in sync with setup.py")
            sys.exit(0)
        else:
            print("\n[FAIL] Some requirements files are out of sync", file=sys.stderr)
            sys.exit(1)
    else:
        print(
            f"\n[SUCCESS] Successfully generated {len(requirements_files)} requirements files"
        )
        print("\nNext steps:")
        print("  1. Review the generated files")
        print("  2. Commit both setup.py and requirements*.txt together")
        sys.exit(0)


if __name__ == "__main__":
    main()
