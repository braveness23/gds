# Environmental Sensor Setup Guide

## Why Environmental Sensors?

Environmental sensors provide:

1. **Speed of sound correction** (critical for trilateration)
   - Temperature affects sound speed by ~0.6 m/s per °C
   - 20°C error = 12 m/s speed error = significant position error

2. **Environmental monitoring**
   - Track weather conditions
   - Correlate detections with weather
   - Data logging and analysis

3. **System health**
   - Temperature monitoring (prevent overheating)
   - Humidity monitoring (condensation risk)

## Sensor Options

### BME280 (Recommended)

**Specifications:**
- Temperature: -40°C to +85°C (±1°C accuracy)
- Humidity: 0-100% (±3% accuracy)
- Pressure: 300-1100 hPa (±1 hPa accuracy)
- Interface: I2C
- Update rate: Up to 1Hz continuous
- Cost: $10-20

**Advantages:**
- ✅ Most accurate
- ✅ Includes pressure (for altitude/weather)
- ✅ Very reliable
- ✅ Low power
- ✅ Fast updates

**Disadvantages:**
- ❌ Requires I2C
- ❌ More expensive

### DHT22 (Budget Option)

**Specifications:**
- Temperature: -40°C to +80°C (±0.5°C accuracy)
- Humidity: 0-100% (±2-5% accuracy)
- No pressure sensor
- Interface: GPIO (1-wire)
- Update rate: 0.5Hz max (2 second minimum)
- Cost: $2-5

**Advantages:**
- ✅ Very cheap
- ✅ Simple GPIO interface
- ✅ Good enough for most uses

**Disadvantages:**
- ❌ Slower updates
- ❌ Frequent read errors (checksum failures)
- ❌ No pressure data
- ❌ Less reliable

### DHT11 (Ultra Budget)

**Specifications:**
- Temperature: 0°C to +50°C (±2°C accuracy)
- Humidity: 20-90% (±5% accuracy)
- Interface: GPIO
- Update rate: 1Hz max
- Cost: $1-2

**Recommendation:** Only use if you absolutely can't afford DHT22

## Hardware Setup

### BME280 Wiring (I2C)

```
BME280 Module       Raspberry Pi
VCC (3.3V)    →     Pin 1 (3.3V)
GND           →     Pin 6 (GND)
SCL           →     Pin 5 (GPIO 3, SCL)
SDA           →     Pin 3 (GPIO 2, SDA)
```

**I2C Address:**
- Usually 0x76 (default)
- Sometimes 0x77 (check module documentation)

### DHT22/DHT11 Wiring (GPIO)

```
DHT Sensor          Raspberry Pi
VCC (3.3V)    →     Pin 1 (3.3V)
GND           →     Pin 6 (GND)
DATA          →     Pin 7 (GPIO 4) [or any GPIO]
```

**Pull-up resistor:**
- 4.7kΩ - 10kΩ between DATA and VCC
- Often included on module boards
- Check if your module has it

## Software Setup

### Enable I2C (for BME280)

```bash
# Enable I2C
sudo raspi-config
# Navigate to: Interface Options → I2C → Enable

# Or edit directly
sudo nano /boot/firmware/config.txt
# Ensure: dtparam=i2c_arm=on

# Reboot
sudo reboot

# Verify I2C is enabled
ls /dev/i2c-*
# Should show: /dev/i2c-1

# Install I2C tools
sudo apt-get install i2c-tools

# Scan I2C bus
i2cdetect -y 1
```

**Expected output:**
```
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:          -- -- -- -- -- -- -- -- -- -- -- -- --
10: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
20: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
30: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
40: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
50: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
60: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
70: -- -- -- -- -- -- 76 --
```

The `76` shows BME280 at address 0x76.

### Install Python Libraries

**For BME280:**

```bash
# Adafruit libraries (recommended)
pip install adafruit-circuitpython-bme280
pip install adafruit-blinka

# Alternative: smbus library
# pip install smbus2
```

**For DHT:**

```bash
# Adafruit DHT library
pip install adafruit-circuitpython-dht

# System dependency
sudo apt-get install libgpiod2
```

## Testing

### Quick Test - BME280

```bash
# Auto-detect and test
python tools/env_test.py

# Or specific tests
python tools/env_test.py --check-i2c
python tools/env_test.py --test-bme280 --duration 30
```

**Expected output:**
```
Temperature:  23.45°C | Humidity:  45.2% | Pressure: 1013.25 hPa | SoS: 345.2 m/s
Temperature:  23.46°C | Humidity:  45.3% | Pressure: 1013.27 hPa | SoS: 345.3 m/s
...
```

### Quick Test - DHT22

```bash
python tools/env_test.py --test-dht22 --gpio 4 --duration 30
```

**Expected output:**
```
Temperature:  23.1°C | Humidity:  46.0% | SoS: 345.0 m/s
Temperature:  23.2°C | Humidity:  45.8% | SoS: 345.1 m/s
...
```

**Note:** DHT sensors may show occasional read errors - this is normal!

### Compare Multiple Sensors

```bash
python tools/env_test.py --compare
```

This will test all available sensors simultaneously and compare readings.

## Using in Code

### Basic Usage

```python
from sensors.environmental import BME280Sensor
from core.event_bus import get_event_bus

# Create sensor
event_bus = get_event_bus()
sensor = BME280Sensor(event_bus=event_bus)

# Connect and start
sensor.connect()
sensor.start()

# Get current reading
data = sensor.get_data()
if data:
    print(f"Temperature: {data.temperature}°C")
    print(f"Humidity: {data.humidity}%")
    print(f"Pressure: {data.pressure} hPa")

    # Calculate speed of sound
    speed = data.calculate_speed_of_sound()
    print(f"Speed of sound: {speed} m/s")

# Stop when done
sensor.stop()
```

### With Callback

```python
def on_environmental_update(data):
    temp = data.temperature
    humidity = data.humidity
    speed = data.calculate_speed_of_sound()

    print(f"Temp: {temp:.1f}°C, Humidity: {humidity:.1f}%, SoS: {speed:.1f} m/s")

    # Update trilateration server with new speed of sound
    # trilateration.update_speed_of_sound(speed)

sensor.add_callback(on_environmental_update)
sensor.start()
```

### Factory Function (Recommended)

```python
from sensors.environmental import create_environmental_sensor
from config.config import Config

# Automatically chooses BME280, DHT22, or None based on config
config = Config('config.yaml')
sensor = create_environmental_sensor(config, event_bus)

if sensor:
    sensor.connect()
    sensor.start()
```

## Configuration

### BME280 Configuration

```yaml
sensors:
  environmental:
    type: "bme280"           # Use BME280
    i2c_address: "0x76"      # I2C address (0x76 or 0x77)
    update_interval: 5.0     # Read every 5 seconds
```

### DHT22 Configuration

```yaml
sensors:
  environmental:
    type: "dht22"            # Use DHT22
    gpio_pin: 4              # GPIO pin number (BCM)
    update_interval: 10.0    # Read every 10 seconds (min 2.0)
```

### DHT11 Configuration

```yaml
sensors:
  environmental:
    type: "dht11"            # Use DHT11
    gpio_pin: 4              # GPIO pin number
    update_interval: 10.0    # Read every 10 seconds
```

### No Sensor

```yaml
sensors:
  environmental:
    type: "none"             # No environmental sensor
```

## Speed of Sound Calculation

### Why It Matters

Speed of sound varies with temperature:

```
Temperature    Speed of Sound
0°C           331 m/s
10°C          337 m/s
20°C          343 m/s (standard)
30°C          349 m/s
40°C          355 m/s
```

**Impact on trilateration:**
- 1°C error → ~0.6 m/s speed error
- At 1km distance → ~1.7m position error
- At 10km distance → ~17m position error

### Formulas

**Simple (temperature only):**
```python
v = 331.3 + (0.606 * temperature_celsius)
```

**Accurate (temperature + humidity):**
```python
import math

temp_ratio = 1 + (temperature / 273.15)
humidity_factor = 1 + (0.0124 * (humidity / 100.0))
v = 331.3 * math.sqrt(temp_ratio) * math.sqrt(humidity_factor)
```

**EnvironmentalData provides this:**
```python
data = sensor.get_data()
speed = data.calculate_speed_of_sound()
```

### Updating Trilateration Server

```python
# In trilateration server
def on_environmental_update(data):
    speed = data.calculate_speed_of_sound()
    trilateration_engine.update_speed_of_sound(speed)

# Subscribe to environmental updates from nodes
mqtt_client.subscribe("gunshot/+/environmental")
```

## Common Issues

### Issue: i2cdetect shows nothing

**Symptoms:**
```bash
i2cdetect -y 1
# Shows all -- with no addresses
```

**Solutions:**

1. **Check I2C is enabled:**
```bash
ls /dev/i2c-*
# Should show /dev/i2c-1
```

2. **Check connections:**
   - VCC to 3.3V (not 5V!)
   - GND to GND
   - SCL to GPIO 3 (Pin 5)
   - SDA to GPIO 2 (Pin 3)

3. **Try other I2C bus:**
```bash
i2cdetect -y 0  # Some systems use bus 0
```

4. **Check module is powered:**
   - Measure voltage at VCC pin
   - Should be ~3.3V

### Issue: BME280 connection fails

**Error:**
```
OSError: [Errno 121] Remote I/O error
```

**Solutions:**

1. **Check I2C address:**
```bash
i2cdetect -y 1
# Note the address (76 or 77)
```

2. **Try both addresses:**
```python
sensor = BME280Sensor(i2c_address=0x77)  # Try 0x77 instead of 0x76
```

3. **Check wiring again:**
   - Loose connections are common
   - Try wiggling wires

### Issue: DHT sensor constant read errors

**Symptoms:**
```
RuntimeError: Checksum did not validate
```

**This is normal!** DHT sensors have frequent checksum errors.

**Solutions:**

1. **Ensure minimum 2 second interval:**
```python
sensor = DHTSensor(update_interval=10.0)  # Not less than 2.0
```

2. **Check pull-up resistor:**
   - 4.7kΩ between DATA and VCC
   - Some modules have it built-in

3. **Check power:**
   - DHT needs stable 3.3V
   - Try separate power supply if needed

4. **Accept some errors:**
   - 10-20% error rate is normal
   - System averages out errors

### Issue: Temperature readings seem wrong

**Symptoms:**
- Temperature much higher than expected
- Different from room temperature

**Causes:**

1. **Self-heating:**
   - Raspberry Pi generates heat
   - Sensor near Pi reads higher

   **Solution:** Mount sensor away from Pi (use cable)

2. **Sunlight:**
   - Direct sunlight heats sensor

   **Solution:** Shade sensor or mount in enclosure

3. **Enclosure heat:**
   - Plastic enclosures trap heat

   **Solution:** Ventilate enclosure

### Issue: Humidity readings unstable

**Causes:**

1. **Settling time:**
   - Sensors need time to stabilize
   - Wait 5-10 minutes after power-on

2. **Rapid changes:**
   - Humidity can change quickly
   - This is normal environmental variation

3. **Breath:**
   - Your breath has high humidity
   - Don't breathe on sensor during testing!

## Best Practices

1. ✅ **Use BME280 if budget allows**
   - More reliable
   - Faster updates
   - Includes pressure

2. ✅ **Mount sensor away from Pi**
   - Use ribbon cable or wire
   - Prevents self-heating
   - More accurate readings

3. ✅ **Shield from elements**
   - Protect from rain/snow
   - Allow air circulation
   - Weatherproof enclosure with vents

4. ✅ **Log environmental data**
   - Track trends
   - Correlate with detections
   - Debug issues

5. ✅ **Update speed of sound in real-time**
   - Send to trilateration server
   - Improves position accuracy
   - Essential for large temperature variations

6. ✅ **Monitor sensor health**
   - Check for failed readings
   - Alert on sensor failure
   - Have fallback speed of sound value

## Sensor Placement

### For Accurate Temperature

```
❌ Bad:
- Next to Raspberry Pi (self-heating)
- In direct sunlight (solar heating)
- In sealed enclosure (heat buildup)
- Near heat sources (CPU, regulators)

✅ Good:
- Separate from Pi (10+ cm away)
- Shaded location
- Ventilated enclosure
- White/reflective housing
```

### For Acoustic Monitoring

```
✅ Best:
- Near microphone location
- Same environmental conditions
- Representative of area
```

## Integration with System

### Environmental Data Flow

```
BME280/DHT Sensor
    ↓
Environmental Module
    ↓
Event Bus
    ↓
├─→ MQTT Output (publish to broker)
├─→ System Monitor (log locally)
└─→ File Logger (save to disk)
    ↓
MQTT Broker
    ↓
Trilateration Server (update speed of sound)
```

### In Detection Messages

Environmental data automatically included:

```json
{
  "node_id": "gunshot_001",
  "timestamp": 1707436789.123,
  "detection": {...},
  "location": {...},
  "environment": {
    "temperature": 23.5,
    "humidity": 45.2,
    "pressure": 1013.25
  }
}
```

### In Trilateration

```python
# Trilateration server receives environmental data
def on_environmental_message(msg):
    data = json.loads(msg.payload)
    temp = data['environment']['temperature']
    humidity = data['environment']['humidity']

    # Calculate speed of sound
    speed = calculate_speed_of_sound(temp, humidity)

    # Update engine
    engine.update_speed_of_sound(speed)
```

## Calibration

### Temperature Calibration

```python
# Compare with reference thermometer
reference_temp = 23.5  # From calibrated thermometer
sensor_temp = sensor.get_data().temperature

offset = reference_temp - sensor_temp

# Apply correction
calibrated_temp = sensor_temp + offset
```

### Humidity Calibration

More complex - use salt test:

1. Put sensor in sealed container with saturated salt solution
2. NaCl (table salt) → 75% humidity
3. Wait 8-12 hours for stabilization
4. Read sensor
5. Apply offset

## Advanced: Multiple Sensors

### Redundancy

```python
# Use multiple sensors for reliability
sensors = [
    BME280Sensor(i2c_address=0x76),
    BME280Sensor(i2c_address=0x77),
    DHTSensor(gpio_pin=4)
]

# Average readings
temps = [s.get_data().temperature for s in sensors if s.get_data()]
avg_temp = sum(temps) / len(temps)
```

### Spatial Array

```python
# Multiple locations for environmental mapping
sensors = {
    'north': BME280Sensor(i2c_address=0x76),
    'south': BME280Sensor(i2c_address=0x77),
    'east': DHTSensor(gpio_pin=4)
}

# Track gradients
temps = {loc: s.get_data().temperature for loc, s in sensors.items()}
temp_gradient = max(temps.values()) - min(temps.values())
```

## Troubleshooting Checklist

BME280:
- [ ] I2C enabled in raspi-config
- [ ] i2cdetect shows device at 0x76 or 0x77
- [ ] Libraries installed (adafruit-circuitpython-bme280, adafruit-blinka)
- [ ] Correct wiring (3.3V, GND, SCL, SDA)
- [ ] Tested with tools/env_test.py

DHT:
- [ ] Libraries installed (adafruit-circuitpython-dht, libgpiod2)
- [ ] Pull-up resistor present (4.7kΩ-10kΩ)
- [ ] Correct wiring (3.3V, GND, DATA)
- [ ] GPIO pin correct in config
- [ ] Update interval ≥ 2.0 seconds
- [ ] Accepting ~10-20% read errors as normal

## Further Reading

- BME280 datasheet: https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bme280-ds002.pdf
- DHT22 datasheet: https://www.sparkfun.com/datasheets/Sensors/Temperature/DHT22.pdf
- Speed of sound calculator: https://www.engineeringtoolbox.com/speed-sound-gases-d_1108.html
- Adafruit BME280 guide: https://learn.adafruit.com/adafruit-bme280-humidity-barometric-pressure-temperature-sensor-breakout
