"""Event bus for pub/sub messaging across the system."""


import logging
import queue
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class EventType(Enum):
    """Types of events in the system"""

    DETECTION = "detection"
    SYSTEM = "system"
    TIMING = "timing"
    HEALTH = "health"
    CONFIG = "config"


@dataclass
class Event:
    """Base event class"""

    event_type: EventType
    timestamp: float
    source: str  # Which node generated this
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "source": self.source,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "Event":
        """Create event from dictionary"""
        return cls(
            event_type=EventType(d["event_type"]),
            timestamp=d["timestamp"],
            source=d["source"],
            data=d.get("data", {}),
        )


@dataclass
class DetectionEvent(Event):
    """Detection event with specific fields"""

    event_type: EventType = field(default=EventType.DETECTION, init=False)
    timestamp: float = 0.0
    source: str = ""
    confidence: float = 0.0
    detector_type: str = ""
    buffer_index: int = 0

    def __post_init__(self):
        self.event_type = EventType.DETECTION
        if "confidence" not in self.data:
            self.data["confidence"] = self.confidence
        if "detector_type" not in self.data:
            self.data["detector_type"] = self.detector_type
        if "buffer_index" not in self.data:
            self.data["buffer_index"] = self.buffer_index


class EventBus:
    """Central event bus for pub/sub messaging"""

    def __init__(self, name: str = "EventBus", max_queue_size: int = 1000):
        self.name = name
        self.subscribers: Dict[EventType, List[Callable]] = {
            event_type: [] for event_type in EventType
        }
        self.all_subscribers: List[Callable] = []  # Subscribe to all events
        self.event_queue = queue.Queue(maxsize=max_queue_size)
        self.running = False
        self.dispatch_thread = None
        self.stats = {
            "events_published": 0,
            "events_dispatched": 0,
            "events_dropped": 0,
        }
        self.lock = threading.Lock()
        self.logger = logging.getLogger(self.__class__.__name__)

    def subscribe(
        self, event_type: Optional[EventType], callback: Callable[[Event], None]
    ):
        """Subscribe to specific event type or all events"""
        with self.lock:
            if event_type is None:
                self.all_subscribers.append(callback)
            else:
                self.subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: Optional[EventType], callback: Callable):
        """Unsubscribe from events"""
        with self.lock:
            if event_type is None:
                if callback in self.all_subscribers:
                    self.all_subscribers.remove(callback)
            else:
                if callback in self.subscribers[event_type]:
                    self.subscribers[event_type].remove(callback)

    def publish(self, event: Event):
        """Publish event to bus"""
        try:
            self.event_queue.put_nowait(event)
            self.stats["events_published"] += 1
            # Debug log for tracing published events
            try:
                evt_type = (
                    event.event_type.value
                    if hasattr(event, "event_type")
                    else str(type(event))
                )
                src = getattr(event, "source", "<unknown>")
                buf_idx = (
                    event.data.get("buffer_index")
                    if isinstance(event.data, dict)
                    else None
                )
                self.logger.debug(
                    f"[{self.name}] Published event: type={evt_type} source={src} buffer_index={buf_idx} timestamp={getattr(event, 'timestamp', None)}"
                )
            except Exception as e:
                # Log failures when formatting the debug message, but do not interrupt publishing
                self.logger.debug(
                    f"[{self.name}] Failed to format published event debug info: %s",
                    e,
                    exc_info=True,
                )
        except queue.Full:
            self.stats["events_dropped"] += 1
            self.logger.warning(
                f"[{self.name}] Warning: Event queue full, dropping event"
            )

    def start(self):
        """Start event dispatch thread"""
        if self.running:
            return

        self.running = True
        self.dispatch_thread = threading.Thread(target=self._dispatch_loop)
        self.dispatch_thread.daemon = True
        self.dispatch_thread.start()
        self.logger.info(f"[{self.name}] Started event bus")

    def stop(self):
        """Stop event dispatch thread"""
        self.running = False
        if self.dispatch_thread:
            self.dispatch_thread.join(timeout=2.0)
        self.logger.info(f"[{self.name}] Stopped event bus")

    def _dispatch_loop(self):
        """Main dispatch loop running in thread"""
        while self.running:
            try:
                event = self.event_queue.get(timeout=0.1)
                self._dispatch_event(event)
                self.stats["events_dispatched"] += 1
            except queue.Empty:
                continue

    def _dispatch_event(self, event: Event):
        """Dispatch event to subscribers"""
        with self.lock:
            # Send to type-specific subscribers
            for callback in self.subscribers[event.event_type]:
                try:
                    callback(event)
                except Exception as e:
                    self.logger.error(
                        f"[{self.name}] Error in subscriber callback: {e}"
                    )

            # Send to all-events subscribers
            for callback in self.all_subscribers:
                try:
                    callback(event)
                except Exception as e:
                    self.logger.error(
                        f"[{self.name}] Error in all-events callback: {e}"
                    )

    def get_stats(self) -> Dict:
        """Get event bus statistics"""
        return self.stats.copy()


# Global event bus instance
_global_event_bus = None


def get_event_bus() -> EventBus:
    """Get global event bus instance"""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
        _global_event_bus.start()
    return _global_event_bus
