import json
import socket
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from maya_unity_preview.transport import is_listening, send_messages, remove_message, request


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(8)
        self.port = self.server.getsockname()[1]

    def tearDown(self):
        self.server.close()

    def test_is_listening(self):
        self.assertTrue(is_listening(port=self.port))
        self.server.close()
        self.assertFalse(is_listening(port=self.port))

    def test_one_json_line_per_connection(self):
        received = []

        def accept(count):
            for _ in range(count):
                client, _ = self.server.accept()
                with client, client.makefile("r", encoding="utf-8") as reader:
                    received.append(json.loads(reader.readline()))

        worker = threading.Thread(target=accept, args=(2,))
        worker.start()
        send_messages([{"type": "MESH_DATA_V2", "name": "a"}, remove_message("|b|bShape")], port=self.port)
        worker.join(3)
        self.assertEqual(received, [{"type": "MESH_DATA_V2", "name": "a"},
                                    {"type": "MESH_REMOVE", "name": "|b|bShape"}])

    def test_request_reads_one_reply_line(self):
        def answer():
            client, _ = self.server.accept()
            with client, client.makefile("rw", encoding="utf-8") as stream:
                assert json.loads(stream.readline())["type"] == "GET_TEMPLATES"
                stream.write(json.dumps({"type": "TEMPLATES", "templates": [{"name": "HDRP/Lit"}]}) + "\n")
                stream.flush()

        worker = threading.Thread(target=answer)
        worker.start()
        reply = request({"type": "GET_TEMPLATES"}, port=self.port)
        worker.join(3)
        self.assertEqual(reply["templates"][0]["name"], "HDRP/Lit")

    def test_cancelled_sends_nothing(self):
        event = threading.Event()
        event.set()
        send_messages([{"type": "x"}], cancelled=event, port=self.port)
        self.server.settimeout(0.2)
        with self.assertRaises(socket.timeout):
            self.server.accept()


if __name__ == "__main__":
    unittest.main()
