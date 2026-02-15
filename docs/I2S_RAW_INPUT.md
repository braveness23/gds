# Direct I2S Microphone Input

The system now supports capturing audio directly from an I2S microphone, bypassing ALSA. This is useful for low-latency or embedded use cases where the I2S device is exposed as a raw character device (e.g., /dev/i2s).

## Usage

1. **Import the class:**

```python
from src.audio import I2SRawSourceNode
```

2. **Create an instance:**

```python
i2s_node = I2SRawSourceNode(
    device="/dev/i2s",  # Path to your I2S device
    sample_rate=48000,
    channels=1,
    buffer_size=1024,
    format_bits=32
)
```

3. **Start capturing:**

```python
i2s_node.start()
```

4. **Read a buffer:**

```python
buffer = i2s_node.read_buffer()
# buffer.samples contains the audio data
```

5. **Stop capturing:**

```python
i2s_node.stop()
```

## Notes
- The device path (default: `/dev/i2s`) must be readable and mapped to your hardware.
- This class does not use ALSA or PyAudio; it reads raw PCM data directly.
- Buffer size, sample rate, and format must match your hardware configuration.
- For stereo, set `channels=2`.

## Integration
You can use `I2SRawSourceNode` anywhere an `AudioSourceNode` is accepted in the pipeline.
