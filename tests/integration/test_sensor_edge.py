import time
from threading import Thread

from src.sensors.base import BaseSensor


class SlowSensor(BaseSensor):
    def _connect(self):
        self.connected = True

    def _read_sensor(self):
        time.sleep(0.2)
        return type("Data", (), {"to_dict": lambda self: {"val": 1}})()

    def _disconnect(self):
        self.connected = False


def test_sensor_update_loop_timeout(monkeypatch):
    sensor = SlowSensor(sensor_name="Slow")
    sensor.update_interval = 0.1
    sensor.connect()
    sensor.running = True
    t = Thread(target=sensor._update_loop)
    t.start()
    time.sleep(0.3)
    sensor.running = False
    t.join(timeout=1)
    assert sensor.get_data() is not None


def test_sensor_callback_error():
    sensor = SlowSensor(sensor_name="Slow")

    def bad_callback(data):
        raise Exception("Callback fail")

    sensor.add_callback(bad_callback)
    sensor.connect()
    sensor.running = True
    t = Thread(target=sensor._update_loop)
    t.start()
    time.sleep(0.2)
    sensor.running = False
    t.join(timeout=1)
    # Should not raise
