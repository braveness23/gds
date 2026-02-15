import pytest
from src.output.mqtt_output import MQTTOutputNode

class DummyClient:
    def __init__(self, fail_connect=False, fail_publish=False):
        self.fail_connect = fail_connect
        self.fail_publish = fail_publish
        self.connected = False
        self.published = False
    def connect(self, *a, **kw):
        if self.fail_connect:
            raise Exception("Connect error")
        self.connected = True
    def publish(self, topic, payload, qos):
        if self.fail_publish:
            class Result:
                rc = 1
            return Result()
        class Result:
            rc = 0
        self.published = True
        return Result()
    def loop_start(self): pass
    def loop_stop(self): pass
    def disconnect(self): pass

def test_mqtt_connect_failure(monkeypatch):
    node = MQTTOutputNode(broker="localhost")
    monkeypatch.setattr("paho.mqtt.client.Client", lambda *a, **kw: DummyClient(fail_connect=True))
    with pytest.raises(Exception):
        node.connect()

def test_mqtt_publish_failure(monkeypatch):
    node = MQTTOutputNode(broker="localhost")
    monkeypatch.setattr("paho.mqtt.client.Client", lambda *a, **kw: DummyClient())
    node.client = DummyClient(fail_publish=True)
    node.connected = True
    node._publish("topic", {"msg": "test"})
    assert not node.client.published
