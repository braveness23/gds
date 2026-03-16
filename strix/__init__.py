"""
strix — distributed acoustic intelligence platform.

A single node is a strix. A network is a parliament.

This namespace re-exports the public API from the src package.
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
