"""
strix root-level shim — for repo-local imports only.

When the package is installed via pip, use `import strix` which resolves
to `src/strix/__init__.py` via setup.py's package_dir={"": "src"}.

This file exists only for uninstalled/editable-mode repo usage where
PYTHONPATH includes the repo root.
"""

from src import (
    AubioOnsetNode,
    AudioNode,
    EventBus,
    GPSReader,
    MQTTOutputNode,
    NTPClock,
    TrilaterationEngine,
    TrilaterationServer,
    __version__,
    create_gps_reader,
)

__all__ = [
    "__version__",
    "EventBus",
    "AudioNode",
    "AubioOnsetNode",
    "MQTTOutputNode",
    "GPSReader",
    "create_gps_reader",
    "NTPClock",
    "TrilaterationEngine",
    "TrilaterationServer",
]
