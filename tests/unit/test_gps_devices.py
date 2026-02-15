import time
from src.sensors.gps import GPSData
from src.sensors.base_gps import BaseGPSDevice
from src.sensors.static_gps import StaticGPSDevice
from src.sensors.mock_gps import MockGPSDevice

class DummyGPSDevice(BaseGPSDevice[GPSData]):
    def _connect(self):
        self.connected = True
    def _read_sensor(self):
        return GPSData(0, 0, 0, time.time(), 1, 4, 1.0, 0.0, 0.0)
    def _disconnect(self):
        self.connected = False

def test_base_gps_device_inheritance():
    device = DummyGPSDevice(update_interval=0.5, sensor_name="Dummy")
    assert isinstance(device, BaseGPSDevice)
    assert device.sensor_name == "Dummy"

def test_static_gps_device():
    lat, lon, alt = 12.34, 56.78, 9.0
    device = StaticGPSDevice(lat, lon, alt)
    pos = device._read_sensor()
    assert pos.latitude == lat
    assert pos.longitude == lon
    assert pos.altitude == alt
    assert pos.fix_quality == 1
    assert pos.satellites == 4
    assert pos.speed == 0.0
    assert pos.has_fix

def test_mock_gps_device_static():
    device = MockGPSDevice(1.0, 2.0, 3.0, move=False)
    pos = device._read_sensor()
    assert pos.latitude == 1.0
    assert pos.longitude == 2.0
    assert pos.altitude == 3.0
    assert pos.speed == 0.0
    assert pos.has_fix

def test_mock_gps_device_movement():
    device = MockGPSDevice(10.0, 20.0, 5.0, move=True)
    pos1 = device._read_sensor()
    pos2 = device._read_sensor()
    assert pos1.latitude != pos2.latitude or pos1.longitude != pos2.longitude
    assert pos2.speed > 0.0
    assert pos2.has_fix
