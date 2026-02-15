"""Base classes for sensor implementations.

Provides common functionality for all sensors:
- Background threading
- Callback management
- Event bus integration
- Statistics tracking
- Thread-safe data access
"""

import time
import logging
import threading
from abc import ABC, abstractmethod
from typing import Optional, Callable, List, Generic, TypeVar, Dict, Any
from core.event_bus import EventType


# Generic type for sensor data
T = TypeVar('T')


class BaseSensor(ABC, Generic[T]):
    """
    Abstract base class for all sensors.
    
    Provides common infrastructure for:
    - Connection management
    - Background data polling
    - Callback notifications
    - Event bus integration
    - Statistics tracking
    
    Subclasses must implement:
    - _connect(): Establish connection to sensor hardware
    - _read_sensor(): Read data from sensor
    - _disconnect(): Clean up sensor connection (optional)
    """

    def connect(self):
        """Establish connection to sensor hardware (public)."""
        print(f"[{self.sensor_name}] Connecting...")
        try:
            self._connect()
            self.connected = True
            print(f"[{self.sensor_name}] Connected successfully")
            # Take initial reading
            initial_data = self._read_sensor()
            if initial_data:
                with self.data_lock:
                    self.current_data = initial_data
        except Exception as e:
            self.connected = False
            print(f"[{self.sensor_name}] Connection failed: {e}")
            raise
    
    def __init__(self,
                 update_interval: float = 1.0,
                 event_bus=None,
                 event_type: Optional[EventType] = None,
                 sensor_name: str = "Sensor"):
        """
        Initialize base sensor.
        
        Args:
            update_interval: How often to poll sensor (seconds)
            event_type: Event type to publish (e.g., EventType.GPS, EventType.ENVIRONMENTAL)
            sensor_name: Name for logging purposes
        """
        self.update_interval = update_interval
        self.event_bus = event_bus
        self.event_type = event_type
        self.sensor_name = sensor_name
        self.logger = logging.getLogger(sensor_name)
        # Connection state
        self.connected = False
        self.running = False
        # Current sensor data
        self.current_data: Optional[T] = None
        self.data_lock = threading.Lock()
        self.callbacks: List[Callable[[T], None]] = []
        self.callback_lock = threading.Lock()
        # Background thread
        self.update_thread: Optional[threading.Thread] = None
        # Statistics
        self.stats = {
            'readings_taken': 0,
            'read_errors': 0,
            'last_reading_time': None,
            'start_time': None
        }
    @abstractmethod
    def _connect(self):
        """
        Establish connection to sensor hardware.
        Must be implemented by subclasses.
        Should raise exception if connection fails.
        Should set self.connected = True on success.
        """
        pass

    @abstractmethod
    def _read_sensor(self) -> Optional[T]:
        """
        Read data from sensor.
        Must be implemented by subclasses.
        Returns:
            Sensor data or None if read failed
        """
        pass

    def _disconnect(self):
        """
        Clean up sensor connection.
        Optional - override if sensor needs cleanup.
        """
        pass
    
    def start(self):
        """Start sensor reading thread."""
        if self.running:
            print(f"[{self.sensor_name}] Already running")
            return
        
        if not self.connected:
            self.connect()
        
        self.running = True
        self.stats['start_time'] = time.time()
        # Start background thread
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()
    
    def stop(self):
        """Stop sensor reading thread."""
        if not self.running:
            return
        
        print(f"[{self.sensor_name}] Stopping...")
        self.running = False
        # self.logger.error(f"Callback error: {e}")
        # Wait for thread to finish
        if self.update_thread and self.update_thread.is_alive():
            self.update_thread.join(timeout=5.0)
        
            self.logger.info(f"Statistics:")
        try:
            self._disconnect()
        except Exception as e:
            print(f"[{self.sensor_name}] Disconnect error: {e}")
        
        self.connected = False
        
        print(f"[{self.sensor_name}] Stopped")
        self._print_stats()
    
    def _update_loop(self):
        """Background thread that polls sensor at regular intervals."""
        print(f"[{self.sensor_name}] Update loop started")
        
        while self.running:
            try:
                # Read sensor
                data = self._read_sensor()
                
                if data is not None:
                    # Update statistics
                    self.stats['readings_taken'] += 1
                    self.stats['last_reading_time'] = time.time()
                    
                    # Store data (thread-safe)
                    with self.data_lock:
                        self.current_data = data
                    
                    # Notify callbacks
                    self._notify_callbacks(data)
                    
                    # Publish to event bus
                    if self.event_bus and self.event_type:
                        from core.event_bus import Event
                        event = Event(
                            event_type=self.event_type,
                            timestamp=time.time(),
                            source=self.sensor_name,
                            data=data.to_dict() if hasattr(data, 'to_dict') else {'data': str(data)}
                        )
                        self.event_bus.publish(event)
                else:
                    self.stats['read_errors'] += 1
                
            except Exception as e:
                self.stats['read_errors'] += 1
                print(f"[{self.sensor_name}] Read error: {e}")
            
            # Sleep until next update
            time.sleep(self.update_interval)
        
        print(f"[{self.sensor_name}] Update loop ended")
    
    def _notify_callbacks(self, data: T):
        """Notify all registered callbacks with new data."""
        with self.callback_lock:
            for callback in self.callbacks:
                try:
                    callback(data)
                except Exception as e:
                    print(f"[{self.sensor_name}] Callback error: {e}")
    
    def get_data(self) -> Optional[T]:
        """
        Get current sensor data.
        
        Returns:
            Most recent sensor reading or None
        """
        with self.data_lock:
            return self.current_data
    
    def add_callback(self, callback: Callable[[T], None]):
        """
        Register callback for sensor updates.
        
        Args:
            callback: Function to call with sensor data
        """
        with self.callback_lock:
            if callback not in self.callbacks:
                self.callbacks.append(callback)
                print(f"[{self.sensor_name}] Callback registered")
    
    def remove_callback(self, callback: Callable[[T], None]):
        """
        Unregister callback.
        
        Args:
            callback: Function to remove
        """
        with self.callback_lock:
            if callback in self.callbacks:
                self.callbacks.remove(callback)
                print(f"[{self.sensor_name}] Callback removed")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get sensor statistics."""
        stats = self.stats.copy()
        stats['connected'] = self.connected
        stats['running'] = self.running
        stats['callbacks_registered'] = len(self.callbacks)
        
        # Calculate uptime
        if stats['start_time']:
            stats['uptime'] = time.time() - stats['start_time']
        
        return stats
    
    def _print_stats(self):
        """Print sensor statistics."""
        stats = self.get_stats()
        print(f"[{self.sensor_name}] Statistics:")
        print(f"  Readings: {stats['readings_taken']}")
        print(f"  Errors: {stats['read_errors']}")
        if stats.get('uptime'):
            print(f"  Uptime: {stats['uptime']:.1f}s")
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False
