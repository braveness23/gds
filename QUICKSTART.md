# Quick Start Guide

## 5-Minute Setup (Single Node)

### 1. Install
```bash
git clone https://github.com/yourusername/gunshot-detection-system.git
cd gunshot-detection-system
sudo bash install.sh
```

### 2. Configure
```bash
nano config.yaml
```

Minimum changes:
- Set `system.node_id` to something unique
- Set `output.mqtt.broker` to your MQTT broker IP
- Disable GPS/sensors if you don't have them:
  ```yaml
  sensors:
    gps:
      enabled: false
    environment:
      enabled: false
  ```

### 3. Test Audio
```bash
# Find your audio device
arecord -l

# Test recording (Ctrl+C to stop)
arecord -D hw:0,0 -f S32_LE -r 48000 -c 1 test.wav
aplay test.wav
```

### 4. Run
```bash
# Development mode (see output)
python src/main.py --config config.yaml

# Or install as service
sudo systemctl start gunshot-detector
sudo journalctl -u gunshot-detector -f
```

## Testing Detection

Make a sharp sound (clap, snap, knock on table) near the microphone. You should see:
```
[AubioDetector] Detection at 1234567.890123s - onset
```

## MQTT Monitoring

Subscribe to all topics:
```bash
mosquitto_sub -h <broker> -t 'gunshot/#' -v
```

You'll see:
- `gunshot/detections` - Detection events
- `gunshot/<node_id>/health` - System health

## Troubleshooting

**No audio detected:**
- Check microphone is working: `arecord -l`
- Verify config `audio.device` matches your device
- Check volume/gain settings

**No GPS fix:**
- Ensure antenna has clear sky view
- Check gpsd: `cgps -s`
- May take 5-10 minutes for first fix

**High CPU usage:**
- Increase `detection.aubio.hop_size` (e.g., 512 → 1024)
- Reduce `audio.sample_rate` (e.g., 48000 → 44100)

**MQTT not working:**
- Verify broker IP: `ping <broker>`
- Test connection: `mosquitto_sub -h <broker> -t test`
- Check firewall: `sudo ufw status`

## Next Steps

1. **Deploy to multiple nodes** - Use `make deploy PI_HOST=pi@192.168.1.X`
2. **Set up central server** - Collect detections for trilateration
3. **Tune detection** - Adjust thresholds based on your environment
4. **Enable remote config** - For fleet management

See full README.md for details.
