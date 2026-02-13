"""Environmental sensors for temperature, humidity, and pressure.

This module provides:
- BME280: Temperature, humidity, and pressure (I2C)
- DHT22/DHT11: Temperature and humidity (GPIO)

Environmental data is used for:
- Speed of sound correction (temperature affects acoustic trilateration)
- Environmental monitoring
- Data logging and analysis
"""

import time
import threading
from dataclasses import dataclass
from typing import Optional, Callable, List
from core.event_bus import Event, EventType
from sensors.base import BaseSensor


@dataclass
class EnvironmentalData:
    """Environmental sensor readings."""
    temperature: float  # Celsius
    humidity: float     # Percent (0-100)
    pressure: float     # hPa (hectopascals/millibars)
    timestamp: float    # Unix timestamp
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'temperature': self.temperature,
            'humidity': self.humidity,
            'pressure': self.pressure,
            'timestamp': self.timestamp
        }
    
    def calculate_speed_of_sound(self) -> float:
        """
        Calculate speed of sound based on temperature and humidity.
        
        Returns:
            Speed of sound in m/s
        
        Formula (simplified):
            v = 331.3 + 0.606 * T
        
        More accurate formula includes humidity:
            v = 331.3 * sqrt(1 + T/273.15) * sqrt(1 + 0.0124 * H)
        
        Where:
            T = temperature in Celsius
            H = relative humidity in percent
        """
        # Simplified formula (good enough for most uses)
        v_simple = 331.3 + (0.606 * self.temperature)
        
        # More accurate with humidity correction
        # Convert to Kelvin ratio
        temp_ratio = 1 + (self.temperature / 273.15)
        humidity_factor = 1 + (0.0124 * (self.humidity / 100.0))
        
        v_accurate = 331.3 * (temp_ratio ** 0.5) * (humidity_factor ** 0.5)
        
        return v_accurate
    
    def calculate_dew_point(self) -> float:
        """
        Calculate dew point temperature.
        
        Returns:
            Dew point in Celsius
        
        Uses Magnus formula approximation.
        """
        a = 17.27
        b = 237.7
        
        alpha = ((a * self.temperature) / (b + self.temperature)) + \
                (self.humidity / 100.0)
        
        dew_point = (b * alpha) / (a - alpha)
        return dew_point


class BME280Sensor(BaseSensor[EnvironmentalData]):
    """
    BME280 temperature, humidity, and pressure sensor.
    
    Uses I2C interface. This is the recommended sensor for:
    - Accurate temperature readings
    - Barometric pressure (for weather monitoring)
    - Humidity
    
    Typical I2C addresses: 0x76 or 0x77
    """
    
    def __init__(self,
                 i2c_address: int = 0x76,
                 update_interval: float = 5.0,
                 event_bus=None):
        """
        Initialize BME280 sensor.
        
        Args:
            i2c_address: I2C address (0x76 or 0x77)
            update_interval: How often to read sensor (seconds)
            event_bus: Event bus for publishing updates
        """
        super().__init__(
            update_interval=update_interval,
            event_bus=event_bus,
            event_type=EventType.SYSTEM,
            sensor_name="BME280"
        )
        
        self.i2c_address = i2c_address
        self.sensor = None
        
        # Track periodic logging
        self._log_counter = 0
    
    def _connect(self):
        """Connect to BME280 sensor."""
        try:
            # Try Adafruit library first (most common)
            import board
            import adafruit_bme280.advanced as adafruit_bme280
            
            i2c = board.I2C()
            self.sensor = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=self.i2c_address)
            
            # Configure sensor for weather monitoring
            self.sensor.sea_level_pressure = 1013.25  # Standard pressure
            
            print(f"[BME280] Connected at I2C address 0x{self.i2c_address:02x}")
            
        except ImportError:
            print("[BME280] Adafruit BME280 library not installed")
            print("  Install with: pip install adafruit-circuitpython-bme280")
            print("  Also needs: pip install adafruit-blinka")
            raise
        
        except Exception as e:
            print(f"[BME280] Failed to connect: {e}")
            print(f"  Check:")
            print(f"    - I2C is enabled (sudo raspi-config)")
            print(f"    - BME280 is connected to I2C pins")
            print(f"    - Correct I2C address (try 0x76 or 0x77)")
            print(f"    - Run: i2cdetect -y 1")
            raise
    
    def _read_sensor(self) -> Optional[EnvironmentalData]:
        """Read sensor values."""
        try:
            # Read from sensor
            temperature = self.sensor.temperature
            humidity = self.sensor.humidity
            pressure = self.sensor.pressure
            
            # Validate readings
            if temperature < -40 or temperature > 85:
                print(f"[BME280] Invalid temperature: {temperature}")
                return None
            
            if humidity < 0 or humidity > 100:
                print(f"[BME280] Invalid humidity: {humidity}")
                return None
            
            if pressure < 300 or pressure > 1100:
                print(f"[BME280] Invalid pressure: {pressure}")
                return None
            
            # Log periodically (every minute at 5s interval)
            self._log_counter += 1
            if self._log_counter % 12 == 0:
                print(f"[BME280] {temperature:.1f}°C, {humidity:.1f}%, {pressure:.1f} hPa")
            
            return EnvironmentalData(
                temperature=temperature,
                humidity=humidity,
                pressure=pressure,
                timestamp=time.time()
            )
        
        except Exception as e:
            print(f"[BME280] Error reading sensor: {e}")
            return None


class DHTSensor(BaseSensor[EnvironmentalData]):
    """
    DHT22 or DHT11 temperature and humidity sensor.
    
    Uses GPIO interface. This is a budget alternative to BME280:
    - No pressure sensor
    - Less accurate
    - Slower update rate (2 seconds minimum)
    - More prone to read errors
    
    But much cheaper ($2-5 vs $10-20 for BME280).
    """
    
    def __init__(self,
                 gpio_pin: int,
                 sensor_type: str = 'DHT22',
                 update_interval: float = 10.0,
                 event_bus=None):
        """
        Initialize DHT sensor.
        
        Args:
            gpio_pin: GPIO pin number (BCM numbering)
            sensor_type: 'DHT22' or 'DHT11'
            update_interval: How often to read (seconds, minimum 2.0)
            event_bus: Event bus for publishing updates
        """
        super().__init__(
            update_interval=max(update_interval, 2.0),  # DHT needs 2s minimum
            event_bus=event_bus,
            event_type=EventType.SYSTEM,
            sensor_name=sensor_type.upper()
        )
        
        self.gpio_pin = gpio_pin
        self.sensor_type = sensor_type
        self.sensor = None
        
        # Track checksum errors specific to DHT
        self.stats['checksum_errors'] = 0
        
        # Track periodic logging
        self._log_counter = 0
    
    def _connect(self):
        """Connect to DHT sensor."""
        try:
            import adafruit_dht
            import board
            
            # Get board pin object
            pin = getattr(board, f'D{self.gpio_pin}')
            
            # Create sensor object
            if self.sensor_type.upper() == 'DHT22':
                self.sensor = adafruit_dht.DHT22(pin)
            elif self.sensor_type.upper() == 'DHT11':
                self.sensor = adafruit_dht.DHT11(pin)
            else:
                raise ValueError(f"Unknown sensor type: {self.sensor_type}")
            
            print(f"[{self.sensor_type}] Connected on GPIO {self.gpio_pin}")
            
            # DHT needs time to stabilize
            time.sleep(2)
        
        except ImportError:
            print(f"[{self.sensor_type}] Adafruit DHT library not installed")
            print("  Install with: pip install adafruit-circuitpython-dht")
            print("  Also needs: sudo apt-get install libgpiod2")
            raise
        
        except Exception as e:
            print(f"[{self.sensor_type}] Failed to connect: {e}")
            print(f"  Check:")
            print(f"    - DHT sensor connected to GPIO {self.gpio_pin}")
            print(f"    - Correct sensor type ({self.sensor_type})")
            print(f"    - Pull-up resistor (4.7k-10k ohm) if needed")
            raise
    
    def _disconnect(self):
        """Clean up GPIO resources."""
        if self.sensor:
            try:
                self.sensor.exit()
                print(f"[{self.sensor_type}] GPIO cleaned up")
            except Exception as e:
                print(f"[{self.sensor_type}] Error cleaning up GPIO: {e}")
    
    def _read_sensor(self) -> Optional[EnvironmentalData]:
        """Read sensor values."""
        try:
            # Read from sensor
            temperature = self.sensor.temperature
            humidity = self.sensor.humidity
            
            # DHT sensors are prone to read errors
            if temperature is None or humidity is None:
                return None
            
            # Validate readings
            if self.sensor_type == 'DHT22':
                # DHT22: -40 to 80°C, 0-100% humidity
                if temperature < -40 or temperature > 80:
                    print(f"[{self.sensor_type}] Invalid temperature: {temperature}")
                    return None
            else:
                # DHT11: 0 to 50°C, 20-90% humidity
                if temperature < 0 or temperature > 50:
                    print(f"[{self.sensor_type}] Invalid temperature: {temperature}")
                    return None
            
            if humidity < 0 or humidity > 100:
                print(f"[{self.sensor_type}] Invalid humidity: {humidity}")
                return None
            
            # Log periodically (every minute at 10s interval)
            self._log_counter += 1
            if self._log_counter % 6 == 0:
                print(f"[{self.sensor_type}] {temperature:.1f}°C, {humidity:.1f}%")
            
            return EnvironmentalData(
                temperature=temperature,
                humidity=humidity,
                pressure=1013.25,  # DHT doesn't measure pressure, use standard
                timestamp=time.time()
            )
        
        except RuntimeError as e:
            # DHT sensors commonly have checksum errors
            if 'checksum' in str(e).lower():
                self.stats['checksum_errors'] += 1
            return None
        
        except Exception as e:
            print(f"[{self.sensor_type}] Error reading sensor: {e}")
            return None


def create_environmental_sensor(config: dict, event_bus=None):
    """
    Factory function to create environmental sensor from config.
    
    Returns appropriate sensor based on configuration.
    """
    env_config = config.get('sensors', {}).get('environmental', {})
    
    sensor_type = env_config.get('type', 'none').lower()
    
    if sensor_type == 'bme280':
        # Use BME280 (recommended)
        sensor = BME280Sensor(
            i2c_address=int(env_config.get('i2c_address', '0x76'), 16),
            update_interval=env_config.get('update_interval', 5.0),
            event_bus=event_bus
        )
        return sensor
    
    elif sensor_type in ['dht22', 'dht11']:
        # Use DHT sensor
        sensor = DHTSensor(
            gpio_pin=env_config.get('gpio_pin', 4),
            sensor_type=sensor_type.upper(),
            update_interval=env_config.get('update_interval', 10.0),
            event_bus=event_bus
        )
        return sensor
    
    else:
        # No environmental sensor
        print("[Environmental] No sensor configured")
        return None
