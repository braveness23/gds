"""Shared sensor types for the `sensors` package.

Place common dataclasses and type aliases here to avoid circular
imports between sibling modules.
"""
from dataclasses import dataclass


@dataclass
class GPSData:
    """GPS position and timing data."""

    latitude: float
    longitude: float
    altitude: float
    timestamp: float  # System time when position was captured
    fix_quality: int  # 0=no fix, 1=GPS, 2=DGPS, 3=PPS, 4=RTK, 5=Float RTK
    satellites: int  # Number of satellites in view
    hdop: float  # Horizontal dilution of precision
    speed: float  # Speed in m/s
    track: float  # Track angle in degrees

    @property
    def has_fix(self) -> bool:
        return self.fix_quality > 0

    @property
    def fix_type_name(self) -> str:
        types = {
            0: "No Fix",
            1: "GPS",
            2: "DGPS",
            3: "PPS",
            4: "RTK Fixed",
            5: "RTK Float",
        }
        return types.get(self.fix_quality, "Unknown")

    def to_dict(self) -> dict:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude": self.altitude,
            "timestamp": self.timestamp,
            "fix_quality": self.fix_quality,
            "fix_type": self.fix_type_name,
            "satellites": self.satellites,
            "hdop": self.hdop,
            "speed": self.speed,
            "track": self.track,
            "has_fix": self.has_fix,
        }
