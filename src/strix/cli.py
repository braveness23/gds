"""
strix CLI entry points.

Installed console scripts delegate here:
  strix          → strix.cli:main         (node audio pipeline)
  strix-server   → strix.cli:trilateration (parliament trilateration server)
"""

import sys


def main():
    """Entry point for the `strix` console script (node audio pipeline)."""
    # main.py lives at repo root, outside src/; resolve it via sys.path.
    # When installed as a package this is reached via the installed entry
    # point, so we import the installed main module (added to sys.path by
    # editable install or the package itself).
    try:
        import main as _main
    except ImportError:
        # Fallback: look for main.py relative to this file's package root
        import importlib
        import os

        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if root not in sys.path:
            sys.path.insert(0, root)
        _main = importlib.import_module("main")

    _main.main()


def trilateration():
    """Entry point for the `strix-server` console script (trilateration server)."""
    from scripts.trilateration_server import main as _server_main

    _server_main()
