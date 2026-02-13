#!/usr/bin/env python3
"""
Environmental Sensor Test Tool

Test and debug BME280 and DHT sensors.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from sensors.environmental import BME280Sensor, DHTSensor, EnvironmentalData


def check_i2c():
    """Check if I2C is enabled and scan for devices."""
    import subprocess
    
    print("=" * 60)
    print("Checking I2C...")
    print("=" * 60)
    
    try:
        # Check if I2C is enabled
        result = subprocess.run(
            ['i2cdetect', '-y', '1'],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        if result.returncode == 0:
            print("✅ I2C is enabled")
            print("\nI2C devices found:")
            print(result.stdout)
            
            # Check for BME280 (0x76 or 0x77)
            if '76' in result.stdout:
                print("✅ Found device at 0x76 (likely BME280)")
                return 0x76
            elif '77' in result.stdout:
                print("✅ Found device at 0x77 (likely BME280)")
                return 0x77
            else:
                print("❌ No BME280 found at 0x76 or 0x77")
                return None
        else:
            print("❌ I2C not working")
            return None
    
    except FileNotFoundError:
        print("❌ i2cdetect not found")
        print("  Install with: sudo apt-get install i2c-tools")
        return None
    
    except Exception as e:
        print(f"❌ Error checking I2C: {e}")
        return None


def test_bme280(address=0x76, duration=30):
    """Test BME280 sensor."""
    print("\n" + "=" * 60)
    print(f"Testing BME280 at 0x{address:02x}...")
    print("=" * 60)
    
    try:
        sensor = BME280Sensor(i2c_address=address)
        sensor.connect()
        
        print("✅ BME280 connected successfully")
        
        # Read sensor multiple times
        print(f"\nReading sensor for {duration} seconds...")
        print()
        
        readings = []
        
        def on_data(data: EnvironmentalData):
            readings.append(data)
            speed = data.calculate_speed_of_sound()
            dew = data.calculate_dew_point()
            
            print(f"Temperature: {data.temperature:6.2f}°C | "
                  f"Humidity: {data.humidity:5.1f}% | "
                  f"Pressure: {data.pressure:7.2f} hPa | "
                  f"SoS: {speed:5.1f} m/s | "
                  f"Dew: {dew:5.1f}°C")
        
        sensor.add_callback(on_data)
        sensor.start()
        
        time.sleep(duration)
        sensor.stop()
        
        # Summary
        print("\n" + "=" * 60)
        print("Summary")
        print("=" * 60)
        
        if readings:
            avg_temp = sum(r.temperature for r in readings) / len(readings)
            avg_hum = sum(r.humidity for r in readings) / len(readings)
            avg_pres = sum(r.pressure for r in readings) / len(readings)
            
            print(f"Readings: {len(readings)}")
            print(f"Average temperature: {avg_temp:.2f}°C")
            print(f"Average humidity: {avg_hum:.1f}%")
            print(f"Average pressure: {avg_pres:.2f} hPa")
            
            # Calculate spread (stability check)
            temp_spread = max(r.temperature for r in readings) - min(r.temperature for r in readings)
            hum_spread = max(r.humidity for r in readings) - min(r.humidity for r in readings)
            
            print(f"\nStability:")
            print(f"Temperature spread: {temp_spread:.2f}°C")
            print(f"Humidity spread: {hum_spread:.1f}%")
            
            if temp_spread < 0.5 and hum_spread < 2:
                print("✅ Sensor readings are stable")
            else:
                print("⚠️  Sensor readings show variation (normal for changing conditions)")
        
        stats = sensor.get_stats()
        print(f"\nStatistics:")
        print(f"  Readings taken: {stats['readings_taken']}")
        print(f"  Read errors: {stats['read_errors']}")
        
        return True
    
    except ImportError:
        print("❌ BME280 library not installed")
        print("\nInstall with:")
        print("  pip install adafruit-circuitpython-bme280")
        print("  pip install adafruit-blinka")
        return False
    
    except Exception as e:
        print(f"❌ Failed to test BME280: {e}")
        return False


def test_dht(gpio_pin=4, sensor_type='DHT22', duration=30):
    """Test DHT sensor."""
    print("\n" + "=" * 60)
    print(f"Testing {sensor_type} on GPIO {gpio_pin}...")
    print("=" * 60)
    
    try:
        sensor = DHTSensor(gpio_pin=gpio_pin, sensor_type=sensor_type)
        sensor.connect()
        
        print(f"✅ {sensor_type} connected successfully")
        print("\nNote: DHT sensors may have occasional read errors (this is normal)")
        
        # Read sensor multiple times
        print(f"\nReading sensor for {duration} seconds...")
        print()
        
        readings = []
        
        def on_data(data: EnvironmentalData):
            readings.append(data)
            speed = data.calculate_speed_of_sound()
            
            print(f"Temperature: {data.temperature:6.2f}°C | "
                  f"Humidity: {data.humidity:5.1f}% | "
                  f"SoS: {speed:5.1f} m/s")
        
        sensor.add_callback(on_data)
        sensor.start()
        
        time.sleep(duration)
        sensor.stop()
        
        # Summary
        print("\n" + "=" * 60)
        print("Summary")
        print("=" * 60)
        
        if readings:
            avg_temp = sum(r.temperature for r in readings) / len(readings)
            avg_hum = sum(r.humidity for r in readings) / len(readings)
            
            print(f"Successful readings: {len(readings)}")
            print(f"Average temperature: {avg_temp:.2f}°C")
            print(f"Average humidity: {avg_hum:.1f}%")
        
        stats = sensor.get_stats()
        print(f"\nStatistics:")
        print(f"  Readings taken: {stats['readings_taken']}")
        print(f"  Read errors: {stats['read_errors']}")
        print(f"  Checksum errors: {stats['checksum_errors']}")
        
        # DHT sensors have frequent errors
        if stats['readings_taken'] > 0:
            error_rate = stats['read_errors'] / (stats['readings_taken'] + stats['read_errors'])
            print(f"  Error rate: {error_rate*100:.1f}%")
            
            if error_rate < 0.2:
                print("  ✅ Error rate is acceptable")
            else:
                print("  ⚠️  High error rate (check connections/power)")
        
        return True
    
    except ImportError:
        print(f"❌ DHT library not installed")
        print("\nInstall with:")
        print("  pip install adafruit-circuitpython-dht")
        print("  sudo apt-get install libgpiod2")
        return False
    
    except Exception as e:
        print(f"❌ Failed to test {sensor_type}: {e}")
        return False


def compare_sensors():
    """Compare readings from multiple sensors."""
    print("\n" + "=" * 60)
    print("Comparing Sensor Readings")
    print("=" * 60)
    print("\nThis will read from all available sensors simultaneously")
    print("and compare their readings.\n")
    
    # Try to initialize all sensors
    sensors = []
    
    # Try BME280
    try:
        bme = BME280Sensor()
        bme.connect()
        sensors.append(('BME280', bme))
        print("✅ BME280 available")
    except:
        print("❌ BME280 not available")
    
    # Try DHT22
    try:
        dht = DHTSensor(gpio_pin=4, sensor_type='DHT22')
        dht.connect()
        sensors.append(('DHT22', dht))
        print("✅ DHT22 available")
    except:
        print("❌ DHT22 not available")
    
    if not sensors:
        print("\n❌ No sensors available for comparison")
        return
    
    print(f"\nComparing {len(sensors)} sensor(s) for 30 seconds...\n")
    
    # Collect readings
    all_readings = {name: [] for name, _ in sensors}
    
    for name, sensor in sensors:
        def make_callback(sensor_name):
            def callback(data):
                all_readings[sensor_name].append(data)
            return callback
        
        sensor.add_callback(make_callback(name))
        sensor.start()
    
    time.sleep(30)
    
    for name, sensor in sensors:
        sensor.stop()
    
    # Compare
    print("\n" + "=" * 60)
    print("Comparison Results")
    print("=" * 60)
    
    for name, readings in all_readings.items():
        if readings:
            avg_temp = sum(r.temperature for r in readings) / len(readings)
            avg_hum = sum(r.humidity for r in readings) / len(readings)
            
            print(f"\n{name}:")
            print(f"  Temperature: {avg_temp:.2f}°C")
            print(f"  Humidity: {avg_hum:.1f}%")
            print(f"  Readings: {len(readings)}")
    
    # Temperature difference
    if len(all_readings) > 1:
        temps = []
        for readings in all_readings.values():
            if readings:
                temps.append(sum(r.temperature for r in readings) / len(readings))
        
        if len(temps) > 1:
            temp_diff = max(temps) - min(temps)
            print(f"\nTemperature difference: {temp_diff:.2f}°C")
            
            if temp_diff < 2.0:
                print("✅ Sensors agree well")
            else:
                print("⚠️  Significant difference (check sensor placement)")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Environmental Sensor Test Tool')
    parser.add_argument('--check-i2c', action='store_true',
                       help='Check I2C bus and scan for devices')
    parser.add_argument('--test-bme280', action='store_true',
                       help='Test BME280 sensor')
    parser.add_argument('--test-dht22', action='store_true',
                       help='Test DHT22 sensor')
    parser.add_argument('--test-dht11', action='store_true',
                       help='Test DHT11 sensor')
    parser.add_argument('--compare', action='store_true',
                       help='Compare multiple sensors')
    parser.add_argument('--gpio', type=int, default=4,
                       help='GPIO pin for DHT sensor (default: 4)')
    parser.add_argument('--i2c-address', type=str, default='0x76',
                       help='I2C address for BME280 (default: 0x76)')
    parser.add_argument('--duration', type=int, default=30,
                       help='Test duration in seconds (default: 30)')
    
    args = parser.parse_args()
    
    print("""
╔════════════════════════════════════════════════════════════╗
║        Environmental Sensor Test Tool                      ║
╚════════════════════════════════════════════════════════════╝
    """)
    
    if args.check_i2c:
        check_i2c()
    
    elif args.test_bme280:
        address = int(args.i2c_address, 16)
        test_bme280(address, args.duration)
    
    elif args.test_dht22:
        test_dht(args.gpio, 'DHT22', args.duration)
    
    elif args.test_dht11:
        test_dht(args.gpio, 'DHT11', args.duration)
    
    elif args.compare:
        compare_sensors()
    
    else:
        # Auto-detect and test
        print("Auto-detecting sensors...\n")
        
        # Check I2C
        address = check_i2c()
        
        if address:
            print("\nFound BME280, testing...")
            test_bme280(address, 10)
        
        print("\n" + "=" * 60)
        print("Test Options:")
        print("=" * 60)
        print()
        print("  python env_test.py --check-i2c         # Scan I2C bus")
        print("  python env_test.py --test-bme280       # Test BME280")
        print("  python env_test.py --test-dht22        # Test DHT22")
        print("  python env_test.py --test-dht11        # Test DHT11")
        print("  python env_test.py --compare           # Compare sensors")


if __name__ == "__main__":
    main()
