import time

import pytest

from src.sensors.base_gps import BaseGPSDevice
from src.sensors.gps import GPSData, validate_coordinates
from src.sensors.mock_gps import MockGPSDevice
from src.sensors.static_gps import StaticGPSDevice


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


# ============================================================================
# Coordinate Validation Tests
# ============================================================================


class TestCoordinateValidation:
    """Tests for validate_coordinates() security function."""

    def test_valid_coordinates(self):
        """Valid coordinates should not raise exceptions."""
        validate_coordinates(37.7749, -122.4194, 10.0)  # San Francisco
        validate_coordinates(0.0, 0.0, 0.0)  # Null Island (valid but unusual)
        validate_coordinates(-33.8688, 151.2093, 58.0)  # Sydney

    def test_valid_edge_cases(self):
        """Coordinates at exact boundaries should be valid."""
        validate_coordinates(90.0, 180.0, 0.0)  # North Pole, Date Line
        validate_coordinates(-90.0, -180.0, 0.0)  # South Pole, Date Line
        validate_coordinates(0.0, 0.0, -500.0)  # Sea level minimum
        validate_coordinates(0.0, 0.0, 10000.0)  # High altitude

    def test_invalid_latitude_too_high(self):
        """Latitude > 90 should raise ValueError."""
        with pytest.raises(ValueError, match="Latitude must be between -90 and 90"):
            validate_coordinates(90.1, 0.0, 0.0)

    def test_invalid_latitude_too_low(self):
        """Latitude < -90 should raise ValueError."""
        with pytest.raises(ValueError, match="Latitude must be between -90 and 90"):
            validate_coordinates(-90.1, 0.0, 0.0)

    def test_invalid_longitude_too_high(self):
        """Longitude > 180 should raise ValueError."""
        with pytest.raises(ValueError, match="Longitude must be between -180 and 180"):
            validate_coordinates(0.0, 180.1, 0.0)

    def test_invalid_longitude_too_low(self):
        """Longitude < -180 should raise ValueError."""
        with pytest.raises(ValueError, match="Longitude must be between -180 and 180"):
            validate_coordinates(0.0, -180.1, 0.0)

    def test_invalid_latitude_type(self):
        """Non-numeric latitude should raise TypeError."""
        with pytest.raises(TypeError, match="Latitude must be numeric"):
            validate_coordinates("37.7749", 0.0, 0.0)

    def test_invalid_longitude_type(self):
        """Non-numeric longitude should raise TypeError."""
        with pytest.raises(TypeError, match="Longitude must be numeric"):
            validate_coordinates(0.0, "invalid", 0.0)

    def test_invalid_altitude_type(self):
        """Non-numeric altitude should raise TypeError."""
        with pytest.raises(TypeError, match="Altitude must be numeric"):
            validate_coordinates(0.0, 0.0, None)

    def test_extreme_altitude_warning(self, caplog):
        """Extreme altitudes should log warning but not fail."""
        validate_coordinates(0.0, 0.0, 15000.0)  # Very high
        assert "outside typical range" in caplog.text

        caplog.clear()
        validate_coordinates(0.0, 0.0, -1000.0)  # Very low
        assert "outside typical range" in caplog.text


class TestStaticGPSDeviceValidation:
    """Tests that StaticGPSDevice validates coordinates."""

    def test_static_gps_rejects_invalid_latitude(self):
        """StaticGPSDevice should reject invalid latitude."""
        with pytest.raises(ValueError, match="Latitude must be between"):
            StaticGPSDevice(91.0, 0.0, 0.0)

    def test_static_gps_rejects_invalid_longitude(self):
        """StaticGPSDevice should reject invalid longitude."""
        with pytest.raises(ValueError, match="Longitude must be between"):
            StaticGPSDevice(0.0, 181.0, 0.0)

    def test_static_gps_rejects_invalid_types(self):
        """StaticGPSDevice should reject non-numeric coordinates."""
        with pytest.raises(TypeError, match="must be numeric"):
            StaticGPSDevice("invalid", 0.0, 0.0)

    def test_static_gps_accepts_valid_coordinates(self):
        """StaticGPSDevice should accept valid coordinates."""
        device = StaticGPSDevice(37.7749, -122.4194, 10.0)
        pos = device.get_position()
        assert pos.latitude == 37.7749
        assert pos.longitude == -122.4194
        assert pos.altitude == 10.0
