"""Socket transport only; no Maya or Qt calls."""
import json
import socket
import struct
import threading


def read_exact(connection, size):
    result = bytearray()
    while len(result) < size:
        part = connection.recv(min(size - len(result), 1024 * 1024))
        if not part:
            raise ConnectionError("Frame connection closed before completion")
        result.extend(part)
    return bytes(result)


def read_frame(connection):
    width, height, size = struct.unpack("<iii", read_exact(connection, 12))
    if not (0 < width <= 8192 and 0 < height <= 8192 and
            size == width * height * 4 and size <= 64 * 1024 * 1024):
        raise ValueError("Invalid RGBA frame header")
    return width, height, read_exact(connection, size)


def send_meshes(meshes, cancelled=None):
    for mesh in meshes:
        if cancelled is not None and cancelled.is_set():
            return
        payload = (json.dumps(mesh, separators=(",", ":")) + "\n").encode("utf-8")
        with socket.create_connection(("127.0.0.1", 50001), timeout=2) as connection:
            connection.sendall(payload)


class FrameReceiver:
    def __init__(self, on_frame, on_error):
        self.on_frame = on_frame
        self.on_error = on_error
        self.stop_event = threading.Event()
        self.listener = None
        self.client = None
        self.thread = None

    def start(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind(("127.0.0.1", 50002))
            listener.listen(2)
            listener.settimeout(0.5)
        except Exception:
            listener.close()
            raise
        self.listener = listener
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while not self.stop_event.is_set():
            try:
                client, _ = self.listener.accept()
                self.client = client
                with client:
                    if self.stop_event.is_set():
                        return
                    client.settimeout(3)
                    frame = read_frame(client)
                    if not self.stop_event.is_set():
                        self.on_frame(*frame)
            except socket.timeout:
                continue
            except (OSError, ValueError, ConnectionError) as error:
                if not self.stop_event.is_set():
                    self.on_error(str(error))
            finally:
                self.client = None

    def stop(self):
        self.stop_event.set()
        for connection in (self.client, self.listener):
            if connection:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                connection.close()
        if self.thread:
            self.thread.join(timeout=4)
