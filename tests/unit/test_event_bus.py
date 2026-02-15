"""Unit tests for event bus."""

import time
from core.event_bus import Event, EventType, DetectionEvent


def test_event_creation():
    """Test creating an event."""
    event = Event(
        event_type=EventType.DETECTION,
        timestamp=123.456,
        source="test_source",
        data={'confidence': 0.9}
    )
    
    assert event.event_type == EventType.DETECTION
    assert event.timestamp == 123.456
    assert event.source == "test_source"
    assert event.data['confidence'] == 0.9


def test_event_to_dict():
    """Test event serialization."""
    event = Event(
        event_type=EventType.SYSTEM,
        timestamp=789.012,
        source="system",
        data={'message': 'test'}
    )
    
    event_dict = event.to_dict()
    
    assert event_dict['event_type'] == 'system'
    assert event_dict['timestamp'] == 789.012
    assert event_dict['source'] == 'system'
    assert event_dict['data']['message'] == 'test'


def test_event_from_dict():
    """Test event deserialization."""
    event_dict = {
        'event_type': 'detection',
        'timestamp': 456.789,
        'source': 'detector',
        'data': {'value': 42}
    }
    
    event = Event.from_dict(event_dict)
    
    assert event.event_type == EventType.DETECTION
    assert event.timestamp == 456.789
    assert event.source == 'detector'
    assert event.data['value'] == 42


def test_detection_event():
    """Test DetectionEvent creation."""
    event = DetectionEvent(
        timestamp=123.0,
        source="aubio",
        confidence=0.85,
        detector_type="onset",
        buffer_index=42
    )
    
    assert event.event_type == EventType.DETECTION
    assert event.data['confidence'] == 0.85
    assert event.data['detector_type'] == "onset"
    assert event.data['buffer_index'] == 42


class TestEventBus:
    """Test suite for EventBus."""
    
    def test_publish_subscribe(self, event_bus):
        """Test basic publish/subscribe."""
        received_events = []
        
        def handler(event):
            received_events.append(event)
        
        # Subscribe
        event_bus.subscribe(EventType.DETECTION, handler)
        
        # Publish
        event = Event(
            event_type=EventType.DETECTION,
            timestamp=123.456,
            source="test",
            data={'confidence': 0.9}
        )
        event_bus.publish(event)
        
        # Wait briefly for dispatch
        time.sleep(0.1)
        
        # Verify
        assert len(received_events) == 1
        assert received_events[0].event_type == EventType.DETECTION
        assert received_events[0].data['confidence'] == 0.9
    
    def test_multiple_subscribers(self, event_bus):
        """Test multiple subscribers receive same event."""
        received_1 = []
        received_2 = []
        received_3 = []
        
        event_bus.subscribe(EventType.SYSTEM, lambda e: received_1.append(e))
        event_bus.subscribe(EventType.SYSTEM, lambda e: received_2.append(e))
        event_bus.subscribe(EventType.SYSTEM, lambda e: received_3.append(e))
        
        event = Event(EventType.SYSTEM, 123.0, "test")
        event_bus.publish(event)
        
        time.sleep(0.1)
        
        assert len(received_1) == 1
        assert len(received_2) == 1
        assert len(received_3) == 1
    
    def test_type_filtering(self, event_bus):
        """Test events only go to correct type subscribers."""
        detection_events = []
        system_events = []
        health_events = []
        
        event_bus.subscribe(EventType.DETECTION, lambda e: detection_events.append(e))
        event_bus.subscribe(EventType.SYSTEM, lambda e: system_events.append(e))
        event_bus.subscribe(EventType.HEALTH, lambda e: health_events.append(e))
        
        event_bus.publish(Event(EventType.DETECTION, 123.0, "test"))
        event_bus.publish(Event(EventType.SYSTEM, 124.0, "test"))
        event_bus.publish(Event(EventType.HEALTH, 125.0, "test"))
        
        time.sleep(0.1)
        
        assert len(detection_events) == 1
        assert len(system_events) == 1
        assert len(health_events) == 1
    
    def test_all_events_subscriber(self, event_bus):
        """Test subscribing to all event types."""
        all_events = []
        
        event_bus.subscribe(None, lambda e: all_events.append(e))  # None = all types
        
        event_bus.publish(Event(EventType.DETECTION, 123.0, "test"))
        event_bus.publish(Event(EventType.SYSTEM, 124.0, "test"))
        event_bus.publish(Event(EventType.HEALTH, 125.0, "test"))
        
        time.sleep(0.1)
        
        assert len(all_events) == 3
    
    def test_unsubscribe(self, event_bus):
        """Test unsubscribing from events."""
        received = []
        
        def handler(event):
            received.append(event)
        
        event_bus.subscribe(EventType.DETECTION, handler)
        
        # Publish - should receive
        event_bus.publish(Event(EventType.DETECTION, 123.0, "test"))
        time.sleep(0.1)
        assert len(received) == 1
        
        # Unsubscribe
        event_bus.unsubscribe(EventType.DETECTION, handler)
        
        # Publish - should NOT receive
        event_bus.publish(Event(EventType.DETECTION, 124.0, "test"))
        time.sleep(0.1)
        assert len(received) == 1  # Still 1, not 2
    
    def test_stats(self, event_bus):
        """Test event bus statistics."""
        event_bus.publish(Event(EventType.DETECTION, 123.0, "test"))
        event_bus.publish(Event(EventType.SYSTEM, 124.0, "test"))
        
        time.sleep(0.1)
        
        stats = event_bus.get_stats()
        assert stats['events_published'] >= 2
        assert stats['events_dispatched'] >= 2
        assert stats['events_dropped'] == 0
    
    def test_handler_exception_doesnt_break_bus(self, event_bus):
        """Test that exceptions in handlers don't break the bus."""
        received = []
        
        def bad_handler(event):
            raise ValueError("Intentional error")
        
        def good_handler(event):
            received.append(event)
        
        event_bus.subscribe(EventType.DETECTION, bad_handler)
        event_bus.subscribe(EventType.DETECTION, good_handler)
        
        event_bus.publish(Event(EventType.DETECTION, 123.0, "test"))
        time.sleep(0.1)
        
        # Good handler should still receive despite bad handler error
        assert len(received) == 1
