"""Dockable Maya panel. It only displays / edits the controller; closing it keeps syncing.

Dock it anywhere (e.g. as a tab next to the Attribute Editor) or close it; reopen from the
DCC Launcher menu. The sync list accepts objects dragged from the Outliner.
"""
import re

from maya import cmds
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

from .qt import QtCore, QtGui, QtWidgets


class DropList(QtWidgets.QListWidget):
    """List that accepts Outliner drags (node names arrive as text)."""
    nodes_dropped = QtCore.Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DropOnly)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)

    def dragEnterEvent(self, event):
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        text = event.mimeData().text() if event.mimeData().hasText() else ""
        names = [n for n in re.split(r"[\s,]+", text) if n and cmds.objExists(n)]
        if not names:   # Outliner drags select what they drag: fall back to the selection
            names = cmds.ls(selection=True, long=True, objectsOnly=True) or []
        event.acceptProposedAction()
        self.nodes_dropped.emit(names)


class PreviewPanel(MayaQWidgetDockableMixin, QtWidgets.QWidget):
    OBJECT_NAME = "MayaUnityPreviewPanel"

    def __init__(self, controller, parent=None):
        super().__init__(parent=parent)
        self.controller = controller
        self.setObjectName(self.OBJECT_NAME)
        self.setWindowTitle("Unity HDRP Preview")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Unity
        row = QtWidgets.QHBoxLayout()
        launch = QtWidgets.QPushButton("Unityを起動")
        launch.clicked.connect(controller.launch_unity)
        row.addWidget(launch)
        self.pip = QtWidgets.QCheckBox("PiP（常に手前）")
        self.pip.setChecked(controller.pip)
        self.pip.toggled.connect(controller.set_pip)
        row.addWidget(self.pip)
        self.visibility = QtWidgets.QPushButton("Unityを隠す")
        self.visibility.clicked.connect(controller.toggle_unity_window)
        row.addWidget(self.visibility)
        row.addStretch(1)
        self.settings_button = QtWidgets.QToolButton()
        self.settings_button.setText("設定")
        self.settings_button.setCheckable(True)
        row.addWidget(self.settings_button)
        layout.addLayout(row)

        # settings (folded by default)
        self.settings_box = QtWidgets.QWidget()
        box = QtWidgets.QVBoxLayout(self.settings_box)
        box.setContentsMargins(0, 0, 0, 0)
        row = QtWidgets.QHBoxLayout()
        self.exe = QtWidgets.QLineEdit(controller.exe_path)
        self.exe.setPlaceholderText("PreviewHost.exe のパス")
        self.exe.editingFinished.connect(lambda: setattr(controller, "exe_path", self.exe.text()))
        row.addWidget(self.exe, 1)
        browse = QtWidgets.QPushButton("参照")
        browse.clicked.connect(self.browse)
        row.addWidget(browse)
        box.addLayout(row)
        self.auto_sync = QtWidgets.QCheckBox("自動同期")
        self.auto_sync.setChecked(controller.auto_sync)
        self.auto_sync.toggled.connect(controller.set_auto_sync)
        box.addWidget(self.auto_sync)
        self.settings_box.setVisible(not controller.exe_path)
        self.settings_button.setChecked(self.settings_box.isVisible())
        self.settings_button.toggled.connect(self.settings_box.setVisible)
        layout.addWidget(self.settings_box)

        # sync list
        layout.addWidget(QtWidgets.QLabel("同期リスト（アウトライナーからドロップ）"))
        self.list = DropList()
        self.list.nodes_dropped.connect(controller.add_to_list)
        self.list.itemDoubleClicked.connect(self.select_in_maya)
        layout.addWidget(self.list, 1)
        row = QtWidgets.QHBoxLayout()
        for label, action in (("選択を追加", controller.add_selection),
                              ("削除", self.remove_selected),
                              ("クリア", controller.clear_list),
                              ("リストを再送信", controller.resend_list)):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(action)
            row.addWidget(button)
        layout.addLayout(row)

        self.status = QtWidgets.QLabel(controller.status)
        self.status.setWordWrap(True)
        self.status.setTextFormat(QtCore.Qt.PlainText)
        layout.addWidget(self.status)
        hint = QtWidgets.QLabel("Unityの窓は端をドラッグでサイズ変更 / Unity上でTab: UIの表示切替")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a8a8a;")
        layout.addWidget(hint)

        controller.status_changed.connect(self.status.setText)
        controller.list_changed.connect(self.refresh_list)
        controller.unity_visibility_changed.connect(self.update_visibility_button)
        self.refresh_list()
        self.resize(360, 420)

    # ------------------------------------------------------------------
    def browse(self):
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "PreviewHost.exeを選択", self.exe.text(), "Executable (*.exe)")
        if filename:
            self.exe.setText(filename)
            self.controller.exe_path = filename

    def refresh_list(self):
        self.list.clear()
        for uuid, name in self.controller.sync_list.items():
            item = QtWidgets.QListWidgetItem(name.split("|")[-1] if name else "（見つかりません）" + uuid)
            item.setData(QtCore.Qt.UserRole, uuid)
            item.setToolTip(name or uuid)
            if not name:
                item.setForeground(QtGui.QColor("#777777"))
            self.list.addItem(item)

    def remove_selected(self):
        uuids = [item.data(QtCore.Qt.UserRole) for item in self.list.selectedItems()]
        if uuids:
            self.controller.remove_from_list(uuids)

    def select_in_maya(self, item):
        names = cmds.ls(item.data(QtCore.Qt.UserRole), long=True) or []
        if names:
            cmds.select(names, replace=True)

    def update_visibility_button(self, visible):
        self.visibility.setText("Unityを隠す" if visible else "Unityを表示")
