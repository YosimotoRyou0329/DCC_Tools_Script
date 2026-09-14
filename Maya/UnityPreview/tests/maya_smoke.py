"""Run with Maya 2024 mayapy; offscreen GUI verification without Maya startup."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from PySide2 import QtWidgets
from unittest.mock import patch
from maya_unity_preview.ui import PreviewTool

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
with patch("maya_unity_preview.ui.OpenMayaUI.MQtUtil.mainWindow", return_value=0):
    window = PreviewTool()
window.show()
assert window.start_preview()
window.start_live()
assert window.live.active
window.display_frame(2, 1, bytes([255, 0, 0, 255] * 2))
assert window.pixmap.width() == 2
window.stop()
assert not window.live.active and window.receiver is None
assert window.start_preview()
window.close()
print("PASS: GUI, receiver restart, live lifecycle, RGBA display")
