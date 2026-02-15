"""GPS sensor integration for position tracking.

This module provides GPS position reading via gpsd daemon.
Supports both callback-based updates and on-demand position retrieval.
"""

import time
import threading
from dataclasses import dataclass
from typing import Optional, Callable, List
from core.event_bus import Event, EventType
from sensors.base_gps import BaseGPSDevice

# Optional serial/NMEA parsing support
try:
    import serial
    import pynmea2
except Exception:
    serial = None  # type: ignore
    pynmea2 = None  # type: ignore


@dataclass
class GPSData:
    """GPS position and timing data."""
    latitude: float
    longitude: float
    altitude: float
    timestamp: float  # System time when position was captured
    fix_quality: int  # 0=no fix, 1=GPS, 2=DGPS, 3=PPS, 4=RTK, 5=Float RTK
    satellites: int   # Number of satellites in view
    hdop: float       # Horizontal dilution of precision
    speed: float      # Speed in m/s
    track: float      # Track angle in degrees
    
    @property
    def has_fix(self) -> bool:
        """Check if GPS has a valid fix."""
        return self.fix_quality > 0
    
    @property
    def fix_type_name(self) -> str:
        """Human-readable fix type."""
        types = {
            0: "No Fix",
            1: "GPS",
            2: "DGPS",
            3: "PPS",
            4: "RTK Fixed",
            5: "RTK Float"
        }
        return types.get(self.fix_quality, "Unknown")
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'latitude': self.latitude,
            'longitude': self.longitude,
            'altitude': self.altitude,
            'timestamp': self.timestamp,
            'fix_quality': self.fix_quality,
            'fix_type': self.fix_type_name,
            'satellites': self.satellites,
            'hdop': self.hdop,
            'speed': self.speed,
            'track': self.track,
            'has_fix': self.has_fix
        }


class GPSReader(BaseGPSDevice[GPSData]):
    """
    GPS reader using gpsd daemon.
    
    This provides position data for:
    - Node location in trilateration
    - Timestamping (system clock should already be GPS-synced via chrony)
    - Movement tracking (if nodes are mobile)
    
    Architecture:
    - gpsd runs as system service
    - This class connects to gpsd via socket
    - Background thread polls for updates
    - Publishes position updates to event bus
    """
    
    def __init__(self,
                 host: str = 'localhost',
                 port: int = 2947,
                 update_interval: float = 1.0,
                 event_bus=None):
        """
        Initialize GPS reader.
        
        Args:
            host: gpsd host (usually localhost)
            port: gpsd port (default 2947)
            update_interval: How often to poll GPS (seconds)
            event_bus: Event bus for publishing position updates
        """
        super().__init__(
            update_interval=update_interval,
            event_bus=event_bus,
            event_type=EventType.SYSTEM,
            sensor_name="GPSReader"
        )
        
        self.host = host
        self.port = port
        self.gps_session = None
        
        # GPS-specific statistics
        self.stats['positions_read'] = 0
        self.stats['no_fix_count'] = 0
        self.stats['last_fix_time'] = None
        
        # Track periodic logging
        self._log_counter = 0
    
    def _connect(self):
        """Connect to gpsd daemon."""
        try:
            import gps
        except ImportError:
            print("[GPSReader] Warning: gps module not installed")
            print("  Install with: pip install gps")
            print("  Or on Raspberry Pi: sudo apt install python3-gps")
            raise ImportError("gps module not available")
        
        try:
            print(f"[GPSReader] Connecting to gpsd at {self.host}:{self.port}...")
            self.gps_session = gps.gps(host=self.host, port=self.port, mode=gps.WATCH_ENABLE)
            print(f"[GPSReader] Connected to gpsd")
        except Exception as e:
            print(f"[GPSReader] Failed to connect to gpsd: {e}")
            print(f"  Make sure gpsd is running: sudo systemctl status gpsd")
            raise
    
    def _read_sensor(self) -> Optional[GPSData]:
        """Read GPS position from gpsd."""
        import gps as gps_module
        
        try:
            # Read next GPS report (blocking with timeout)
            report = self.gps_session.next()
            
            # Process TPV (Time-Position-Velocity) reports
            if report['class'] == 'TPV':
                position = self._parse_tpv_report(report)
                
                if position:
                    # Update GPS-specific statistics
                    self.stats['positions_read'] += 1
                    
                    if not position.has_fix:
                        self.stats['no_fix_count'] += 1
                    else:
                        self.stats['last_fix_time'] = time.time()
                    
                    # Log position updates periodically (only with fix)
                    if position.has_fix:
                        self._log_counter += 1
                        if self._log_counter % 10 == 0:
                            print(f"[GPSReader] Position: ({position.latitude:.6f}, "
                                  f"{position.longitude:.6f}, {position.altitude:.1f}m) "
                                  f"{position.fix_type_name}, {position.satellites} sats, "
                                  f"HDOP: {position.hdop:.1f}")
                    
                    return position
                
            return None
        
        except StopIteration:
            # gpsd connection lost
            print(f"[GPSReader] Connection to gpsd lost, attempting reconnect...")
            self._reconnect()
            return None
        
        except Exception as e:
            print(f"[GPSReader] Error reading GPS: {e}")
            return None
    
    def _parse_tpv_report(self, report: dict) -> Optional[GPSData]:
        """Parse TPV (Time-Position-Velocity) report from gpsd."""
        try:
            # Check for required fields
            mode = report.get('mode', 0)
            
            # mode: 0=no mode, 1=no fix, 2=2D fix, 3=3D fix
            if mode < 2:
                # No fix
                return GPSData(
                    latitude=0.0,
                    longitude=0.0,
                    altitude=0.0,
                    timestamp=time.time(),
                    fix_quality=0,
                    satellites=0,
                    hdop=99.9,
                    speed=0.0,
                    track=0.0
                )
            
            # Extract position
            lat = report.get('lat', 0.0)
            lon = report.get('lon', 0.0)
            alt = report.get('alt', 0.0)
            
            # Fix quality (map gpsd mode to our quality scale)
            # 2 = 2D fix (GPS), 3 = 3D fix (GPS)
            fix_quality = 1 if mode >= 2 else 0
            
            # Get accuracy info
            epx = report.get('epx', 0.0)  # Longitude error (m)
            epy = report.get('epy', 0.0)  # Latitude error (m)
            
            # Approximate HDOP from position errors
            # HDOP ≈ sqrt(epx² + epy²) / 5
            if epx > 0 and epy > 0:
                hdop = ((epx**2 + epy**2)**0.5) / 5.0
            else:
                hdop = 99.9
            
            # Speed and track
            speed = report.get('speed', 0.0)  # m/s
            track = report.get('track', 0.0)  # degrees
            
            return GPSData(
                latitude=lat,
                longitude=lon,
                altitude=alt,
                timestamp=time.time(),
                fix_quality=fix_quality,
                satellites=0,  # Not in TPV report, use SKY report for this
                hdop=hdop,
                speed=speed,
                track=track
            )
        
        except Exception as e:
            print(f"[GPSReader] Error parsing TPV report: {e}")
            return None
    
    def _reconnect(self):
        """Reconnect to gpsd."""
        try:
            self.connected = False
            time.sleep(2.0)  # Wait before reconnect
            self.connect()
        except Exception as e:
            print(f"[GPSReader] Reconnect failed: {e}")
    
    # Alias for GPS-specific naming
    def get_position(self) -> Optional[GPSData]:
        """Get current GPS position (alias for get_data)."""
        return self.get_data()
    
    def wait_for_fix(self, timeout: float = 60.0) -> bool:
        """
        Wait for GPS to acquire fix.
        
        Args:
            timeout: Maximum time to wait (seconds)
        
        Returns:
            True if fix acquired, False if timeout
        """
        print(f"[GPSReader] Waiting for GPS fix (timeout: {timeout}s)...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            position = self.get_position()
            
            if position and position.has_fix:
                print(f"[GPSReader] GPS fix acquired! "
                      f"({position.latitude:.6f}, {position.longitude:.6f})")
                return True
            
            time.sleep(1.0)
        
        print(f"[GPSReader] Timeout waiting for GPS fix")
        return False


class StaticLocationProvider:
    """
    Fallback location provider for nodes without GPS.
    
    Useful for:
    - Testing
    - Fixed installations with surveyed positions
    - Backup when GPS fails
    """
    
    def __init__(self,
                 latitude: float,
                 longitude: float,
                 altitude: float = 0.0):
        """
        Initialize static location.
        
        Args:
            latitude: Latitude in decimal degrees
            longitude: Longitude in decimal degrees
            altitude: Altitude in meters above sea level
        """
        self.position = GPSData(
            latitude=latitude,
            longitude=longitude,
            altitude=altitude,
            timestamp=time.time(),
            fix_quality=1,  # Fake "GPS" fix
            satellites=4,   # Minimum for fix
            hdop=1.0,       # Good accuracy
            speed=0.0,
            track=0.0
        )
        
        print(f"[StaticLocation] Using static position: "
              f"({latitude:.6f}, {longitude:.6f}, {altitude:.1f}m)")
    
    def connect(self):
        """No-op for static location."""
        pass
    
    def start(self):
        """No-op for static location."""
        pass
    
    def stop(self):
        """No-op for static location."""
        pass
    
    def get_position(self) -> GPSData:
        """Return static position."""
        # Update timestamp to current time
        self.position.timestamp = time.time()
        return self.position
    
    def wait_for_fix(self, timeout: float = 0.0) -> bool:
        """Always returns True (static position always available)."""
        return True
    
    def add_callback(self, callback: Callable[[GPSData], None]):
        """No-op for static location."""
        pass
    
    def get_stats(self) -> dict:
        """Get static location stats."""
        return {
            'type': 'static',
            'latitude': self.position.latitude,
            'longitude': self.position.longitude,
            'altitude': self.position.altitude
        }


class SerialGPSReader(BaseGPSDevice[GPSData]):
        def _connect(self):
            if serial is None or pynmea2 is None:
                raise ImportError("pyserial and pynmea2 are required for SerialGPSReader")
            try:
                self.serial = serial.Serial(self.device, self.baudrate, timeout=1)
            except Exception as e:
                print(f"[SerialGPSReader] Failed to open serial device {self.device}: {e}")
                raise

        def _disconnect(self):
            try:
                if hasattr(self, 'serial') and self.serial and getattr(self.serial, 'is_open', True):
                    self.serial.close()
            except Exception as e:
                print(f"[SerialGPSReader] Error closing serial device: {e}")

        def _read_sensor(self):
            if serial is None or pynmea2 is None:
                return None
            try:
                if not hasattr(self, 'serial') or self.serial is None:
                    return None
                line = self.serial.readline().decode(errors='ignore').strip()
                if not line or not line.startswith('$'):
                    return None
                try:
                    msg = pynmea2.parse(line)
                except Exception:
                    return None

                # Parse GGA or RMC sentences for position
                lat = getattr(msg, 'latitude', None)
                lon = getattr(msg, 'longitude', None)
                try:
                    alt = float(getattr(msg, 'altitude', 0.0))
                except Exception:
                    alt = 0.0
                try:
                    fix_quality = int(getattr(msg, 'gps_qual', getattr(msg, 'gps_quality', 0)))
                except Exception:
                    fix_quality = 0
                try:
                    sats = int(getattr(msg, 'num_sats', getattr(msg, 'num_sv', 0)))
                except Exception:
                    sats = 0
                try:
                    hdop = float(getattr(msg, 'horizontal_dil', getattr(msg, 'hdop', 99.9)))
                except Exception:
                    hdop = 99.9
                try:
                    spd = float(getattr(msg, 'spd_over_grnd', 0.0))
                except Exception:
                    spd = 0.0
                speed = spd * 0.514444  # knots to m/s
                try:
                    track = float(getattr(msg, 'true_course', 0.0))
                except Exception:
                    track = 0.0
                status = getattr(msg, 'status', 'A')
                if status == 'A' or fix_quality > 0:
                    if lat and lon:
                        try:
                            return GPSData(
                                latitude=float(lat),
                                longitude=float(lon),
                                altitude=float(alt),
                                timestamp=time.time(),
                                fix_quality=fix_quality,
                                satellites=sats,
                                hdop=hdop,
                                speed=speed,
                                track=track
                            )
                        except Exception:
                            return None
                return None
            except Exception as e:
                print(f"[SerialGPSReader] Read error: {e}")
                return None


def create_gps_reader(config: dict, event_bus=None):
    """
    Factory function to create GPS reader from config.
    
    Returns GPSReader if GPS is enabled, otherwise StaticLocationProvider.
    """
    gps_config = config.get('sensors', {}).get('gps', {})
    location_config = config.get('location', {})
    
    if gps_config.get('enabled', False):
        serial_dev = gps_config.get('serial_device') or ''
        baud = gps_config.get('baudrate', 9600)
        prefer_serial = bool(gps_config.get('prefer_serial', False))

        # Detect availability of gpsd python module and serial/pynmea2
        gps_available = True
        try:
            import gps as _gps_check  # type: ignore
        except Exception:
            gps_available = False

        serial_available = (serial is not None and pynmea2 is not None)

        # Selection logic
        if prefer_serial:
            if serial_dev and serial_available:
                try:
                    return SerialGPSReader(device=serial_dev,
                                             baudrate=baud,
                                             update_interval=gps_config.get('update_interval', 1.0),
                                             event_bus=event_bus)
                except Exception as e:
                    print(f"[GPS] Failed to initialize SerialGPSReader: {e}")
                    # fallthrough to gpsd
            else:
                print("[GPS] prefer_serial is true but serial device or dependencies missing")

        # If gpsd is available and either preferred or serial not configured, use gpsd
        if gps_available and (not prefer_serial or not serial_dev or not serial_available):
            try:
                return GPSReader(host=gps_config.get('host', 'localhost'),
                                 port=gps_config.get('port', 2947),
                                 update_interval=gps_config.get('update_interval', 1.0),
                                 event_bus=event_bus)
            except Exception as e:
                print(f"[GPS] Failed to initialize GPSReader (gpsd): {e}")

        # If we get here, try serial reader if available
        if serial_dev and serial_available:
            try:
                return SerialGPSReader(device=serial_dev,
                                       baudrate=baud,
                                       update_interval=gps_config.get('update_interval', 1.0),
                                       event_bus=event_bus)
            except Exception as e:
                print(f"[GPS] Failed to initialize SerialGPSReader: {e}")

        if not gps_available and not (serial_dev and serial_available):
            print("[GPS] No GPS backend available (gps module or pyserial/pynmea2). Falling back to static location")
    
    # Use static location (from config or default)
    lat = location_config.get('latitude', 0.0)
    lon = location_config.get('longitude', 0.0)
    alt = location_config.get('altitude', 0.0)
    
    if lat == 0.0 and lon == 0.0:
        print("[GPS] Warning: Using default location (0, 0)")
        print("  Set location in config.yaml under 'location' section")
    
    from sensors.static_gps import StaticGPSDevice
    return StaticGPSDevice(lat, lon, alt)
