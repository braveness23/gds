"""Unit tests for the parliament map server."""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.ui.parliament_map.server import (
    ParliamentMapServer,
    NodeStatus,
    DetectionEvent,
    TrilaterationEvent,
)


class TestNodeStatus:
    def test_online_node_not_stale(self):
        node = NodeStatus(
            node_id="test", latitude=37.77, longitude=-122.41,
            altitude=0, last_seen=time.time()
        )
        assert not node.is_stale

    def test_old_node_is_stale(self):
        node = NodeStatus(
            node_id="test", latitude=37.77, longitude=-122.41,
            altitude=0, last_seen=time.time() - 120
        )
        assert node.is_stale

    def test_to_dict_has_required_fields(self):
        node = NodeStatus(
            node_id="witness", latitude=37.77, longitude=-122.41,
            altitude=150, last_seen=time.time()
        )
        d = node.to_dict()
        assert d["node_id"] == "witness"
        assert d["latitude"] == 37.77
        assert d["longitude"] == -122.41
        assert "status" in d
        assert "detection_count" in d


class TestDetectionEvent:
    def test_to_dict(self):
        event = DetectionEvent(
            event_id="e1", node_id="node_alpha", timestamp=1000.0,
            latitude=37.77, longitude=-122.41, altitude=0.0,
            confidence=0.9, detector_type="aubio", event_type="gunshot"
        )
        d = event.to_dict()
        assert d["node_id"] == "node_alpha"
        assert d["confidence"] == 0.9
        assert d["event_type"] == "gunshot"


class TestTrilaterationEvent:
    def test_to_dict(self):
        result = TrilaterationEvent(
            result_id="r1", timestamp=1000.0,
            latitude=37.77, longitude=-122.41, altitude=0.0,
            confidence=0.85, num_nodes=4,
            contributing_nodes=["a", "b", "c", "d"],
            event_type="gunshot", geometry_score=0.8, residual_error=1.2
        )
        d = result.to_dict()
        assert d["num_nodes"] == 4
        assert len(d["contributing_nodes"]) == 4
        assert d["geometry_score"] == 0.8


class TestParliamentMapServer:
    def make_server(self):
        return ParliamentMapServer(
            broker_host="localhost",
            broker_port=1883,
            web_port=8080,
        )

    def test_init(self):
        server = self.make_server()
        assert server.broker_host == "localhost"
        assert server.web_port == 8080
        assert len(server.nodes) == 0
        assert len(server.detections) == 0

    @pytest.mark.asyncio
    async def test_handle_detection_updates_node(self):
        server = self.make_server()
        server._loop = asyncio.get_event_loop()

        payload = {
            "node_id": "node_alpha",
            "timestamp": time.time(),
            "location": {"latitude": 37.77, "longitude": -122.41, "altitude": 150.0},
            "detection": {"confidence": 0.9, "detector_type": "aubio"},
            "event_type": "gunshot",
        }

        with patch.object(server, "_broadcast", new_callable=AsyncMock):
            await server._handle_detection(payload)

        assert "node_alpha" in server.nodes
        assert server.nodes["node_alpha"].detection_count == 1
        assert len(server.detections) == 1

    @pytest.mark.asyncio
    async def test_handle_detection_skips_zero_coords(self):
        server = self.make_server()
        server._loop = asyncio.get_event_loop()

        payload = {
            "node_id": "node_alpha",
            "timestamp": time.time(),
            "location": {"latitude": 0.0, "longitude": 0.0, "altitude": 0.0},
            "detection": {"confidence": 0.5, "detector_type": "threshold"},
        }

        with patch.object(server, "_broadcast", new_callable=AsyncMock):
            await server._handle_detection(payload)

        assert "node_alpha" not in server.nodes
        assert len(server.detections) == 0

    @pytest.mark.asyncio
    async def test_handle_trilateration(self):
        server = self.make_server()
        server._loop = asyncio.get_event_loop()

        payload = {
            "timestamp": time.time(),
            "latitude": 37.77, "longitude": -122.41, "altitude": 0.0,
            "confidence": 0.88, "num_nodes": 4,
            "contributing_nodes": ["a", "b", "c", "d"],
            "event_type": "gunshot",
            "geometry_score": 0.75, "residual_error": 0.8,
        }

        with patch.object(server, "_broadcast", new_callable=AsyncMock):
            await server._handle_trilateration(payload)

        assert len(server.trilateration_results) == 1

    @pytest.mark.asyncio
    async def test_broadcast_skips_dead_clients(self):
        server = self.make_server()
        dead_ws = MagicMock()
        dead_ws.send_str = AsyncMock(side_effect=Exception("closed"))
        alive_ws = MagicMock()
        alive_ws.send_str = AsyncMock()

        server.websocket_clients = {dead_ws, alive_ws}
        await server._broadcast({"type": "test"})

        assert dead_ws not in server.websocket_clients
        assert alive_ws in server.websocket_clients

    @pytest.mark.asyncio
    async def test_node_becomes_stale(self):
        server = self.make_server()
        server.nodes["old_node"] = NodeStatus(
            node_id="old_node", latitude=37.77, longitude=-122.41,
            altitude=0, last_seen=time.time() - 120, status="online"
        )

        with patch.object(server, "_broadcast", new_callable=AsyncMock) as mock_broadcast:
            # Simulate one stale-check cycle
            for node in server.nodes.values():
                new_status = "offline" if node.is_stale else "online"
                if new_status != node.status:
                    node.status = new_status
                    await server._broadcast({"type": "node_update", "node": node.to_dict()})

        assert server.nodes["old_node"].status == "offline"
        mock_broadcast.assert_called_once()

    def test_max_events_respected(self):
        server = ParliamentMapServer(max_events=5)
        for i in range(10):
            server.detections.append(DetectionEvent(
                event_id=str(i), node_id="n", timestamp=float(i),
                latitude=37.0, longitude=-122.0, altitude=0.0,
                confidence=0.9, detector_type="test"
            ))
        assert len(server.detections) == 5
