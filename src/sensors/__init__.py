"""Sensor modules for environmental and GPS data.

This package provides:
- BaseSensor: Abstract base class for all sensors
- Environmental sensors (BME280, DHT22/DHT11)
- GPS sensor integration (real, static, mock)
"""

from src.sensors.base import BaseSensor
from src.sensors.environmental import (
    BME280Sensor,
    DHTSensor,
    EnvironmentalData,
    create_environmental_sensor,
)
from src.sensors.gps import GPSData, GPSReader, create_gps_reader
from src.sensors.mock_gps import MockGPSDevice
from src.sensors.static_gps import StaticGPSDevice

__all__ = [
    "BaseSensor",
    "EnvironmentalData",
    "BME280Sensor",
    "DHTSensor",
    "create_environmental_sensor",
    "GPSData",
    "GPSReader",
    "StaticGPSDevice",
    "MockGPSDevice",
    "create_gps_reader",
]
