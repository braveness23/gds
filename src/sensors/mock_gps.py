from .base_gps import BaseGPSDevice
from .gps import GPSData
import time

class MockGPSDevice(BaseGPSDevice[GPSData]):
    """
    Mock GPS device for testing. Simulates movement or random positions.
    """
    def __init__(self, latitude: float = 0.0, longitude: float = 0.0, altitude: float = 0.0, move: bool = False):
        super().__init__(update_interval=1.0, sensor_name="MockGPSDevice")
        self.latitude = latitude
        self.longitude = longitude
        self.altitude = altitude
        self.move = move
        self._step = 0

    def _connect(self):
        pass

    def _read_sensor(self):
        # Simulate movement if enabled
        if self.move:
            self.latitude += 0.0001 * ((-1) ** self._step)
            self.longitude += 0.0001 * ((-1) ** (self._step + 1))
            self._step += 1
        return GPSData(
            latitude=self.latitude,
            longitude=self.longitude,
            altitude=self.altitude,
            timestamp=time.time(),
            fix_quality=1,
            satellites=5,
            hdop=0.9,
            speed=0.5 if self.move else 0.0,
            track=90.0 if self.move else 0.0
        )

    def _disconnect(self):
        pass
