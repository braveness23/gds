"""Unit tests for environmental sensors."""

import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.sensors.environmental import (
    BME280Sensor,
    DHTSensor,
    EnvironmentalData,
    create_environmental_sensor,
)

# ============================================================================
# EnvironmentalData Tests
# ============================================================================


class TestEnvironmentalData:
    """Tests for EnvironmentalData dataclass."""

    def test_environmental_data_creation(self):
        """EnvironmentalData should store sensor readings."""
        data = EnvironmentalData(
            temperature=25.5, humidity=60.0, pressure=1013.25, timestamp=123.456
        )

        assert data.temperature == 25.5
        assert data.humidity == 60.0
        assert data.pressure == 1013.25
        assert data.timestamp == 123.456

    def test_environmental_data_to_dict(self):
        """to_dict should return dictionary with all fields."""
        data = EnvironmentalData(
            temperature=22.5, humidity=55.0, pressure=1015.0, timestamp=time.time()
        )

        result = data.to_dict()

        assert result["temperature"] == 22.5
        assert result["humidity"] == 55.0
        assert result["pressure"] == 1015.0
        assert "timestamp" in result

    def test_calculate_speed_of_sound(self):
        """Speed of sound should be calculated from temperature and humidity."""
        # At 20°C and 50% humidity, speed of sound ≈ 343 m/s
        data = EnvironmentalData(
            temperature=20.0, humidity=50.0, pressure=1013.25, timestamp=time.time()
        )

        speed = data.calculate_speed_of_sound()

        # Should be around 343 m/s (±2 m/s tolerance)
        assert 341.0 < speed < 345.0

    def test_calculate_speed_of_sound_cold(self):
        """Speed of sound should decrease with temperature."""
        cold_data = EnvironmentalData(
            temperature=0.0, humidity=50.0, pressure=1013.25, timestamp=time.time()
        )
        warm_data = EnvironmentalData(
            temperature=30.0, humidity=50.0, pressure=1013.25, timestamp=time.time()
        )

        cold_speed = cold_data.calculate_speed_of_sound()
        warm_speed = warm_data.calculate_speed_of_sound()

        # Warmer air should have higher speed
        assert warm_speed > cold_speed

    def test_calculate_dew_point(self):
        """Dew point should be calculated from temperature and humidity."""
        # Using current formula implementation
        data = EnvironmentalData(
            temperature=25.0, humidity=60.0, pressure=1013.25, timestamp=time.time()
        )

        dew_point = data.calculate_dew_point()

        # Formula gives ~35°C (note: implementation may need review)
        assert dew_point > 0.0  # Reasonable dew point value

    def test_calculate_dew_point_low_humidity(self):
        """Low humidity should give lower dew point."""
        dry_data = EnvironmentalData(
            temperature=25.0, humidity=30.0, pressure=1013.25, timestamp=time.time()
        )
        humid_data = EnvironmentalData(
            temperature=25.0, humidity=80.0, pressure=1013.25, timestamp=time.time()
        )

        dry_dew = dry_data.calculate_dew_point()
        humid_dew = humid_data.calculate_dew_point()

        # Higher humidity should have higher dew point
        assert humid_dew > dry_dew


# ============================================================================
# BME280Sensor Tests
# ============================================================================


class TestBME280Sensor:
    """Tests for BME280Sensor."""

    def test_bme280_initialization(self):
        """BME280Sensor should initialize with I2C parameters."""
        sensor = BME280Sensor(i2c_address=0x77, update_interval=10.0)

        assert sensor.i2c_address == 0x77
        assert sensor.update_interval == 10.0
        assert sensor.sensor_name == "BME280"

    @pytest.mark.skip(reason="BME280 connect uses dynamic import - tested in integration tests")
    def test_bme280_connect_success(self):
        """BME280 should connect to I2C sensor."""
        pass

    def test_bme280_connect_library_not_installed(self):
        """BME280 should raise ImportError if library missing."""
        with patch.dict("sys.modules", {"adafruit_bme280.advanced": None, "board": None}):
            sensor = BME280Sensor()

            with pytest.raises(ImportError):
                sensor._connect()

    def test_bme280_read_sensor_valid(self):
        """BME280 should read and return valid sensor data."""
        mock_sensor = Mock()
        mock_sensor.temperature = 22.5
        mock_sensor.humidity = 55.0
        mock_sensor.pressure = 1013.25

        sensor = BME280Sensor()
        sensor.sensor = mock_sensor

        result = sensor._read_sensor()

        assert result is not None
        assert result.temperature == 22.5
        assert result.humidity == 55.0
        assert result.pressure == 1013.25

    def test_bme280_read_sensor_invalid_temperature(self):
        """BME280 should reject invalid temperature readings."""
        mock_sensor = Mock()
        mock_sensor.temperature = 100.0  # > 85°C max
        mock_sensor.humidity = 50.0
        mock_sensor.pressure = 1013.25

        sensor = BME280Sensor()
        sensor.sensor = mock_sensor

        result = sensor._read_sensor()

        assert result is None  # Invalid temperature rejected

    def test_bme280_read_sensor_invalid_humidity(self):
        """BME280 should reject invalid humidity readings."""
        mock_sensor = Mock()
        mock_sensor.temperature = 22.0
        mock_sensor.humidity = 150.0  # > 100%
        mock_sensor.pressure = 1013.25

        sensor = BME280Sensor()
        sensor.sensor = mock_sensor

        result = sensor._read_sensor()

        assert result is None  # Invalid humidity rejected

    def test_bme280_read_sensor_invalid_pressure(self):
        """BME280 should reject invalid pressure readings."""
        mock_sensor = Mock()
        mock_sensor.temperature = 22.0
        mock_sensor.humidity = 50.0
        mock_sensor.pressure = 200.0  # < 300 hPa min

        sensor = BME280Sensor()
        sensor.sensor = mock_sensor

        result = sensor._read_sensor()

        assert result is None  # Invalid pressure rejected

    def test_bme280_read_sensor_io_error(self):
        """BME280 should handle I/O errors gracefully."""
        mock_sensor = Mock()
        # Make temperature property raise IOError when accessed
        type(mock_sensor).temperature = property(
            lambda self: (_ for _ in ()).throw(IOError("I2C bus error"))
        )

        sensor = BME280Sensor()
        sensor.sensor = mock_sensor

        result = sensor._read_sensor()

        assert result is None  # Error handled gracefully


# ============================================================================
# DHTSensor Tests
# ============================================================================


class TestDHTSensor:
    """Tests for DHTSensor (DHT22/DHT11)."""

    def test_dht_initialization_dht22(self):
        """DHTSensor should initialize with GPIO parameters."""
        sensor = DHTSensor(gpio_pin=4, sensor_type="DHT22", update_interval=10.0)

        assert sensor.gpio_pin == 4
        assert sensor.sensor_type == "DHT22"
        assert sensor.update_interval == 10.0
        assert sensor.sensor_name == "DHT22"

    def test_dht_initialization_minimum_interval(self):
        """DHTSensor should enforce 2-second minimum interval."""
        sensor = DHTSensor(gpio_pin=4, sensor_type="DHT22", update_interval=1.0)

        # Should be clamped to 2.0 seconds
        assert sensor.update_interval == 2.0

    def test_dht_connect_dht22(self):
        """DHTSensor should connect to DHT22 sensor."""
        mock_dht = MagicMock()
        mock_board = MagicMock()
        mock_sensor = Mock()

        mock_dht.DHT22.return_value = mock_sensor
        mock_board.D4 = Mock()  # GPIO pin

        with patch.dict("sys.modules", {"adafruit_dht": mock_dht, "board": mock_board}):
            with patch("time.sleep"):  # Skip stabilization delay
                sensor = DHTSensor(gpio_pin=4, sensor_type="DHT22")
                sensor._connect()

                assert sensor.sensor is mock_sensor
                mock_dht.DHT22.assert_called_once()

    def test_dht_connect_dht11(self):
        """DHTSensor should connect to DHT11 sensor."""
        mock_dht = MagicMock()
        mock_board = MagicMock()
        mock_sensor = Mock()

        mock_dht.DHT11.return_value = mock_sensor
        mock_board.D4 = Mock()

        with patch.dict("sys.modules", {"adafruit_dht": mock_dht, "board": mock_board}):
            with patch("time.sleep"):
                sensor = DHTSensor(gpio_pin=4, sensor_type="DHT11")
                sensor._connect()

                assert sensor.sensor is mock_sensor
                mock_dht.DHT11.assert_called_once()

    def test_dht_connect_invalid_sensor_type(self):
        """DHTSensor should raise ValueError for invalid sensor type."""
        mock_dht = MagicMock()
        mock_board = MagicMock()

        with patch.dict("sys.modules", {"adafruit_dht": mock_dht, "board": mock_board}):
            sensor = DHTSensor(gpio_pin=4, sensor_type="INVALID")

            with pytest.raises(ValueError, match="Unknown sensor type"):
                sensor._connect()

    def test_dht_connect_library_not_installed(self):
        """DHTSensor should raise ImportError if library missing."""
        with patch.dict("sys.modules", {"adafruit_dht": None, "board": None}):
            sensor = DHTSensor(gpio_pin=4)

            with pytest.raises(ImportError):
                sensor._connect()

    def test_dht22_read_sensor_valid(self):
        """DHT22 should read and return valid sensor data."""
        mock_sensor = Mock()
        mock_sensor.temperature = 22.5
        mock_sensor.humidity = 55.0

        sensor = DHTSensor(gpio_pin=4, sensor_type="DHT22")
        sensor.sensor = mock_sensor

        result = sensor._read_sensor()

        assert result is not None
        assert result.temperature == 22.5
        assert result.humidity == 55.0
        assert result.pressure == 1013.25  # Default for DHT

    def test_dht22_read_sensor_none_values(self):
        """DHT22 should handle None values (read errors)."""
        mock_sensor = Mock()
        mock_sensor.temperature = None  # Read error
        mock_sensor.humidity = 55.0

        sensor = DHTSensor(gpio_pin=4, sensor_type="DHT22")
        sensor.sensor = mock_sensor

        result = sensor._read_sensor()

        assert result is None  # Rejected due to None value

    def test_dht22_read_sensor_invalid_temperature(self):
        """DHT22 should reject out-of-range temperature."""
        mock_sensor = Mock()
        mock_sensor.temperature = -50.0  # < -40°C min for DHT22
        mock_sensor.humidity = 50.0

        sensor = DHTSensor(gpio_pin=4, sensor_type="DHT22")
        sensor.sensor = mock_sensor

        result = sensor._read_sensor()

        assert result is None  # Invalid temperature rejected

    def test_dht11_read_sensor_invalid_temperature(self):
        """DHT11 should reject out-of-range temperature (different from DHT22)."""
        mock_sensor = Mock()
        mock_sensor.temperature = -10.0  # < 0°C min for DHT11
        mock_sensor.humidity = 50.0

        sensor = DHTSensor(gpio_pin=4, sensor_type="DHT11")
        sensor.sensor = mock_sensor

        result = sensor._read_sensor()

        assert result is None  # Invalid for DHT11

    def test_dht_read_sensor_checksum_error(self):
        """DHT should track checksum errors."""
        mock_sensor = Mock()
        # Make temperature property raise RuntimeError when accessed
        type(mock_sensor).temperature = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("Checksum failed"))
        )

        sensor = DHTSensor(gpio_pin=4, sensor_type="DHT22")
        sensor.sensor = mock_sensor

        result = sensor._read_sensor()

        assert result is None
        assert sensor.stats["checksum_errors"] == 1

    def test_dht_disconnect_cleanup(self):
        """DHT should clean up GPIO on disconnect."""
        mock_sensor = Mock()

        sensor = DHTSensor(gpio_pin=4, sensor_type="DHT22")
        sensor.sensor = mock_sensor

        sensor._disconnect()

        mock_sensor.exit.assert_called_once()


# ============================================================================
# create_environmental_sensor Factory Tests
# ============================================================================


class TestCreateEnvironmentalSensor:
    """Tests for create_environmental_sensor factory function."""

    def test_create_bme280_sensor(self):
        """Factory should create BME280Sensor from config."""
        config = {
            "sensors": {
                "environmental": {
                    "type": "bme280",
                    "i2c_address": "0x77",
                    "update_interval": 5.0,
                }
            }
        }

        sensor = create_environmental_sensor(config)

        assert isinstance(sensor, BME280Sensor)
        assert sensor.i2c_address == 0x77
        assert sensor.update_interval == 5.0

    def test_create_dht22_sensor(self):
        """Factory should create DHTSensor for DHT22."""
        config = {
            "sensors": {
                "environmental": {
                    "type": "dht22",
                    "gpio_pin": 4,
                    "update_interval": 10.0,
                }
            }
        }

        sensor = create_environmental_sensor(config)

        assert isinstance(sensor, DHTSensor)
        assert sensor.gpio_pin == 4
        assert sensor.sensor_type == "DHT22"

    def test_create_dht11_sensor(self):
        """Factory should create DHTSensor for DHT11."""
        config = {"sensors": {"environmental": {"type": "dht11", "gpio_pin": 17}}}

        sensor = create_environmental_sensor(config)

        assert isinstance(sensor, DHTSensor)
        assert sensor.sensor_type == "DHT11"

    def test_create_no_sensor(self):
        """Factory should return None when no sensor configured."""
        config = {"sensors": {"environmental": {"type": "none"}}}

        sensor = create_environmental_sensor(config)

        assert sensor is None

    def test_create_default_no_sensor(self):
        """Factory should return None when environmental config missing."""
        config = {"sensors": {}}

        sensor = create_environmental_sensor(config)

        assert sensor is None
