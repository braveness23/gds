"""
strix — distributed acoustic intelligence platform.

A single node is a strix. A network is a parliament.
"""

__version__ = "0.2.0"

from src.audio.audio_nodes import AudioNode
from src.core.event_bus import EventBus
from src.detection.detection_nodes import AubioOnsetNode
from src.output.mqtt_output import MQTTOutputNode
from src.sensors.gps import GPSReader, create_gps_reader
from src.timing.ntp_clock import NTPClock
from src.trilateration import TrilaterationEngine, TrilaterationServer

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
