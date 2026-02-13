#!/bin/bash
# Installation script for Gunshot Detection System

set -e  # Exit on error

echo "========================================"
echo "Gunshot Detection System - Installation"
echo "========================================"
echo ""

# Check if running on Raspberry Pi
if [ ! -f /proc/device-tree/model ]; then
    echo "Warning: This doesn't appear to be a Raspberry Pi"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check for root
if [ "$EUID" -ne 0 ]; then
    echo "This script must be run as root (use sudo)"
    exit 1
fi

echo "Step 1: Installing system dependencies..."
apt update
apt install -y \
    python3-pip python3-dev python3-venv \
    libasound2-dev portaudio19-dev libportaudio2 \
    gpsd gpsd-clients python3-gps \
    git build-essential \
    aubio-tools libaubio-dev

echo ""
echo "Step 2: Setting up Python environment..."
INSTALL_DIR="/home/pi/gunshot-detection-system"

# Create user if doesn't exist
if ! id "pi" &>/dev/null; then
    useradd -m -s /bin/bash pi
fi

# Copy files if not already there
if [ ! -d "$INSTALL_DIR" ]; then
    mkdir -p "$INSTALL_DIR"
    cp -r . "$INSTALL_DIR/"
    chown -R pi:pi "$INSTALL_DIR"
fi

# Create virtual environment as pi user
sudo -u pi bash << EOF
cd $INSTALL_DIR
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
EOF

echo ""
echo "Step 3: Creating directories..."
mkdir -p /var/log/gunshot_detector
mkdir -p /data/detections
chown pi:pi /var/log/gunshot_detector
chown pi:pi /data/detections

echo ""
echo "Step 4: Configuring gpsd..."
if [ -f /dev/ttyAMA0 ] || [ -f /dev/ttyUSB0 ]; then
    cat > /etc/default/gpsd << 'GPSD_EOF'
# Default settings for the gpsd init script
DEVICES="/dev/ttyAMA0"
GPSD_OPTIONS="-n"
START_DAEMON="true"
USBAUTO="true"
GPSD_EOF
    
    systemctl enable gpsd
    systemctl restart gpsd
    echo "gpsd configured and started"
else
    echo "No GPS device found - skipping gpsd configuration"
fi

echo ""
echo "Step 5: Creating configuration file..."
if [ ! -f "$INSTALL_DIR/config.yaml" ]; then
    cp "$INSTALL_DIR/examples/config.example.yaml" "$INSTALL_DIR/config.yaml"
    chown pi:pi "$INSTALL_DIR/config.yaml"
    echo "Created config.yaml from example"
    echo "IMPORTANT: Edit $INSTALL_DIR/config.yaml with your settings!"
else
    echo "config.yaml already exists - not overwriting"
fi

echo ""
echo "Step 6: Installing systemd service..."
cp "$INSTALL_DIR/systemd/gunshot-detector.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable gunshot-detector

echo ""
echo "========================================"
echo "Installation Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Edit configuration: sudo nano $INSTALL_DIR/config.yaml"
echo "2. Set your node_id (must be unique)"
echo "3. Configure MQTT broker address"
echo "4. Test audio device: arecord -l"
echo "5. Start service: sudo systemctl start gunshot-detector"
echo "6. Check status: sudo systemctl status gunshot-detector"
echo "7. View logs: sudo journalctl -u gunshot-detector -f"
echo ""
echo "For help: see README.md"
