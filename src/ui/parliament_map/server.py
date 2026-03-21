"""
Parliament Map server — bridges MQTT detection events to browser via WebSocket.

Architecture:
    MQTT broker → ParliamentMapServer → WebSocket → Browser (Leaflet map)

The server:
- Subscribes to gunshot/# MQTT topics
- Buffers last MAX_EVENTS detection/node events in memory
- Serves a single-page HTML map application
- Pushes new events to all connected browsers via WebSocket

Handled topics:
    gunshot/+/detections   — per-node detection events
    gunshot/+/health       — per-node health/status
    gunshot/results        — trilateration results
    gunshot/detections     — broadcast detection fallback
"""

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)

MAX_EVENTS = 500


@dataclass
class NodeStatus:
    node_id: str
    latitude: float
    longitude: float
    altitude: float
    last_seen: float
    timing_stratum: int = 0
    timing_offset_ms: float = 0.0
    detection_count: int = 0
    status: str = "online"  # online / degraded / offline

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_stale(self) -> bool:
        return (time.time() - self.last_seen) > 60


@dataclass
class DetectionEvent:
    event_id: str
    node_id: str
    timestamp: float
    latitude: float
    longitude: float
    altitude: float
    confidence: float
    detector_type: str
    event_type: str = "unknown"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TrilaterationEvent:
    result_id: str
    timestamp: float
    latitude: float
    longitude: float
    altitude: float
    confidence: float
    num_nodes: int
    contributing_nodes: list
    event_type: str
    geometry_score: float
    residual_error: float

    def to_dict(self) -> dict:
        return asdict(self)


class ParliamentMapServer:
    """
    Bridges MQTT events to a browser-based live map via WebSocket.

    Subscribes to:
        gunshot/+/detections   — per-node detection events
        gunshot/+/health       — per-node health/status
        gunshot/results        — trilateration results from fusion server
        gunshot/nodes          — node registry updates

    Publishes via WebSocket:
        { "type": "node_update", "node": {...} }
        { "type": "detection", "detection": {...} }
        { "type": "trilateration", "result": {...} }
        { "type": "history", "nodes": [...], "events": [...] }
    """

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        web_port: int = 8080,
        mqtt_username: Optional[str] = None,
        mqtt_password: Optional[str] = None,
        max_events: int = MAX_EVENTS,
    ):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.web_port = web_port
        self.mqtt_username = mqtt_username
        self.mqtt_password = mqtt_password
        self.max_events = max_events

        self.nodes: Dict[str, NodeStatus] = {}
        self.detections: deque = deque(maxlen=max_events)
        self.trilateration_results: deque = deque(maxlen=max_events)
        self.websocket_clients: Set[Any] = set()

        self._mqtt_client = None
        self._loop = None

    # ------------------------------------------------------------------ #
    # MQTT handling                                                         #
    # ------------------------------------------------------------------ #

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info(f"Connected to MQTT broker at {self.broker_host}:{self.broker_port}")
            client.subscribe("gunshot/#", qos=1)
        else:
            logger.error(f"MQTT connection failed with code {rc}")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            topic = msg.topic
            asyncio.run_coroutine_threadsafe(
                self._handle_message(topic, payload), self._loop
            )
        except Exception as e:
            logger.warning(f"Failed to parse MQTT message on {msg.topic}: {e}")

    async def _handle_message(self, topic: str, payload: dict):
        parts = topic.split("/")

        if len(parts) == 3 and parts[2] == "detections":
            await self._handle_detection(payload)
        elif len(parts) == 3 and parts[2] == "health":
            await self._handle_health(payload)
        elif len(parts) == 2 and parts[1] == "results":
            await self._handle_trilateration(payload)
        elif topic == "gunshot/detections":
            await self._handle_detection(payload)

    async def _handle_detection(self, payload: dict):
        try:
            location = payload.get("location", {})
            det = payload.get("detection", {})
            node_id = payload.get("node_id", "unknown")

            lat = location.get("latitude", 0.0)
            lon = location.get("longitude", 0.0)

            if lat == 0.0 and lon == 0.0:
                return  # No location data, skip

            event = DetectionEvent(
                event_id=f"{node_id}_{payload.get('timestamp', time.time())}",
                node_id=node_id,
                timestamp=payload.get("timestamp", time.time()),
                latitude=lat,
                longitude=lon,
                altitude=location.get("altitude", 0.0),
                confidence=det.get("confidence", 0.0),
                detector_type=det.get("detector_type", "unknown"),
                event_type=payload.get("event_type", "detection"),
            )
            self.detections.append(event)

            # Update node last-seen
            if node_id in self.nodes:
                self.nodes[node_id].last_seen = time.time()
                self.nodes[node_id].detection_count += 1
                self.nodes[node_id].latitude = lat
                self.nodes[node_id].longitude = lon
            else:
                self.nodes[node_id] = NodeStatus(
                    node_id=node_id,
                    latitude=lat,
                    longitude=lon,
                    altitude=location.get("altitude", 0.0),
                    last_seen=time.time(),
                    detection_count=1,
                )

            await self._broadcast({"type": "detection", "detection": event.to_dict()})
            await self._broadcast({"type": "node_update", "node": self.nodes[node_id].to_dict()})

        except Exception as e:
            logger.warning(f"Failed to process detection: {e}")

    async def _handle_health(self, payload: dict):
        try:
            node_id = payload.get("node_id", "unknown")
            location = payload.get("location", {})
            lat = location.get("latitude", 0.0)
            lon = location.get("longitude", 0.0)

            if node_id not in self.nodes:
                if lat == 0.0 and lon == 0.0:
                    return
                self.nodes[node_id] = NodeStatus(
                    node_id=node_id,
                    latitude=lat,
                    longitude=lon,
                    altitude=location.get("altitude", 0.0),
                    last_seen=time.time(),
                )
            else:
                node = self.nodes[node_id]
                node.last_seen = time.time()
                if lat != 0.0:
                    node.latitude = lat
                    node.longitude = lon

            timing = payload.get("timing", {})
            if timing:
                self.nodes[node_id].timing_stratum = timing.get("stratum", 0)
                self.nodes[node_id].timing_offset_ms = timing.get("offset_ms", 0.0)

            await self._broadcast({"type": "node_update", "node": self.nodes[node_id].to_dict()})

        except Exception as e:
            logger.warning(f"Failed to process health message: {e}")

    async def _handle_trilateration(self, payload: dict):
        try:
            result = TrilaterationEvent(
                result_id=f"result_{payload.get('timestamp', time.time())}",
                timestamp=payload.get("timestamp", time.time()),
                latitude=payload.get("latitude", 0.0),
                longitude=payload.get("longitude", 0.0),
                altitude=payload.get("altitude", 0.0),
                confidence=payload.get("confidence", 0.0),
                num_nodes=payload.get("num_nodes", 0),
                contributing_nodes=payload.get("contributing_nodes", []),
                event_type=payload.get("event_type", "unknown"),
                geometry_score=payload.get("geometry_score", 0.0),
                residual_error=payload.get("residual_error", 0.0),
            )
            self.trilateration_results.append(result)
            await self._broadcast({"type": "trilateration", "result": result.to_dict()})
        except Exception as e:
            logger.warning(f"Failed to process trilateration result: {e}")

    # ------------------------------------------------------------------ #
    # WebSocket                                                             #
    # ------------------------------------------------------------------ #

    async def _broadcast(self, message: dict):
        if not self.websocket_clients:
            return
        data = json.dumps(message)
        dead = set()
        for ws in list(self.websocket_clients):  # snapshot — safe under concurrent connect/disconnect
            try:
                await ws.send_str(data)
            except Exception:
                dead.add(ws)
        self.websocket_clients -= dead

    async def _send_history(self, ws):
        history = {
            "type": "history",
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "detections": [d.to_dict() for d in self.detections],
            "trilateration": [r.to_dict() for r in self.trilateration_results],
        }
        await ws.send_str(json.dumps(history))

    # ------------------------------------------------------------------ #
    # Web server                                                            #
    # ------------------------------------------------------------------ #

    async def _websocket_handler(self, request):
        from aiohttp import web
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.websocket_clients.add(ws)
        logger.info(f"Browser connected — {len(self.websocket_clients)} client(s)")

        await self._send_history(ws)

        try:
            async for msg in ws:
                pass  # client messages not used in v1
        except Exception:
            pass
        finally:
            self.websocket_clients.discard(ws)
            logger.info(f"Browser disconnected — {len(self.websocket_clients)} client(s)")

        return ws

    async def _index_handler(self, request):
        from aiohttp import web
        from pathlib import Path
        html_path = Path(__file__).parent / "static" / "index.html"
        return web.FileResponse(html_path)

    async def _status_handler(self, request):
        from aiohttp import web
        return web.json_response({
            "status": "ok",
            "nodes": len(self.nodes),
            "detections": len(self.detections),
            "trilateration_results": len(self.trilateration_results),
            "websocket_clients": len(self.websocket_clients),
        })

    def _start_mqtt(self):
        import paho.mqtt.client as mqtt
        self._mqtt_client = mqtt.Client(client_id="parliament-map")
        self._mqtt_client.on_connect = self._on_connect
        self._mqtt_client.on_message = self._on_message
        if self.mqtt_username:
            self._mqtt_client.username_pw_set(self.mqtt_username, self.mqtt_password)
        self._mqtt_client.connect_async(self.broker_host, self.broker_port, keepalive=60)
        self._mqtt_client.loop_start()

    async def run(self):
        from aiohttp import web
        self._loop = asyncio.get_event_loop()
        self._start_mqtt()

        app = web.Application()
        app.router.add_get("/", self._index_handler)
        app.router.add_get("/ws", self._websocket_handler)
        app.router.add_get("/status", self._status_handler)
        app.router.add_static("/static", path=str(__import__("pathlib").Path(__file__).parent / "static"))

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self.web_port)
        await site.start()

        logger.info(f"Parliament map running at http://localhost:{self.web_port}")
        logger.info(f"MQTT broker: {self.broker_host}:{self.broker_port}")

        try:
            while True:
                await asyncio.sleep(10)
                # Mark stale nodes — snapshot dict to avoid mutation during async iteration
                updates = []
                for node in list(self.nodes.values()):
                    new_status = "offline" if node.is_stale else "online"
                    if new_status != node.status:
                        node.status = new_status
                        updates.append(node.to_dict())
                for node_dict in updates:
                    await self._broadcast({"type": "node_update", "node": node_dict})
        except asyncio.CancelledError:
            pass
        finally:
            if self._mqtt_client:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            await runner.cleanup()

    def start(self):
        asyncio.run(self.run())
