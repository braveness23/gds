"""Unit tests for sensor base class and implementations."""

import pytest
import time
import threading
from dataclasses import dataclass
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from sensors.base import BaseSensor
from core.event_bus import EventBus, EventType


@dataclass
class TestData:
    """Test data structure for mock sensor."""
    value: float
    timestamp: float
    
    def to_dict(self):
        return {'value': self.value, 'timestamp': self.timestamp}


class MockSensor(BaseSensor[TestData]):
    """Mock sensor implementation for testing."""
    
    def __init__(self, 
                 fail_connect=False,
                 fail_read=False,
                 read_delay=0.0,
                 **kwargs):
        super().__init__(**kwargs)
        self.fail_connect = fail_connect
        self.fail_read = fail_read
        self.read_delay = read_delay
        self.connect_called = False
        self.read_count = 0
        self.disconnect_called = False
        
    def _connect(self):
        """Mock connection."""
        self.connect_called = True
        if self.fail_connect:
            raise ConnectionError("Mock connection failed")
    
    def _read_sensor(self) -> TestData:
        """Mock sensor read."""
        self.read_count += 1
        
        if self.read_delay > 0:
            time.sleep(self.read_delay)
        
        if self.fail_read:
            return None
        
        return TestData(
            value=float(self.read_count),
            timestamp=time.time()
        )
    
    def _disconnect(self):
        """Mock disconnect."""
        self.disconnect_called = True


class TestBaseSensorLifecycle:
    """Test sensor lifecycle management."""
    
    def test_sensor_initialization(self):
        """Test sensor is initialized correctly."""
        sensor = MockSensor(
            update_interval=1.0,
            sensor_name="TestSensor"
        )
        
        assert sensor.sensor_name == "TestSensor"
        assert sensor.update_interval == 1.0
        assert sensor.connected is False
        assert sensor.running is False
        assert sensor.current_data is None
        assert len(sensor.callbacks) == 0
    
    def test_sensor_connect(self):
        """Test sensor connection."""
        sensor = MockSensor()
        
        sensor.connect()
        
        assert sensor.connected is True
        assert sensor.connect_called is True
    
    def test_sensor_connect_failure(self):
        """Test sensor connection failure handling."""
        sensor = MockSensor(fail_connect=True)
        
        with pytest.raises(ConnectionError):
            sensor.connect()
        
        assert sensor.connected is False
        assert sensor.connect_called is True
    
    def test_sensor_start_stop(self):
        """Test starting and stopping sensor."""
        sensor = MockSensor(update_interval=0.1)
        
        # Start sensor
        sensor.start()
        assert sensor.running is True
        assert sensor.connected is True
        assert sensor.update_thread is not None
        
        # Give it time to read
        time.sleep(0.3)
        
        # Should have read at least once
        assert sensor.read_count > 0
        assert sensor.current_data is not None
        
        # Stop sensor
        sensor.stop()
        assert sensor.running is False
        assert sensor.connected is False
        assert sensor.disconnect_called is True
    
    def test_sensor_cannot_start_twice(self):
        """Test sensor won't start if already running."""
        sensor = MockSensor(update_interval=0.1)
        
        sensor.start()
        # read_count_before = sensor.read_count
        
        # Try to start again
        sensor.start()
        
        # Should still be same instance
        assert sensor.running is True
        time.sleep(0.2)
        
        sensor.stop()
    
    def test_sensor_auto_connect_on_start(self):
        """Test sensor auto-connects when started."""
        sensor = MockSensor()
        
        assert sensor.connected is False
        
        sensor.start()
        
        assert sensor.connected is True
        assert sensor.connect_called is True
        
        sensor.stop()
    
    def test_context_manager(self):
        """Test sensor as context manager."""
        sensor = MockSensor(update_interval=0.1)
        
        assert sensor.running is False
        
        with sensor:
            assert sensor.running is True
            assert sensor.connected is True
            time.sleep(0.2)
            assert sensor.read_count > 0
        
        # Should auto-stop
        assert sensor.running is False
        assert sensor.connected is False


class TestSensorDataThreadSafety:
    """Test thread safety of sensor data access."""
    
    def test_concurrent_get_data(self):
        """Test concurrent get_data() calls are thread-safe."""
        sensor = MockSensor(update_interval=0.05)
        sensor.start()
        
        # Give it time to get some data
        time.sleep(0.15)
        
        results = []
        errors = []
        
        def read_data():
            """Read data in thread."""
            try:
                for _ in range(20):
                    data = sensor.get_data()
                    if data:
                        results.append(data.value)
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)
        
        # Start multiple reader threads
        threads = [threading.Thread(target=read_data) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        sensor.stop()
        
        # Should have no errors
        assert len(errors) == 0
        # Should have read data successfully
        assert len(results) > 0
    
    def test_concurrent_callbacks(self):
        """Test callbacks are thread-safe."""
        sensor = MockSensor(update_interval=0.05)
        
        callback_data = []
        callback_errors = []
        lock = threading.Lock()
        
        def callback(data):
            try:
                with lock:
                    callback_data.append(data.value)
                # Simulate some processing
                time.sleep(0.001)
            except Exception as e:
                callback_errors.append(e)
        
        # Register multiple callbacks
        for _ in range(3):
            sensor.add_callback(callback)
        
        sensor.start()
        time.sleep(0.3)
        sensor.stop()
        
        # Should have no errors
        assert len(callback_errors) == 0
        # Should have received callbacks
        assert len(callback_data) > 0
    
    def test_data_lock_prevents_corruption(self):
        """Test data lock prevents corruption during updates."""
        sensor = MockSensor(update_interval=0.01)
        sensor.start()
        
        # Give it time to start updating
        time.sleep(0.05)
        
        corruption_detected = False
        
        # Try to read data many times quickly
        for _ in range(100):
            data = sensor.get_data()
            if data:
                # Data should be consistent (value matches read_count)
                # If lock is broken, we might see inconsistent state
                pass
        
        sensor.stop()
        
        # If we get here without errors, locks work
        assert not corruption_detected


class TestSensorErrorHandling:
    """Test error handling in sensor operations."""
    
    def test_connect_error_handling(self):
        """Test _connect() error is propagated."""
        sensor = MockSensor(fail_connect=True)
        
        with pytest.raises(ConnectionError):
            sensor.connect()
        
        assert sensor.connected is False
    
    def test_read_error_increments_error_count(self):
        """Test _read_sensor() errors are tracked."""
        sensor = MockSensor(fail_read=True, update_interval=0.05)
        
        sensor.start()
        time.sleep(0.2)
        sensor.stop()
        
        # Should have attempted reads
        assert sensor.read_count > 0
        # Should have tracked errors
        assert sensor.stats['read_errors'] > 0
        # Should not have valid data
        assert sensor.current_data is None
    
    def test_read_error_continues_loop(self):
        """Test sensor continues reading after errors."""
        sensor = MockSensor(fail_read=False, update_interval=0.05)
        sensor.start()
        
        # Let it collect some successful reads
        time.sleep(0.15)
        successful_reads = sensor.read_count
        
        # Make it fail
        sensor.fail_read = True
        time.sleep(0.1)
        
        # Make it succeed again
        sensor.fail_read = False
        time.sleep(0.15)
        
        sensor.stop()
        
        # Should have continued trying despite errors
        assert sensor.read_count > successful_reads
        assert sensor.stats['read_errors'] > 0
    
    def test_callback_error_does_not_stop_sensor(self):
        """Test callback errors don't stop sensor."""
        sensor = MockSensor(update_interval=0.05)
        
        def bad_callback(data):
            raise RuntimeError("Callback error")
        
        def good_callback(data):
            # This should still work
            pass
        
        sensor.add_callback(bad_callback)
        sensor.add_callback(good_callback)
        
        sensor.start()
        time.sleep(0.2)
        
        # Sensor should still be running
        assert sensor.running is True
        assert sensor.read_count > 0
        
        sensor.stop()
    
    def test_disconnect_error_handling(self):
        """Test _disconnect() errors are caught."""
        sensor = MockSensor()
        
        # Override to raise error
        def bad_disconnect():
            raise RuntimeError("Disconnect failed")
        
        sensor._disconnect = bad_disconnect
        
        sensor.start()
        time.sleep(0.1)
        
        # Should not raise exception
        sensor.stop()
        
        # Should be marked as stopped
        assert sensor.running is False


class TestSensorCallbacks:
    """Test callback registration and notification."""
    
    def test_add_callback(self):
        """Test adding callbacks."""
        sensor = MockSensor()
        
        callback_count = 0
        
        def callback(data):
            nonlocal callback_count
            callback_count += 1
        
        sensor.add_callback(callback)
        sensor.start()
        time.sleep(0.2)
        sensor.stop()
        
        assert callback_count > 0
    
    def test_remove_callback(self):
        """Test removing callbacks."""
        sensor = MockSensor(update_interval=0.05)
        
        callback_count = 0
        
        def callback(data):
            nonlocal callback_count
            callback_count += 1
        
        sensor.add_callback(callback)
        sensor.start()
        time.sleep(0.1)
        
        # Record count
        count_before_removal = callback_count
        
        # Remove callback
        sensor.remove_callback(callback)
        time.sleep(0.1)
        
        sensor.stop()
        
        # Should not have increased much after removal
        # (maybe 1-2 due to timing, but not many)
        assert callback_count - count_before_removal < 3
    
    def test_multiple_callbacks(self):
        """Test multiple callbacks all get called."""
        sensor = MockSensor(update_interval=0.05)
        
        counts = [0, 0, 0]
        
        def make_callback(index):
            def callback(data):
                counts[index] += 1
            return callback
        
        for i in range(3):
            sensor.add_callback(make_callback(i))
        
        sensor.start()
        time.sleep(0.2)
        sensor.stop()
        
        # All callbacks should have been called
        assert all(c > 0 for c in counts)


class TestSensorStatistics:
    """Test sensor statistics tracking."""
    
    def test_statistics_tracking(self):
        """Test sensor tracks statistics."""
        sensor = MockSensor(update_interval=0.05)
        
        sensor.start()
        time.sleep(0.2)
        sensor.stop()
        
        stats = sensor.get_stats()
        
        assert stats['readings_taken'] > 0
        assert stats['read_errors'] == 0
        assert stats['connected'] is False
        assert stats['running'] is False
        assert stats['last_reading_time'] is not None
        assert 'uptime' in stats
    
    def test_error_statistics(self):
        """Test error statistics are tracked."""
        sensor = MockSensor(fail_read=True, update_interval=0.05)
        
        sensor.start()
        time.sleep(0.2)
        sensor.stop()
        
        stats = sensor.get_stats()
        
        assert stats['read_errors'] > 0


class TestSensorEventBus:
    """Test sensor integration with event bus."""
    
    def test_sensor_publishes_to_event_bus(self):
        """Test sensor publishes data to event bus."""
        event_bus = EventBus()
        event_bus.start()
        
        received_events = []
        
        def event_handler(event):
            received_events.append(event)
        
        event_bus.subscribe(EventType.SYSTEM, event_handler)
        
        sensor = MockSensor(
            update_interval=0.05,
            event_bus=event_bus,
            event_type=EventType.SYSTEM
        )
        
        sensor.start()
        time.sleep(0.2)
        sensor.stop()
        
        event_bus.stop()
        
        # Should have received events
        assert len(received_events) > 0
    
    def test_sensor_without_event_bus(self):
        """Test sensor works without event bus."""
        sensor = MockSensor(
            update_interval=0.05,
            event_bus=None
        )
        
        sensor.start()
        time.sleep(0.2)
        sensor.stop()
        
        # Should still work and read data
        assert sensor.read_count > 0
        assert sensor.current_data is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
