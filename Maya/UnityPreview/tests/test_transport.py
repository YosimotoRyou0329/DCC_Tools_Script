import socket
import struct
import threading
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from maya_unity_preview.transport import read_frame, FrameReceiver


class TransportTests(unittest.TestCase):
    def test_fragmented_frame(self):
        a, b = socket.socketpair()
        payload = struct.pack("<iii", 2, 1, 8) + bytes(range(8))
        def writer():
            with a:
                for byte in payload:
                    a.sendall(bytes([byte]))
        worker = threading.Thread(target=writer)
        worker.start()
        with b:
            self.assertEqual(read_frame(b), (2, 1, bytes(range(8))))
        worker.join()

    def test_reject_bad_size_and_truncated_frame(self):
        for data, error in ((struct.pack("<iii", 1, 1, 8), ValueError),
                            (struct.pack("<iii", 1, 1, 4) + b"x", ConnectionError)):
            a, b = socket.socketpair()
            a.sendall(data)
            a.close()
            with b, self.assertRaises(error):
                read_frame(b)

    def test_start_stop_releases_port(self):
        for _ in range(2):
            receiver = FrameReceiver(lambda *args: None, lambda error: None)
            receiver.start()
            receiver.stop()
            self.assertFalse(receiver.thread.is_alive())


if __name__ == "__main__":
    unittest.main()
