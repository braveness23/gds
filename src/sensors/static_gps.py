import time

from .base_gps import BaseGPSDevice
from .types import GPSData


class StaticGPSDevice(BaseGPSDevice[GPSData]):
    """
    Provides a static GPS position (for testing or fixed installations).
    """

    def __init__(self, latitude: float, longitude: float, altitude: float = 0.0):
        # Import here to avoid circular import
        from .gps import validate_coordinates

        # Validate coordinates
        validate_coordinates(latitude, longitude, altitude)

        super().__init__(update_interval=0, sensor_name="StaticGPSDevice")
        self.position = GPSData(
            latitude=latitude,
            longitude=longitude,
            altitude=altitude,
            timestamp=time.time(),
            fix_quality=1,  # Fake "GPS" fix
            satellites=4,  # Minimum for fix
            hdop=1.0,  # Good accuracy
            speed=0.0,
            track=0.0,
        )

    def get_position(self):
        """Return the static GPS position (with updated timestamp)."""
        self.position.timestamp = time.time()
        return self.position

    def _connect(self):
        pass

    def _read_sensor(self):
        self.position.timestamp = time.time()
        return self.position

    def _disconnect(self):
        pass
