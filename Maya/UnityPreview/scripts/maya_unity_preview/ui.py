"""Maya-owned GUI and lifecycle coordination.

- Unity started (by this tool or by hand) -> detected automatically, all meshes are sent,
  then every change is synced by SceneWatch. No "send" button needed.
- The Unity window itself is the preview: it can be resized, pinned as Picture-in-Picture
  (always on top) and hidden / shown from here.
"""
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from maya import cmds, OpenMayaUI

from .qt import QtCore, QtWidgets, wrapInstance
from .mesh import meshes_for
from .scene_watch import SceneWatch
from .transport import is_listening, send_messages, remove_message
from . import unity_window

MONITOR_INTERVAL = 1.0


class PreviewTool(QtWidgets.QDialog):
    connection_changed = QtCore.Signal(bool)
    send_finished = QtCore.Signal(str)

    def __init__(self):
        self.maya_window = wrapInstance(int(OpenMayaUI.MQtUtil.mainWindow()), QtWidgets.QWidget)
        super().__init__(self.maya_window)
        self.setWindowTitle("Maya Unity HDRP Preview")
        self.settings = QtCore.QSettings("DCCLauncher", "MayaUnityPreview")
        self.process = None
        self.closed = False
        self.connected = False
        self.sending = False
        self.cancelled = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.unity = None
        self.normal_rect = None
        self.watch = SceneWatch(self.flush, self)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("Unity PreviewHost.exe"))
        row = QtWidgets.QHBoxLayout()
        self.exe = QtWidgets.QLineEdit(self.settings.value("exe", ""))
        row.addWidget(self.exe, 1)
        for label, action in (("参照", self.browse), ("Unityを起動", self.launch_host)):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(action)
            row.addWidget(button)
        layout.addLayout(row)

        row = QtWidgets.QHBoxLayout()
        self.auto_sync = QtWidgets.QCheckBox("自動同期")
        self.auto_sync.setChecked(self.settings.value("auto_sync", True, type=bool))
        self.auto_sync.toggled.connect(self.auto_sync_toggled)
        row.addWidget(self.auto_sync)
        resend = QtWidgets.QPushButton("全メッシュを再送信")
        resend.clicked.connect(self.resend_all)
        row.addWidget(resend)
        row.addStretch(1)
        layout.addLayout(row)

        row = QtWidgets.QHBoxLayout()
        self.pip = QtWidgets.QCheckBox("PiP（常に手前の小窓）")
        self.pip.setChecked(self.settings.value("pip", False, type=bool))
        self.pip.toggled.connect(self.apply_pip)
        row.addWidget(self.pip)
        self.visibility = QtWidgets.QPushButton("Unityを隠す")
        self.visibility.clicked.connect(self.toggle_unity_window)
        row.addWidget(self.visibility)
        row.addStretch(1)
        layout.addLayout(row)

        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(QtCore.Qt.PlainText)
        layout.addWidget(self.status)
        hint = QtWidgets.QLabel("Unityの窓は端をドラッグでサイズ変更 / Unity上でTabキー: Hierarchy・Inspectorの表示切替")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#999999;")
        layout.addWidget(hint)
        self.resize(560, 10)

        self.connection_changed.connect(self.on_connection_changed, QtCore.Qt.QueuedConnection)
        self.send_finished.connect(self.on_send_finished, QtCore.Qt.QueuedConnection)
        QtWidgets.QApplication.instance().aboutToQuit.connect(self.shutdown)

        self.monitor_stop = threading.Event()
        self.monitor = threading.Thread(target=self.monitor_unity, daemon=True)
        self.monitor.start()
        self.set_status("Unityの起動を待っています（127.0.0.1:50001）")

    # ------------------------------------------------------------------ Unity process
    def browse(self):
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "PreviewHost.exeを選択", self.exe.text(), "Executable (*.exe)")
        if filename:
            self.exe.setText(filename)
            self.settings.setValue("exe", filename)

    def launch_host(self):
        path = Path(self.exe.text().strip().strip('"'))
        if not path.is_file() or path.suffix.lower() != ".exe":
            self.set_status("PreviewHostの.exeファイルを指定してください。")
            return
        if self.connected or (self.process is not None and self.process.poll() is None):
            self.set_status("Unityは起動済みです。")
            return
        try:
            self.process = subprocess.Popen([str(path)], cwd=str(path.parent))
        except OSError as error:
            self.set_status(str(error))
            return
        self.settings.setValue("exe", str(path))
        self.set_status("Unityを起動中… 接続できたら自動で同期を始めます。")

    def monitor_unity(self):
        """Background thread: report when the Unity PreviewHost appears or goes away."""
        last = None
        while not self.monitor_stop.is_set():
            listening = is_listening()
            if listening != last:
                last = listening
                self.connection_changed.emit(listening)
            self.monitor_stop.wait(MONITOR_INTERVAL)

    def on_connection_changed(self, connected):
        self.connected = connected
        if connected:
            self.attach_window()
            if self.auto_sync.isChecked():
                self.start_sync()
            else:
                self.set_status("Unity接続中（自動同期オフ）")
        else:
            self.watch.stop()
            self.unity = None
            self.normal_rect = None
            self.set_status("Unity未接続：Unityを起動すると自動で同期を始めます。")

    # ------------------------------------------------------------------ sync
    def start_sync(self):
        if self.watch.active:
            self.watch.resend_all()
        else:
            self.watch.start()
        self.set_status("自動同期中：メッシュの編集・移動・マテリアル変更をUnityへ送ります。")

    def auto_sync_toggled(self, checked):
        self.settings.setValue("auto_sync", checked)
        if checked and self.connected:
            self.start_sync()
        elif not checked:
            self.watch.stop()
            self.set_status("自動同期オフ" + ("（Unity接続中）" if self.connected else ""))

    def resend_all(self):
        if not self.connected:
            self.set_status("Unityが起動していません。")
        elif self.watch.active:
            self.watch.resend_all()
        else:
            self.flush(cmds.ls(type="mesh", long=True, noIntermediate=True) or [], [])

    def flush(self, paths, removed):
        """Called by SceneWatch on the main thread. False = busy, retry later."""
        if self.sending:
            return False
        if not self.connected:
            return True
        try:
            messages = [remove_message(name) for name in removed] + meshes_for(paths)
        except Exception as error:  # a broken mesh must not stop the sync
            self.set_status("メッシュ取得エラー: " + str(error))
            return True
        if not messages:
            return True
        self.sending = True
        names = ", ".join(path.split("|")[-1] for path in paths[:3]) + (" …" if len(paths) > 3 else "")
        future = self.executor.submit(send_messages, messages, self.cancelled)

        def completed(job):
            error = job.exception()
            self.send_finished.emit("送信失敗: " + str(error) if error else
                                    "同期: " + (names or "削除のみ"))
        future.add_done_callback(completed)
        return True

    def on_send_finished(self, message):
        self.sending = False
        self.set_status(message)

    # ------------------------------------------------------------------ Unity window (PiP)
    def attach_window(self):
        if not unity_window.IS_WINDOWS:
            return None
        if self.unity is None or not self.unity.alive():
            pid = self.process.pid if self.process is not None and self.process.poll() is None else None
            hwnd = unity_window.find_unity_window(pid=pid, exe_path=self.exe.text().strip().strip('"') or None)
            self.unity = unity_window.UnityWindow(hwnd) if hwnd else None
            if self.unity:
                self.unity.make_resizable()
                if self.pip.isChecked():
                    self.apply_pip(True)
        return self.unity

    def apply_pip(self, enabled):
        self.settings.setValue("pip", enabled)
        window = self.attach_window() if self.connected else None
        if window is None:
            return
        if enabled:
            if self.normal_rect is None:
                self.normal_rect = window.rect()
            saved = self.settings.value("pip_rect")
            rect = [int(v) for v in saved] if saved else window.default_pip_rect(int(self.maya_window.winId()))
            window.show()
            window.set_rect(rect)
            window.set_topmost(True)
            self.visibility.setText("Unityを隠す")
        else:
            self.settings.setValue("pip_rect", window.rect())
            window.set_topmost(False)
            if self.normal_rect:
                window.set_rect(self.normal_rect)
            self.normal_rect = None

    def toggle_unity_window(self):
        window = self.attach_window() if self.connected else None
        if window is None:
            self.set_status("Unityのウィンドウが見つかりません。")
            return
        if window.visible():
            window.hide()
            self.visibility.setText("Unityを表示")
        else:
            window.show()
            if self.pip.isChecked():
                window.set_topmost(True)
            self.visibility.setText("Unityを隠す")

    # ------------------------------------------------------------------ misc
    def set_status(self, text):
        self.status.setText(text)

    def shutdown(self):
        if self.closed:
            return
        self.closed = True
        self.monitor_stop.set()
        self.watch.stop()
        self.cancelled.set()
        if self.unity is not None and self.unity.alive():
            if self.pip.isChecked():
                self.settings.setValue("pip_rect", self.unity.rect())
            if not self.unity.visible():
                self.unity.show()   # never leave Unity hidden with no way back
        self.executor.shutdown(wait=False)

    def closeEvent(self, event):
        self.settings.setValue("exe", self.exe.text())
        self.shutdown()
        super().closeEvent(event)
