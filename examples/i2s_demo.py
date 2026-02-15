
import time
from src.audio.audio_nodes import ALSASourceNode

def main():
    buffer_count = 5
    received = []

    def on_buffer(buf):
        print(f"Buffer {len(received)+1}: min={buf.samples.min():.4f}, max={buf.samples.max():.4f}, std={buf.samples.std():.4f}, mean={buf.samples.mean():.4f}, timestamp={buf.timestamp}")
        received.append(buf)
        if len(received) >= buffer_count:
            alsa_node.stop()

    alsa_node = ALSASourceNode(
        device="plughw:2,0",
        sample_rate=48000,
        channels=1,
        buffer_size=1024,
        format_bits=16
    )
    alsa_node.connect(on_buffer)
    print(f"Capturing {buffer_count} buffers from ALSA I2S mic...")
    alsa_node.start()

    # Wait for buffers to be received
    while len(received) < buffer_count:
        time.sleep(0.05)
    print("Done.")

if __name__ == "__main__":
    main()
