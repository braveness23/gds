import pytest
from src.sensors.base import BaseSensor

class DummySensor(BaseSensor):
    def _connect(self):
        raise Exception("Connect error")
    def _read_sensor(self):
        raise Exception("Read error")
    def _disconnect(self):
        raise Exception("Disconnect error")

def test_sensor_connect_error():
    sensor = DummySensor(sensor_name="TestSensor")
    with pytest.raises(Exception):
        sensor.connect()

def test_sensor_read_error():
    sensor = DummySensor(sensor_name="TestSensor")
    sensor.connected = True
    sensor.running = True
    with pytest.raises(Exception):
        sensor._read_sensor()

def test_sensor_disconnect_error():
    sensor = DummySensor(sensor_name="TestSensor")
    sensor.connected = True
    with pytest.raises(Exception):
        sensor._disconnect()
