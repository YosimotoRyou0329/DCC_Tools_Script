"""Dockable Maya panel. It only displays / edits the controller; closing it keeps syncing.

Dock it anywhere (e.g. as a tab next to the Attribute Editor) or close it; reopen from the
DCC Launcher menu. The sync list accepts objects dragged from the Outliner.
"""
import re

from maya import cmds
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

from .qt import QtCore, QtGui, QtWidgets
from .material import state as material_state


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


class MaterialEditor(QtWidgets.QGroupBox):
    """Make / edit materials in Maya; Unity builds them from the chosen shader (template).

    Base colour and normal map are real Maya file nodes (see UVs and placement in the Maya
    viewport). Other Unity texture slots of the template are stored on the Maya material.
    """
    NO_TEMPLATE = "（Unityの同名マテリアル / 無ければ HDRP/Lit）"
    SLOT_FILTER = "Images (*.png *.jpg *.jpeg)"

    def __init__(self, controller, parent=None):
        super().__init__("マテリアル", parent)
        self.controller = controller
        self.updating = False
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        row = QtWidgets.QHBoxLayout()
        self.materials = QtWidgets.QComboBox()
        self.materials.currentIndexChanged.connect(self.load_material)
        row.addWidget(self.materials, 1)
        refresh = QtWidgets.QPushButton("更新")
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)
        create = QtWidgets.QPushButton("新規")
        create.setToolTip("選択中のオブジェクト / フェースに新しいマテリアルを作って割り当てます")
        create.clicked.connect(self.create)
        row.addWidget(create)
        layout.addLayout(row)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Unityシェーダー"))
        self.templates = QtWidgets.QComboBox()
        self.templates.currentIndexChanged.connect(self.template_chosen)
        row.addWidget(self.templates, 1)
        layout.addLayout(row)

        self.slots = QtWidgets.QFormLayout()
        self.slots.setLabelAlignment(QtCore.Qt.AlignRight)
        layout.addLayout(self.slots)
        note = QtWidgets.QLabel("ベースカラー / ノーマルはMayaのfileノードとして接続（MayaでUV・貼り具合を確認）。"
                                "テクスチャを上書き保存するとMaya・Unityとも自動で更新。PNG / JPG対応。")
        note.setWordWrap(True)
        note.setStyleSheet("color:#8a8a8a;")
        layout.addWidget(note)

        controller.templates_changed.connect(self.fill_templates)
        controller.list_changed.connect(self.refresh)
        self.fill_templates()
        self.refresh()

    # ------------------------------------------------------------------
    def current_material(self):
        material = self.materials.currentData()
        return material if material and cmds.objExists(material) else None

    def refresh(self):
        selected = self.materials.currentData()
        self.updating = True
        self.materials.clear()
        for material in self.controller.materials_in_list():
            self.materials.addItem(material, material)
        index = self.materials.findData(selected)
        self.materials.setCurrentIndex(index if index >= 0 else 0)
        self.updating = False
        self.load_material()

    def fill_templates(self):
        self.updating = True
        current = self.templates.currentData()
        self.templates.clear()
        self.templates.addItem(self.NO_TEMPLATE, "")
        for template in self.controller.templates:
            self.templates.addItem(template["name"], template["name"])
        index = self.templates.findData(current)
        self.templates.setCurrentIndex(max(0, index))
        self.updating = False
        self.load_material()

    def load_material(self, *_):
        if self.updating:
            return
        material = self.current_material()
        state = material_state(material) if material else None
        self.updating = True
        if state:
            index = self.templates.findData(state["template"])
            if index < 0 and state["template"]:
                self.templates.addItem(state["template"] + "（Unity未接続/不明）", state["template"])
                index = self.templates.count() - 1
            self.templates.setCurrentIndex(max(0, index))
        self.updating = False
        self.build_slots(material, state)

    def build_slots(self, material, state):
        while self.slots.rowCount():
            self.slots.removeRow(0)
        if not material:
            self.slots.addRow(QtWidgets.QLabel("同期リストのオブジェクトにマテリアルがありません。"))
            return
        template = self.controller.template(state["template"]) if state["template"] else None
        rows = [("ベースカラー", "@base", state["base"]), ("ノーマル", "@normal", state["normal"])]
        skip = {template.get("baseProp"), template.get("normalProp")} if template else set()
        for slot in (template or {}).get("textures", []):
            if slot["prop"] not in skip:
                rows.append((slot.get("label") or slot["prop"], slot["prop"], state["extras"].get(slot["prop"], "")))
        for prop, path in state["extras"].items():   # slots kept on the material but unknown to the template
            if all(prop != r[1] for r in rows):
                rows.append((prop, prop, path))
        for label, slot, path in rows:
            self.slots.addRow(label, self.slot_row(material, slot, path))

    def slot_row(self, material, slot, path):
        widget = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        field = QtWidgets.QLineEdit(path)
        field.setPlaceholderText("なし")
        field.editingFinished.connect(lambda: self.apply(material, slot, field.text().strip()))
        row.addWidget(field, 1)
        browse = QtWidgets.QPushButton("参照")
        browse.clicked.connect(lambda: self.browse(material, slot, field))
        row.addWidget(browse)
        clear = QtWidgets.QPushButton("×")
        clear.setFixedWidth(24)
        clear.clicked.connect(lambda: (field.setText(""), self.apply(material, slot, "")))
        row.addWidget(clear)
        return widget

    def browse(self, material, slot, field):
        start = field.text() or cmds.workspace(query=True, rootDirectory=True)
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(self, "テクスチャを選択", start, self.SLOT_FILTER)
        if filename:
            field.setText(filename)
            self.apply(material, slot, filename)

    def apply(self, material, slot, path):
        if not cmds.objExists(material):
            return
        try:
            self.controller.set_texture(material, slot, path)
        except RuntimeError as error:
            cmds.warning(str(error))

    def template_chosen(self, *_):
        if self.updating:
            return
        material = self.current_material()
        if material:
            self.controller.set_template(material, self.templates.currentData() or "")
            self.build_slots(material, material_state(material))

    def create(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "新規マテリアル", "マテリアル名", text="MT_New")
        if not ok or not name.strip():
            return
        material = self.controller.create_material(name.strip(), self.templates.currentData() or "")
        self.refresh()
        index = self.materials.findData(material)
        if index < 0:
            self.materials.addItem(material, material)
            index = self.materials.count() - 1
        self.materials.setCurrentIndex(index)


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

        layout.addWidget(MaterialEditor(controller))

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
        self.resize(380, 640)

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
