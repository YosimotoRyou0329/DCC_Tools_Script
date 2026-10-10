"""Sync engine, independent from the panel: closing / docking the panel never stops syncing.

- watches for the Unity PreviewHost (started here or by hand) and starts syncing when it appears
- SceneWatch reports changed meshes; only meshes in the SyncList are sent
- controls the Unity window (resizable, PiP, hide / show)
- materials: MATERIAL_DEF (Maya colour / base map / normal map) is sent with the meshes that
  use a material, only when it changed; texture files are watched on disk, so re-exporting
  from Substance updates Maya and Unity. Shaders and their values are set in the PreviewHost.
- SESSION tells Unity where to save its material settings: <Maya project>/unityPreview/materials
  (one JSON per material name, so the same material looks the same in every scene of the project)
"""
import json
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from maya import cmds, OpenMayaUI

from .qt import QtCore, QtWidgets, wrapInstance
from .mesh import meshes_for
from .scene_watch import SceneWatch
from .sync_list import SyncList
from .transport import is_listening, send_messages, remove_message
from . import material as mat
from . import unity_window

MONITOR_INTERVAL = 1.0


class PreviewController(QtCore.QObject):
    status_changed = QtCore.Signal(str)
    connection_changed = QtCore.Signal(bool)
    list_changed = QtCore.Signal()
    unity_visibility_changed = QtCore.Signal(bool)
    _connection_detected = QtCore.Signal(bool)
    _send_finished = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QtCore.QSettings("DCCLauncher", "MayaUnityPreview")
        self.process = None
        self.connected = False
        self.sending = False
        self.status = ""
        self.cancelled = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.unity = None
        self.normal_rect = None
        self.sync_list = SyncList()
        self._session_pending = False
        self._sent_defs = {}         # Unity material name -> JSON last sent
        self._def_nodes = {}         # Unity material name -> Maya material node
        self._texture_users = {}     # normalised texture path -> {Unity material names}
        self._texture_watcher = QtCore.QFileSystemWatcher(self)
        self._texture_watcher.fileChanged.connect(self._texture_changed)
        self._changed_textures = set()
        self._texture_timer = QtCore.QTimer(self)
        self._texture_timer.setSingleShot(True)
        self._texture_timer.setInterval(400)    # exporters write in several chunks
        self._texture_timer.timeout.connect(self._reload_textures)
        self.watch = SceneWatch(self._flush, self.sync_list.contains, self._scene_opened, self)
        self._connection_detected.connect(self._on_connection, QtCore.Qt.QueuedConnection)
        self._send_finished.connect(self._on_sent, QtCore.Qt.QueuedConnection)
        QtWidgets.QApplication.instance().aboutToQuit.connect(self.shutdown)
        self._monitor_stop = threading.Event()
        threading.Thread(target=self._monitor, daemon=True).start()
        self._set_status("Unityの起動を待っています（127.0.0.1:50001）")

    # ------------------------------------------------------------------ settings
    @property
    def exe_path(self):
        return str(self.settings.value("exe", ""))

    @exe_path.setter
    def exe_path(self, value):
        self.settings.setValue("exe", value)

    @property
    def auto_sync(self):
        return self.settings.value("auto_sync", True, type=bool)

    @property
    def pip(self):
        return self.settings.value("pip", False, type=bool)

    # ------------------------------------------------------------------ Unity process
    def launch_unity(self):
        path = Path(self.exe_path.strip().strip('"'))
        if not path.is_file() or path.suffix.lower() != ".exe":
            self._set_status("PreviewHostの.exeファイルを指定してください。")
            return
        if self.connected or (self.process is not None and self.process.poll() is None):
            self._set_status("Unityは起動済みです。")
            return
        try:
            self.process = subprocess.Popen([str(path)], cwd=str(path.parent))
        except OSError as error:
            self._set_status(str(error))
            return
        self._set_status("Unityを起動中… 接続できたら自動で同期を始めます。")

    def _monitor(self):
        last = None
        while not self._monitor_stop.is_set():
            listening = is_listening()
            if listening != last:
                last = listening
                self._connection_detected.emit(listening)
            self._monitor_stop.wait(MONITOR_INTERVAL)

    def _on_connection(self, connected):
        self.connected = connected
        if connected:
            self._attach_window()
            if self.auto_sync:
                self._start_sync()
            else:
                self._set_status("Unity接続中（自動同期オフ）")
        else:
            self.watch.stop()
            self.unity = None
            self.normal_rect = None
            self._set_status("Unity未接続：Unityを起動すると自動で同期を始めます。")
        self.connection_changed.emit(connected)

    # ------------------------------------------------------------------ sync
    def _start_sync(self):
        self._sent_defs.clear()      # Unity (re)started: it knows no Maya material yet
        self._session_pending = True
        if self.watch.active:
            self.watch.resend_all()
        else:
            self.watch.start()
        if self.sync_list.uuids:
            self._set_status("自動同期中：リストのオブジェクトの変更をUnityへ送ります。")
        else:
            self._set_status("同期リストが空です。アウトライナーからオブジェクトをドロップしてください。")

    def set_auto_sync(self, enabled):
        self.settings.setValue("auto_sync", enabled)
        if enabled and self.connected:
            self._start_sync()
        elif not enabled:
            self.watch.stop()
            self._set_status("自動同期オフ" + ("（Unity接続中）" if self.connected else ""))

    def resend_list(self):
        if not self.connected:
            self._set_status("Unityが起動していません。")
        elif self.watch.active:
            self.watch.resend_all()
        else:
            paths = [p for p in cmds.ls(type="mesh", long=True, noIntermediate=True) or []
                     if self._is_target_path(p)]
            self._flush(paths, [])

    def _is_target_path(self, path):
        selection = om_selection(path)
        return selection is not None and self.sync_list.contains(selection)

    @staticmethod
    def material_folder():
        root = cmds.workspace(query=True, rootDirectory=True) or ""
        return os.path.join(root, "unityPreview", "materials").replace("\\", "/")

    def _scene_opened(self):
        self._session_pending = True      # the project may have changed
        self.sync_list.load()
        self.list_changed.emit()

    def _flush(self, paths, removed):
        """Called on the main thread. False = busy, retry later."""
        if self.sending:
            return False
        if not self.connected:
            return True
        try:
            meshes = meshes_for(paths)
            definitions = self._material_messages(meshes)
            messages = [remove_message(name) for name in removed] + definitions + meshes
            if self._session_pending:
                messages.insert(0, {"type": "SESSION", "materialFolder": self.material_folder()})
                self._session_pending = False
        except Exception as error:  # a broken mesh must not stop the sync
            self._set_status("メッシュ取得エラー: " + str(error))
            return True
        if not messages:
            return True
        self.sending = True
        names = ", ".join(p.split("|")[-1] for p in paths[:3]) + (" …" if len(paths) > 3 else "")
        future = self.executor.submit(send_messages, messages, self.cancelled)

        def completed(job):
            error = job.exception()
            self._send_finished.emit("送信失敗: " + str(error) if error else
                                     "同期: " + (names or "削除のみ"))
        future.add_done_callback(completed)
        return True

    def _material_messages(self, meshes):
        """MATERIAL_DEF for materials used by these meshes (only the ones that changed)."""
        result, deps_of = [], {}
        for material in dict.fromkeys(m for payload in meshes for m in payload.get("_materials", [])):
            data, deps, textures = mat.definition(material)
            deps_of[material] = deps
            name = data["name"]
            self._def_nodes[name] = material
            for path in textures:
                key = os.path.normcase(os.path.normpath(path))
                self._texture_users.setdefault(key, set()).add(name)
                if os.path.isfile(path) and path not in self._texture_watcher.files():
                    self._texture_watcher.addPath(path)
            text = json.dumps(data, sort_keys=True)
            if self._sent_defs.get(name) != text:
                self._sent_defs[name] = text
                result.append(data)
        for payload in meshes:
            used = payload.pop("_materials", [])
            self.watch.set_dependencies(payload["name"], [d for m in used for d in deps_of.get(m, [])])
        return result

    def _texture_changed(self, path):
        self._changed_textures.add(path)
        self._texture_timer.start()

    def _reload_textures(self):
        """A texture file changed on disk: reload it in Maya and re-send the materials using it."""
        changed, self._changed_textures = self._changed_textures, set()
        for path in changed:
            if os.path.isfile(path) and path not in self._texture_watcher.files():
                self._texture_watcher.addPath(path)    # some exporters replace the file
            mat.reload_file_nodes(path)
            for name in self._texture_users.get(os.path.normcase(os.path.normpath(path)), ()):
                self._sent_defs.pop(name, None)
                node = self._def_nodes.get(name)
                if node and cmds.objExists(node):
                    self.watch.mark_dependents(node)
        if changed:
            self._set_status("テクスチャ更新: " + ", ".join(os.path.basename(p) for p in changed))

    def _on_sent(self, message):
        self.sending = False
        self._set_status(message)

    # ------------------------------------------------------------------ sync list
    def add_to_list(self, nodes):
        added = self.sync_list.add(nodes)
        self.list_changed.emit()
        self.watch.refresh()
        if added:
            self._set_status("同期リストに{}件追加しました。".format(added))
        else:
            self._set_status("追加できるDAGオブジェクトがありません（既に登録済み、またはDAG以外）。")

    def add_selection(self):
        self.add_to_list(cmds.ls(selection=True, long=True, objectsOnly=True) or [])

    def remove_from_list(self, uuids):
        self.sync_list.remove(uuids)
        self.list_changed.emit()
        self.watch.refresh()      # meshes no longer listed are removed from Unity

    def clear_list(self):
        self.sync_list.clear()
        self.list_changed.emit()
        self.watch.refresh()

    # ------------------------------------------------------------------ Unity window (PiP)
    def _attach_window(self):
        if not unity_window.IS_WINDOWS or not self.connected:
            return None
        if self.unity is None or not self.unity.alive():
            pid = self.process.pid if self.process is not None and self.process.poll() is None else None
            hwnd = unity_window.find_unity_window(pid=pid, exe_path=self.exe_path.strip().strip('"') or None)
            self.unity = unity_window.UnityWindow(hwnd) if hwnd else None
            if self.unity:
                self.unity.make_resizable()
                if self.pip:
                    self.set_pip(True)
        return self.unity

    def set_pip(self, enabled):
        self.settings.setValue("pip", enabled)
        window = self._attach_window()
        if window is None:
            return
        if enabled:
            if self.normal_rect is None:
                self.normal_rect = window.rect()
            saved = self.settings.value("pip_rect")
            maya_hwnd = int(wrapInstance(int(OpenMayaUI.MQtUtil.mainWindow()), QtWidgets.QWidget).winId())
            rect = [int(v) for v in saved] if saved else window.default_pip_rect(maya_hwnd)
            window.show()
            window.set_rect(rect)
            window.set_topmost(True)
            self.unity_visibility_changed.emit(True)
        else:
            self.settings.setValue("pip_rect", window.rect())
            window.set_topmost(False)
            if self.normal_rect:
                window.set_rect(self.normal_rect)
            self.normal_rect = None

    def toggle_unity_window(self):
        window = self._attach_window()
        if window is None:
            self._set_status("Unityのウィンドウが見つかりません。")
            return
        if window.visible():
            window.hide()
        else:
            window.show()
            if self.pip:
                window.set_topmost(True)
        self.unity_visibility_changed.emit(window.visible())

    def unity_visible(self):
        return self.unity is not None and self.unity.alive() and self.unity.visible()

    # ------------------------------------------------------------------ misc
    def _set_status(self, text):
        self.status = text
        self.status_changed.emit(text)

    def shutdown(self):
        self._monitor_stop.set()
        self.watch.stop()
        self.cancelled.set()
        if self.unity is not None and self.unity.alive():
            if self.pip:
                self.settings.setValue("pip_rect", self.unity.rect())
            if not self.unity.visible():
                self.unity.show()   # never leave Unity hidden with no way back
        self.executor.shutdown(wait=False)


def om_selection(path):
    from maya.api import OpenMaya as om
    selection = om.MSelectionList()
    try:
        selection.add(path)
        return selection.getDagPath(0)
    except RuntimeError:
        return None
