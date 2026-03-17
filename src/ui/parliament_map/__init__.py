"""
parliament map — live web UI for the strix trilateration server.

A single-page map showing parliament nodes and detection events in real time.
Subscribes to MQTT, serves a browser UI, streams events via WebSocket.

Usage:
    strix-map --broker localhost --port 8080
"""
