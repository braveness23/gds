"""Simulation module for acoustic gunshot detection system testing.

Provides physics-accurate simulation of acoustic events propagating to
a network of distributed nodes, enabling integration testing without
real hardware.
"""

import sys
from pathlib import Path

# Ensure repo root is in path so scripts/ and src/ are importable
_root = Path(__file__).parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
