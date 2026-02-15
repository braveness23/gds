#!/usr/bin/env python3
import ssl
import sys
import threading
import time

import yaml

try:
    import paho.mqtt.client as mqtt
except Exception as e:
    print("paho-mqtt not available:", e)
    sys.exit(2)

CONFIG_PATH = "config.yaml"


def load_config(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main():
    cfg = load_config(CONFIG_PATH)
    mqtt_cfg = cfg.get("output", {}).get("mqtt", {})

    broker = mqtt_cfg.get("broker", "localhost")
    port = mqtt_cfg.get("port", 1883)
    use_tls = mqtt_cfg.get("use_tls", False)
    tls_ca = mqtt_cfg.get("tls_ca_cert")
    tls_insecure = mqtt_cfg.get("tls_insecure", False)
    username = mqtt_cfg.get("username")
    password = mqtt_cfg.get("password")

    print(
        f"Attempting connect -> {broker}:{port} use_tls={use_tls} tls_ca={tls_ca} tls_insecure={tls_insecure}"
    )

    evt = threading.Event()
    result = {"rc": None}
    pub_evt = threading.Event()

    def on_connect(client, userdata, flags, rc):
        result["rc"] = rc
        if rc == 0:
            print("on_connect: rc=0 (success)")
        else:
            print(f"on_connect: rc={rc}")
        evt.set()

    def on_disconnect(client, userdata, rc):
        print(f"on_disconnect: rc={rc}")

    def on_publish(client, userdata, mid):
        print(f"on_publish: mid={mid}")
        pub_evt.set()

    client = mqtt.Client(client_id=f"live_test_{int(time.time())}")
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_publish = on_publish

    if username:
        client.username_pw_set(username, password)

    if use_tls:
        try:
            if tls_ca:
                print(f"Using custom CA: {tls_ca}")
                client.tls_set(ca_certs=tls_ca)
            elif tls_insecure:
                print("TLS insecure mode: certificate verification disabled")
                client.tls_set(cert_reqs=ssl.CERT_NONE)
                client.tls_insecure_set(True)
            else:
                print("TLS enabled with system CA verification")
                client.tls_set()
        except Exception as e:
            print("Failed to configure TLS:", e)
            print("Falling back to insecure TLS (accept self-signed)")
            try:
                client.tls_set(cert_reqs=ssl.CERT_NONE)
                client.tls_insecure_set(True)
            except Exception as e2:
                print("TLS fallback failed:", e2)
                sys.exit(3)

    try:
        client.connect(broker, port, keepalive=10)
    except Exception as e:
        print("Connect attempt failed:", e)
        sys.exit(4)

    client.loop_start()

    if not evt.wait(8):
        print("Timed out waiting for on_connect callback")
        client.loop_stop()
        try:
            client.disconnect()
        except Exception:
            pass
        sys.exit(5)

    # If connected rc==0, publish a test message then disconnect
    try:
        topic = mqtt_cfg.get("topic", "gunshot/detections")
        payload = {
            "node_id": mqtt_cfg.get("username", "test_node"),
            "test": "live_publish",
            "timestamp": time.time(),
        }
        import json

        print(f"Publishing test message to {topic}")
        info = client.publish(topic, json.dumps(payload), qos=mqtt_cfg.get("qos", 1))
        # Wait for publish callback (ack) when QoS >=1
        if not pub_evt.wait(8):
            print("Timed out waiting for publish acknowledgement")
        else:
            print("Publish acknowledged")
    except Exception as e:
        print("Publish failed:", e)
    time.sleep(0.5)
    try:
        client.disconnect()
    except Exception as e:
        print("Disconnect failed:", e)
    client.loop_stop()

    print("Test complete, on_connect rc=", result["rc"])
    sys.exit(0)


if __name__ == "__main__":
    main()
