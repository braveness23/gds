"""
strix — distributed acoustic intelligence platform.

A single node is a strix. A network is a parliament.

This is the installable public API for the strix package.
"""

__version__ = "0.2.0"

from audio.audio_nodes import AudioNode
from core.event_bus import EventBus
from detection.detection_nodes import AubioOnsetNode
from output.mqtt_output import MQTTOutputNode
from sensors.gps import GPSReader, create_gps_reader
from timing.ntp_clock import NTPClock
from trilateration import TrilaterationEngine, TrilaterationServer

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
