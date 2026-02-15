from src.output.mqtt_output import MQTTOutputNode


class DummyEvent:
    def __init__(self, timestamp, data):
        self.timestamp = timestamp
        self.data = data


class DummyBus:
    def __init__(self):
        self.published = []

    def publish(self, event):
        self.published.append(event)


def test_mqtt_output_event_bus_disconnect(monkeypatch):
    node = MQTTOutputNode(broker="localhost", event_bus=DummyBus())
    node.connected = False
    event = DummyEvent(timestamp=0, data={})
    node._on_detection_event(event)
    node._on_health_event(event)
    node._on_system_event(event)
    # Should not raise, should not publish
    assert node.event_bus.published == []


def test_mqtt_output_publish_invalid_topic(monkeypatch):
    node = MQTTOutputNode(broker="localhost")
    node.connected = True
    node.client = type(
        "C", (), {"publish": lambda *a, **k: type("R", (), {"rc": 1})()}
    )()
    node._publish("", {"msg": "test"})
    # Should not raise
