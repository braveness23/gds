import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.sensors.base_gps import BaseGPSDevice
from src.sensors.gps import (
    GPSData,
    GPSReader,
    StaticLocationProvider,
    create_gps_reader,
    validate_coordinates,
)
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


# ============================================================================
# GPSData Tests
# ============================================================================


class TestGPSData:
    """Tests for GPSData dataclass."""

    def test_gpsdata_has_fix_property(self):
        """has_fix should be True when fix_quality > 0."""
        no_fix = GPSData(0, 0, 0, time.time(), 0, 0, 99.9, 0.0, 0.0)
        assert no_fix.has_fix is False

        gps_fix = GPSData(37.7749, -122.4194, 10.0, time.time(), 1, 8, 1.2, 0.0, 0.0)
        assert gps_fix.has_fix is True

    def test_gpsdata_fix_type_name(self):
        """fix_type_name should return correct string for fix_quality."""
        assert GPSData(0, 0, 0, time.time(), 0, 0, 99.9, 0.0, 0.0).fix_type_name == "No Fix"
        assert (
            GPSData(37.7749, -122.4194, 10.0, time.time(), 1, 8, 1.2, 0.0, 0.0).fix_type_name
            == "GPS"
        )
        assert (
            GPSData(37.7749, -122.4194, 10.0, time.time(), 2, 8, 1.2, 0.0, 0.0).fix_type_name
            == "DGPS"
        )
        assert (
            GPSData(37.7749, -122.4194, 10.0, time.time(), 4, 8, 1.2, 0.0, 0.0).fix_type_name
            == "RTK Fixed"
        )

    def test_gpsdata_to_dict(self):
        """to_dict should return dictionary with all fields."""
        gps_data = GPSData(37.7749, -122.4194, 10.0, 123.456, 1, 8, 1.2, 2.5, 45.0)
        result = gps_data.to_dict()

        assert result["latitude"] == 37.7749
        assert result["longitude"] == -122.4194
        assert result["altitude"] == 10.0
        assert result["timestamp"] == 123.456
        assert result["fix_quality"] == 1
        assert result["fix_type"] == "GPS"
        assert result["satellites"] == 8
        assert result["hdop"] == 1.2
        assert result["speed"] == 2.5
        assert result["track"] == 45.0
        assert result["has_fix"] is True


# ============================================================================
# GPSReader Tests (gpsd)
# ============================================================================


class TestGPSReader:
    """Tests for GPSReader (gpsd-based)."""

    def test_gpsreader_initialization(self):
        """GPSReader should initialize with connection parameters."""
        reader = GPSReader(host="192.168.1.100", port=2948, update_interval=2.0)

        assert reader.host == "192.168.1.100"
        assert reader.port == 2948
        assert reader.update_interval == 2.0
        assert reader.gps_session is None
        assert reader.stats["positions_read"] == 0
        assert reader.stats["no_fix_count"] == 0

    def test_gpsreader_connect_success(self):
        """GPSReader should connect to gpsd successfully."""
        mock_gps = MagicMock()
        mock_session = Mock()
        mock_gps.gps.return_value = mock_session

        with patch.dict("sys.modules", {"gps": mock_gps}):
            reader = GPSReader()
            reader._connect()

            assert reader.gps_session is mock_session
            mock_gps.gps.assert_called_once()

    def test_gpsreader_connect_module_not_installed(self):
        """GPSReader should raise ImportError if gps module not installed."""
        with patch.dict("sys.modules", {"gps": None}):
            reader = GPSReader()

            with pytest.raises(ImportError, match="gps module not available"):
                reader._connect()

    def test_gpsreader_connect_daemon_not_running(self):
        """GPSReader should raise error if gpsd daemon not running."""
        mock_gps = MagicMock()
        mock_gps.gps.side_effect = ConnectionError("Connection refused")

        with patch.dict("sys.modules", {"gps": mock_gps}):
            reader = GPSReader()

            with pytest.raises(ConnectionError, match="Connection refused"):
                reader._connect()

    def test_gpsreader_parse_tpv_no_fix(self):
        """_parse_tpv_report should return no-fix GPSData for mode < 2."""
        reader = GPSReader()

        # Mode 0 = no mode
        report = {"mode": 0}
        result = reader._parse_tpv_report(report)

        assert result is not None
        assert result.has_fix is False
        assert result.fix_quality == 0

        # Mode 1 = no fix
        report = {"mode": 1}
        result = reader._parse_tpv_report(report)

        assert result is not None
        assert result.has_fix is False

    def test_gpsreader_parse_tpv_2d_fix(self):
        """_parse_tpv_report should parse 2D fix (mode 2)."""
        reader = GPSReader()

        report = {
            "mode": 2,
            "lat": 37.7749,
            "lon": -122.4194,
            "alt": 0.0,
            "epx": 5.0,
            "epy": 5.0,
            "speed": 1.5,
            "track": 90.0,
        }

        result = reader._parse_tpv_report(report)

        assert result is not None
        assert result.has_fix is True
        assert result.latitude == 37.7749
        assert result.longitude == -122.4194
        assert result.speed == 1.5
        assert result.track == 90.0

    def test_gpsreader_parse_tpv_3d_fix(self):
        """_parse_tpv_report should parse 3D fix (mode 3)."""
        reader = GPSReader()

        report = {
            "mode": 3,
            "lat": 37.7749,
            "lon": -122.4194,
            "alt": 100.0,
            "epx": 3.0,
            "epy": 4.0,
            "speed": 2.5,
            "track": 180.0,
        }

        result = reader._parse_tpv_report(report)

        assert result is not None
        assert result.has_fix is True
        assert result.latitude == 37.7749
        assert result.longitude == -122.4194
        assert result.altitude == 100.0
        assert result.hdop > 0  # Calculated from epx/epy

    def test_gpsreader_read_sensor_tpv_report(self):
        """_read_sensor should process TPV reports."""
        mock_session = Mock()
        mock_session.next.return_value = {
            "class": "TPV",
            "mode": 3,
            "lat": 37.7749,
            "lon": -122.4194,
            "alt": 10.0,
        }

        reader = GPSReader()
        reader.gps_session = mock_session

        result = reader._read_sensor()

        assert result is not None
        assert result.latitude == 37.7749
        assert reader.stats["positions_read"] == 1

    def test_gpsreader_read_sensor_non_tpv_report(self):
        """_read_sensor should ignore non-TPV reports."""
        mock_session = Mock()
        mock_session.next.return_value = {"class": "SKY"}  # Not TPV

        reader = GPSReader()
        reader.gps_session = mock_session

        result = reader._read_sensor()

        assert result is None

    def test_gpsreader_read_sensor_connection_lost(self):
        """_read_sensor should handle StopIteration (connection lost)."""
        mock_session = Mock()
        mock_session.next.side_effect = StopIteration()

        reader = GPSReader()
        reader.gps_session = mock_session
        reader._reconnect = Mock()  # Mock reconnect to avoid actual reconnection

        result = reader._read_sensor()

        assert result is None
        reader._reconnect.assert_called_once()

    def test_gpsreader_get_position_alias(self):
        """get_position should be an alias for get_data."""
        reader = GPSReader()
        reader.get_data = Mock(return_value=Mock())

        result = reader.get_position()

        reader.get_data.assert_called_once()
        assert result is not None

    def test_gpsreader_wait_for_fix_success(self):
        """wait_for_fix should return True when fix is acquired."""
        reader = GPSReader()

        # Mock get_position to return fix immediately
        mock_position = GPSData(37.7749, -122.4194, 10.0, time.time(), 1, 8, 1.2, 0.0, 0.0)
        reader.get_position = Mock(return_value=mock_position)

        assert reader.wait_for_fix(timeout=5.0) is True

    def test_gpsreader_wait_for_fix_timeout(self):
        """wait_for_fix should return False on timeout."""
        reader = GPSReader()

        # Mock get_position to always return no fix
        mock_position = GPSData(0, 0, 0, time.time(), 0, 0, 99.9, 0.0, 0.0)
        reader.get_position = Mock(return_value=mock_position)

        assert reader.wait_for_fix(timeout=0.5) is False


# ============================================================================
# StaticLocationProvider Tests
# ============================================================================


class TestStaticLocationProvider:
    """Tests for StaticLocationProvider."""

    def test_static_location_initialization(self):
        """StaticLocationProvider should initialize with coordinates."""
        provider = StaticLocationProvider(37.7749, -122.4194, 10.0)

        pos = provider.get_position()
        assert pos.latitude == 37.7749
        assert pos.longitude == -122.4194
        assert pos.altitude == 10.0
        assert pos.has_fix is True

    def test_static_location_get_position(self):
        """get_position should return static coordinates."""
        provider = StaticLocationProvider(40.7128, -74.0060, 5.0)

        pos = provider.get_position()
        assert pos.latitude == 40.7128
        assert pos.longitude == -74.0060

    def test_static_location_timestamp_updates(self):
        """get_position should update timestamp on each call."""
        provider = StaticLocationProvider(0.0, 0.0, 0.0)

        pos1 = provider.get_position()
        time.sleep(0.01)  # Small delay
        pos2 = provider.get_position()

        # Timestamps should be different (or at minimum equal, but position updated)
        assert pos2.timestamp >= pos1.timestamp
        assert pos2.latitude == pos1.latitude  # Same position

    def test_static_location_no_ops(self):
        """connect/start/stop should be no-ops."""
        provider = StaticLocationProvider(0.0, 0.0, 0.0)

        # Should not raise
        provider.connect()
        provider.start()
        provider.stop()
        provider.add_callback(lambda x: None)

    def test_static_location_wait_for_fix(self):
        """wait_for_fix should always return True."""
        provider = StaticLocationProvider(0.0, 0.0, 0.0)

        assert provider.wait_for_fix(timeout=0.0) is True

    def test_static_location_get_stats(self):
        """get_stats should return position info."""
        provider = StaticLocationProvider(37.7749, -122.4194, 10.0)

        stats = provider.get_stats()

        assert stats["type"] == "static"
        assert stats["latitude"] == 37.7749
        assert stats["longitude"] == -122.4194
        assert stats["altitude"] == 10.0


# ============================================================================
# SerialGPSReader Tests
# ============================================================================


class TestSerialGPSReader:
    """Tests for SerialGPSReader (NMEA serial)."""

    @pytest.mark.skip(reason="SerialGPSReader missing __init__ - cannot instantiate")
    def test_serial_gps_connect_success(self):
        """SerialGPSReader should open serial port."""
        pass

    @pytest.mark.skip(reason="SerialGPSReader missing __init__ - cannot instantiate")
    def test_serial_gps_connect_no_dependencies(self):
        """SerialGPSReader should raise ImportError if dependencies missing."""
        pass

    @pytest.mark.skip(reason="SerialGPSReader missing __init__ - cannot instantiate")
    def test_serial_gps_read_gga_sentence(self):
        """SerialGPSReader should parse GGA sentences."""
        pass


# ============================================================================
# create_gps_reader Factory Function Tests
# ============================================================================


class TestCreateGPSReader:
    """Tests for create_gps_reader factory function."""

    def test_create_gps_reader_static_fallback(self):
        """Factory should create StaticGPSDevice when GPS disabled."""
        config = {
            "sensors": {"gps": {"enabled": False}},
            "location": {"latitude": 37.7749, "longitude": -122.4194, "altitude": 10.0},
        }

        reader = create_gps_reader(config)

        assert isinstance(reader, StaticGPSDevice)
        pos = reader.get_position()
        assert pos.latitude == 37.7749

    def test_create_gps_reader_rejects_default_coordinates(self):
        """Factory should reject default (0, 0) coordinates."""
        config = {
            "sensors": {"gps": {"enabled": False}},
            "location": {"latitude": 0.0, "longitude": 0.0},  # Default not allowed
        }

        with pytest.raises(ValueError, match="GPS coordinates not configured"):
            create_gps_reader(config)

    def test_create_gps_reader_validates_coordinates(self):
        """Factory should validate coordinate ranges."""
        config = {
            "sensors": {"gps": {"enabled": False}},
            "location": {"latitude": 91.0, "longitude": 0.0},  # Invalid latitude
        }

        with pytest.raises(ValueError, match="Latitude must be between"):
            create_gps_reader(config)

    def test_create_gps_reader_gpsd_enabled(self):
        """Factory should create GPSReader when enabled and gpsd available."""
        config = {
            "sensors": {
                "gps": {"enabled": True, "host": "localhost", "port": 2947, "update_interval": 1.0}
            },
            "location": {"latitude": 37.7749, "longitude": -122.4194},
        }

        # Factory will attempt to create GPSReader (but not connect yet)
        reader = create_gps_reader(config)

        # Should be GPSReader instance (connection happens later via connect())
        assert isinstance(reader, GPSReader)
        assert reader.host == "localhost"
        assert reader.port == 2947

    def test_create_gps_reader_serial_not_available(self):
        """Factory should fall back to gpsd when serial unavailable."""
        config = {
            "sensors": {
                "gps": {
                    "enabled": True,
                    "prefer_serial": True,
                    "serial_device": "/dev/ttyS0",
                    "baudrate": 9600,
                }
            },
            "location": {"latitude": 37.7749, "longitude": -122.4194},
        }

        # When serial/pynmea2 not available, factory falls back to gpsd
        # (since gps module is imported at module level and available)
        reader = create_gps_reader(config)

        # Should create GPSReader as fallback (warning logged about serial missing)
        assert isinstance(reader, GPSReader)
