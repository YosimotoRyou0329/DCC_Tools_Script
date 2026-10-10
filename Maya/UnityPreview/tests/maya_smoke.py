"""Run with Maya mayapy; offscreen GUI verification (maya.standalone, no Maya UI)."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
from maya_unity_preview.qt import QtWidgets
from maya_unity_preview.ui import PreviewTool

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
sent = []
with patch("maya_unity_preview.ui.OpenMayaUI.MQtUtil.mainWindow", return_value=0), \
     patch("maya_unity_preview.ui.is_listening", return_value=False):
    window = PreviewTool()
window.show()

# connected -> SceneWatch starts and the first batch contains every mesh
cube = cmds.polyCube(name="smokeCube")[0]
with patch("maya_unity_preview.ui.send_messages", side_effect=lambda m, c: sent.extend(m)):
    window.on_connection_changed(True)
    assert window.watch.active
    window.watch._on_timer()
    window.executor.submit(lambda: None).result()
    app.processEvents()
    assert any(m["type"] == "MESH_DATA_V2" and m["name"].endswith("smokeCubeShape") for m in sent), sent

    # rename -> old Unity object removed, new one sent
    sent.clear()
    cmds.rename(cube, "smokeCube2")
    window.watch._on_timer()
    window.executor.submit(lambda: None).result()
    app.processEvents()
    assert any(m["type"] == "MESH_REMOVE" for m in sent), sent

window.on_connection_changed(False)
assert not window.watch.active
window.close()
assert window.closed
print("PASS: auto sync start/stop, rename removal, window lifecycle")
