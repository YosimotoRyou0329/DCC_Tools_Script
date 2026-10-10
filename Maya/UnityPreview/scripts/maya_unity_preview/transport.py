"""Socket transport only; no Maya or Qt calls.

Unity PreviewHost listens on 127.0.0.1:50001 and reads one JSON line per connection.
"""
import json
import socket

HOST = "127.0.0.1"
PORT = 50001


def is_listening(host=HOST, port=PORT, timeout=0.3):
    """True when the Unity PreviewHost accepts connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def send_messages(messages, cancelled=None, host=HOST, port=PORT):
    """Send each message (dict) as one JSON line on its own connection."""
    for message in messages:
        if cancelled is not None and cancelled.is_set():
            return
        payload = (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")
        with socket.create_connection((host, port), timeout=2) as connection:
            connection.sendall(payload)


def remove_message(name):
    return {"type": "MESH_REMOVE", "name": name}


def request(message, host=HOST, port=PORT, timeout=2.0):
    """Send one JSON line and read one JSON line back (e.g. GET_TEMPLATES)."""
    payload = (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")
    with socket.create_connection((host, port), timeout=timeout) as connection:
        connection.sendall(payload)
        with connection.makefile("r", encoding="utf-8") as reader:
            line = reader.readline()
    return json.loads(line) if line.strip() else {}
