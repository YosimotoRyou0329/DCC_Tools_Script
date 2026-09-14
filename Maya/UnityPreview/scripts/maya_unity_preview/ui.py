"""Maya-owned GUI and lifecycle coordination."""
import subprocess
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from .qt import QtCore, QtGui, QtWidgets, wrapInstance
from maya import OpenMayaUI

from .transport import FrameReceiver, send_meshes
from .mesh import selected_meshes
from .live_sync import LiveSync


class PreviewTool(QtWidgets.QDialog):
    frame_received = QtCore.Signal(int, int, bytes)
    error_received = QtCore.Signal(str)
    sync_requested = QtCore.Signal()
    send_finished = QtCore.Signal(str)

    def __init__(self):
        parent = wrapInstance(int(OpenMayaUI.MQtUtil.mainWindow()), QtWidgets.QWidget)
        super().__init__(parent)
        self.setWindowTitle("Maya Unity HDRP Preview")
        self.resize(850, 600)
        self.receiver = None
        self.executor = None
        self.sending = False
        self.generation = 0
        self.cancelled = threading.Event()
        self.process = None
        self.pixmap = None
        self.settings = QtCore.QSettings("DCCLauncher", "MayaUnityPreview")
        self.live = LiveSync(self.sync_requested.emit, self)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("Unity PreviewHost.exe パス"))
        row = QtWidgets.QHBoxLayout()
        self.exe = QtWidgets.QLineEdit(self.settings.value("exe", ""))
        row.addWidget(self.exe, 1)
        browse = QtWidgets.QPushButton("参照")
        browse.clicked.connect(self.browse)
        row.addWidget(browse)
        launch = QtWidgets.QPushButton("Unityを起動")
        launch.clicked.connect(self.launch_host)
        row.addWidget(launch)
        layout.addLayout(row)
        row = QtWidgets.QHBoxLayout()
        for label, action in (("HDRP Preview 起動", self.start_preview),
                              ("Live Sync 起動", self.start_live),
                              ("選択メッシュを送信", self.request_manual),
                              ("停止", self.stop)):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(action)
            row.addWidget(button)
        layout.addLayout(row)
        self.status = QtWidgets.QLabel("停止中")
        self.status.setWordWrap(True)
        self.status.setTextFormat(QtCore.Qt.PlainText)
        layout.addWidget(self.status)
        self.preview = QtWidgets.QLabel("Previewを起動してUnityへメッシュを送ると、HDRP画像が表示されます。")
        self.preview.setAlignment(QtCore.Qt.AlignCenter)
        self.preview.setMinimumSize(320, 180)
        self.preview.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Expanding)
        self.preview.setStyleSheet("background:#202020;color:#cccccc;")
        layout.addWidget(self.preview, 1)
        layout.addWidget(QtWidgets.QLabel("選択メッシュを同期 / 左ボタンのドラッグ終了時のみ / Scale 1:1 / TCP 50001・50002"))
        self.frame_received.connect(self.display_frame, QtCore.Qt.QueuedConnection)
        self.error_received.connect(self.status.setText, QtCore.Qt.QueuedConnection)
        self.sync_requested.connect(self.send_selection, QtCore.Qt.QueuedConnection)
        self.send_finished.connect(self.sent, QtCore.Qt.QueuedConnection)
        QtWidgets.QApplication.instance().aboutToQuit.connect(self.stop)

    def browse(self):
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(self, "PreviewHost.exeを選択", self.exe.text(), "Executable (*.exe)")
        if filename:
            self.exe.setText(filename)
            self.settings.setValue("exe", filename)

    def launch_host(self):
        path = Path(self.exe.text().strip().strip('"'))
        if not path.is_file() or path.suffix.lower() != ".exe":
            self.status.setText("PreviewHostの.exeファイルを指定してください。")
            return
        if self.process is not None and self.process.poll() is None:
            self.status.setText("このツールから起動したUnityは実行中です。")
            return
        if not self.start_preview():
            return
        try:
            self.process = subprocess.Popen([str(path)], cwd=str(path.parent))
            self.settings.setValue("exe", str(path))
            self.status.setText("Unityを起動しました。表示後にLive Syncを起動してください。")
        except OSError as error:
            self.status.setText(str(error))

    def start_preview(self):
        if self.receiver:
            return True
        receiver = FrameReceiver(self.frame_received.emit, self.error_received.emit)
        try:
            receiver.start()
        except OSError as error:
            self.status.setText("Preview受信を開始できません: " + str(error))
            return False
        self.receiver = receiver
        self.status.setText("Preview受信待機中（127.0.0.1:50002）")
        return True

    def start_live(self):
        if self.start_preview():
            self.live.start()
            self.status.setText("Live Sync中：選択メッシュをViewportの左Mouse Up時に同期します。")

    def request_manual(self):
        if self.start_preview():
            self.send_selection(manual=True)

    def send_selection(self, manual=False):
        if not manual and (not self.live.active or self.live.pressed):
            return
        if self.sending:
            self.status.setText("前回の送信中です。完了後に再操作または手動送信してください。")
            return
        try:
            meshes = selected_meshes()
            if not meshes:
                self.status.setText("送信するポリゴンメッシュを選択してください。")
                return
            if self.executor is None:
                self.cancelled = threading.Event()
                self.executor = ThreadPoolExecutor(max_workers=1)
            self.sending = True
            generation = self.generation
            future = self.executor.submit(send_meshes, meshes, self.cancelled)

            def completed(job):
                error = job.exception()
                if generation == self.generation:
                    self.send_finished.emit("送信失敗: " + str(error) if error else "送信完了：HDRPフレーム待機中")
            future.add_done_callback(completed)
        except Exception as error:
            self.sending = False
            self.status.setText(str(error))

    def sent(self, message):
        self.sending = False
        self.status.setText(message)

    def display_frame(self, width, height, data):
        if not self.receiver:
            return
        image = QtGui.QImage(data, width, height, width * 4, QtGui.QImage.Format_RGBA8888).copy()
        self.pixmap = QtGui.QPixmap.fromImage(image.mirrored(False, True))
        self.update_image()
        self.status.setText("HDRP Frame受信: {} × {}".format(width, height))

    def update_image(self):
        if self.pixmap:
            self.preview.setPixmap(self.pixmap.scaled(self.preview.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_image()

    def stop(self):
        self.live.stop()
        self.generation += 1
        self.cancelled.set()
        if self.receiver:
            self.receiver.stop()
            self.receiver = None
        if self.executor:
            self.executor.shutdown(wait=False)
            self.executor = None
        self.sending = False
        self.status.setText("停止中（UnityのウィンドウはUnity側で終了できます）")

    def closeEvent(self, event):
        self.stop()
        self.settings.setValue("exe", self.exe.text())
        super().closeEvent(event)
