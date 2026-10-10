"""Run with Maya mayapy (maya.standalone, offscreen Qt). Checks the sync engine without Unity."""
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
from maya_unity_preview.controller import PreviewController

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
sent = []


def pump(controller):
    controller.watch._on_timer()
    controller.executor.submit(lambda: None).result()
    app.processEvents()


with patch("maya_unity_preview.controller.is_listening", return_value=False), \
     patch("maya_unity_preview.controller.unity_window.IS_WINDOWS", False):
    controller = PreviewController()
cube = cmds.polyCube(name="smokeCube")[0]
other = cmds.polySphere(name="smokeSphere")[0]

with patch("maya_unity_preview.controller.send_messages", side_effect=lambda m, c: sent.extend(m)):
    controller._on_connection(True)
    pump(controller)
    assert not sent, "empty sync list must send nothing"

    controller.add_to_list([cube])
    pump(controller)
    names = [m["name"] for m in sent if m["type"] == "MESH_DATA_V2"]
    assert names and all("smokeCube" in n for n in names), sent
    assert any(m["type"] == "MATERIAL_DEF" for m in sent), "material definition must be sent with the mesh"

    assert sent[0]["type"] == "SESSION" and sent[0]["materialFolder"].endswith("unityPreview/materials"), sent[0]

    sent.clear()
    cmds.move(1, 2, 3, cube)
    pump(controller)
    assert any(m["type"] == "MESH_DATA_V2" for m in sent), "transform move must sync"

    sent.clear()
    controller.remove_from_list(controller.sync_list.uuids)
    pump(controller)
    assert any(m["type"] == "MESH_REMOVE" for m in sent), sent

controller._on_connection(False)
assert not controller.watch.active
controller.shutdown()
print("PASS: sync list filter, material defs, transform sync, list removal, connection lifecycle")
