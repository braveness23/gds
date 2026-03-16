"""MQTT publisher for simulation detections.

Converts SimulatedDetection objects to MQTT payloads matching the schema
expected by src.trilateration.models.Detection.from_mqtt_payload().

Can publish via MockMQTTBroker (for integration tests) or a real broker.
"""

import json
from typing import List

from tests.simulation.acoustic_simulator import SimulatedDetection


def detection_to_payload(sim_detection: SimulatedDetection) -> dict:
    """Convert SimulatedDetection to MQTT payload dict.

    Args:
        sim_detection: A simulated detection result.

    Returns:
        Payload dict matching Detection.from_mqtt_payload() schema.
    """
    return {
        "node_id": sim_detection.node.node_id,
        "timestamp": sim_detection.detection_timestamp,
        "location": {
            "latitude": sim_detection.node_latitude,
            "longitude": sim_detection.node_longitude,
            "altitude": sim_detection.node_altitude,
        },
        "detection": {
            "confidence": 0.95,
            "detector_type": "simulation",
        },
    }


def to_detection_objects(sim_detections: List[SimulatedDetection]) -> list:
    """Convert SimulatedDetection list to Detection objects for direct engine use.

    Args:
        sim_detections: List of SimulatedDetection from AcousticSimulator.

    Returns:
        List of src.trilateration.models.Detection objects.
    """
    from src.trilateration.models import Detection

    return [
        Detection.from_mqtt_payload(detection_to_payload(sd))
        for sd in sim_detections
    ]


class SimulationMQTTPublisher:
    """Publishes SimulatedDetection objects as MQTT messages.

    Works with MockMQTTBroker for in-process integration tests.
    Topics published:
      - gunshot/detections
      - gunshot/{node_id}/detections
    """

    def __init__(self, broker):
        """Args:
            broker: MockMQTTBroker instance for routing messages.
        """
        self._broker = broker

    def publish(self, sim_detections: List[SimulatedDetection]) -> None:
        """Publish detections to MQTT topics via the mock broker.

        Args:
            sim_detections: Detections to publish.
        """
        from tests.mocks.mock_mqtt import MockMQTTClient

        client = MockMQTTClient(client_id="sim_publisher", broker=self._broker)
        client.connect("localhost")

        for sd in sim_detections:
            payload_bytes = json.dumps(detection_to_payload(sd)).encode()
            node_id = sd.node.node_id
            client.publish("gunshot/detections", payload_bytes, qos=1)
            client.publish(f"gunshot/{node_id}/detections", payload_bytes, qos=1)
