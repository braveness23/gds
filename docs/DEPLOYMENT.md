# Deployment Guide

## Fleet Deployment

### Prerequisites

- Multiple Raspberry Pi 4/5 boards
- MicroSD cards (16GB+ each)
- I2S MEMS microphones
- GPS modules with PPS (optional but recommended)
- Network access (WiFi or Ethernet)
- MQTT broker (central server or cloud)

### Setup Process

#### 1. Prepare SD Cards

Flash Raspberry Pi OS (64-bit) to all SD cards:
```bash
# Download Raspberry Pi Imager
# Flash "Raspberry Pi OS (64-bit)" to each card
# Enable SSH in advanced options
# Set hostname: gunshot-001, gunshot-002, etc.
# Set same username/password for all
```

#### 2. Initial Pi Configuration

Boot each Pi and configure:
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Set timezone
sudo raspi-config
# Choose: Localisation Options > Timezone

# Enable I2C (if using sensors)
sudo raspi-config
# Choose: Interface Options > I2C > Enable

# Reboot
sudo reboot
```

#### 3. Deploy Code

From your development machine:
```bash
# Set Pi IP addresses in a list
NODES=(
  "pi@192.168.1.101"
  "pi@192.168.1.102"
  "pi@192.168.1.103"
)

# Deploy to each node
for node in "${NODES[@]}"; do
  echo "Deploying to $node..."
  make deploy PI_HOST=$node
done
```

Or manually on each Pi:
```bash
git clone https://github.com/yourusername/gunshot-detection-system.git
cd gunshot-detection-system
sudo bash scripts/install.sh
```

#### 4. Configure Each Node

Edit config on each Pi:
```bash
sudo nano ~/gunshot-detection-system/config.yaml
```

Critical settings per node:
```yaml
system:
  node_id: "gunshot-001"  # UNIQUE per node

output:
  mqtt:
    broker: "192.168.1.100"  # Your central MQTT broker

location:
  # Set manually if no GPS
  latitude: 37.7749
  longitude: -122.4194
```

#### 5. Start Services

On each Pi:
```bash
sudo systemctl start gunshot-detector
sudo systemctl status gunshot-detector
```

#### 6. Verify Operation

Monitor all nodes from central location:
```bash
# Subscribe to all detections
mosquitto_sub -h <broker> -t 'gunshot/detections' -v

# Subscribe to all health messages
mosquitto_sub -h <broker> -t 'gunshot/+/health' -v

# Monitor specific node
mosquitto_sub -h <broker> -t 'gunshot/gunshot-001/#' -v
```

### Network Configuration

#### Option 1: WiFi Mesh

Configure each Pi to connect to same WiFi:
```bash
sudo raspi-config
# Choose: System Options > Wireless LAN
```

#### Option 2: Ethernet + PoE

- Use PoE HAT on Pi 4
- Connect to PoE switch
- More reliable, provides power
- Recommended for permanent installations

#### Option 3: Mesh Network (Meshtastic)

- Add Meshtastic LoRa radio to each Pi
- Configure mesh network channel
- Enables communication without infrastructure
- Longer range, lower bandwidth

### GPS/PPS Configuration

On each Pi with GPS:

1. Connect GPS module to UART (GPIO 14/15)
2. Enable UART:
```bash
sudo raspi-config
# Interface Options > Serial Port
# Login shell: No
# Serial port hardware: Yes
```

3. Edit boot config:
```bash
sudo nano /boot/firmware/config.txt
# Add:
dtoverlay=pps-gpio,gpiopin=18
enable_uart=1
```

4. Configure gpsd:
```bash
sudo nano /etc/default/gpsd
# Set:
DEVICES="/dev/ttyAMA0"
GPSD_OPTIONS="-n"
```

5. Reboot and verify:
```bash
sudo reboot
# After reboot:
cgps -s
sudo ppstest /dev/pps0
```

### Central MQTT Broker Setup

On central server (or cloud):

```bash
# Install Mosquitto
sudo apt install mosquitto mosquitto-clients

# Configure
sudo nano /etc/mosquitto/mosquitto.conf
```

Add:
```
listener 1883
allow_anonymous true

# Or with authentication:
# listener 1883
# password_file /etc/mosquitto/passwd
```

Create users (if using auth):
```bash
sudo mosquitto_passwd -c /etc/mosquitto/passwd admin
sudo systemctl restart mosquitto
```

### Monitoring Dashboard

#### Option 1: MQTT Explorer (Desktop)

Download MQTT Explorer and connect to broker:
- Host: Your broker IP
- Port: 1883

#### Option 2: Node-RED (Web)

```bash
# Install Node-RED
bash <(curl -sL https://raw.githubusercontent.com/node-red/linux-installers/master/deb/update-nodejs-and-nodered)

# Install MQTT nodes
cd ~/.node-red
npm install node-red-dashboard

# Start
node-red-start
```

Access at http://server-ip:1880

#### Option 3: Custom Dashboard

See example dashboard code in docs/dashboard-example.html

### Trilateration Server

Create separate server for position calculation:

```python
# trilateration_server.py (simplified example)
import paho.mqtt.client as mqtt
import json
from collections import defaultdict

detections = defaultdict(list)

def on_message(client, userdata, msg):
    event = json.loads(msg.payload)

    # Collect detections from multiple nodes
    detections[event['timestamp']].append(event)

    # If we have 3+ nodes with same timestamp (within window)
    # Calculate position...

mqtt_client = mqtt.Client()
mqtt_client.on_message = on_message
mqtt_client.connect("localhost", 1883)
mqtt_client.subscribe("gunshot/detections")
mqtt_client.loop_forever()
```

### Maintenance

#### Update All Nodes

From dev machine:
```bash
for node in "${NODES[@]}"; do
  ssh $node "cd ~/gunshot-detection-system && git pull && sudo systemctl restart gunshot-detector"
done
```

#### Check Node Health

```bash
for node in "${NODES[@]}"; do
  echo "=== $node ==="
  ssh $node "sudo systemctl status gunshot-detector"
done
```

#### Remote Configuration

Enable remote config in config.yaml:
```yaml
remote_config:
  enabled: true
  mqtt:
    enabled: true
```

Then update remotely:
```bash
# Update threshold on all nodes
mosquitto_pub -h <broker> -t "gunshot/config/all/set/detection/aubio/threshold" -m "0.7"
```

### Troubleshooting

#### Node Not Reporting

1. Check service status:
```bash
ssh pi@node sudo systemctl status gunshot-detector
```

2. Check logs:
```bash
ssh pi@node sudo journalctl -u gunshot-detector -n 50
```

3. Check network:
```bash
ping node-ip
ssh pi@node mosquitto_pub -h broker -t test -m "hello"
```

#### Timing Issues

1. Verify GPS lock:
```bash
ssh pi@node cgps -s
```

2. Check PPS:
```bash
ssh pi@node sudo ppstest /dev/pps0
```

3. Check NTP:
```bash
ssh pi@node ntpq -p
```

#### High False Positive Rate

1. Adjust detection threshold
2. Enable high-pass filter
3. Increase silence threshold
4. Add ML classifier for confirmation

### Scaling Beyond 10 Nodes

- Consider dedicated MQTT broker with clustering
- Use MQTT bridge to cloud (AWS IoT, Azure IoT Hub)
- Implement data aggregation at edge
- Use time-series database (InfluxDB) for events
- Deploy regional trilateration servers

### Security Hardening

1. Use MQTT TLS/SSL
2. Enable MQTT authentication
3. Configure firewall on each Pi
4. Use VPN for inter-node communication
5. Regular security updates
6. Disable unused services

```bash
# Example firewall rules
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 8883/tcp  # MQTT over TLS
sudo ufw enable
```
