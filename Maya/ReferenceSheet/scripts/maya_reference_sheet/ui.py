"""Dockable editor: up to 4 images (front / back / right / left) -> aligned reference planes."""
import os

from maya import cmds
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

from .qt import QtCore, QtGui, QtWidgets
from . import builder, layout
from .canvas import GuideCanvas, OverviewCanvas, dropped_image

DISPLAY_MAX = 1600          # longest side of the pixmap kept for display
DETECT_WIDTH = 256          # guides are detected on a small copy


def _rgba_bytes(image):
    """RGBA8888 bytes of a QImage for PySide6 and PySide2."""
    expected = image.width() * image.height() * 4
    try:
        data = bytes(image.constBits())
        if len(data) >= expected:
            return data[:expected]
    except (TypeError, ValueError):
        pass
    data = bytearray()
    for y in range(image.height()):
        for x in range(image.width()):
            argb = image.pixel(x, y)
            data += bytes(((argb >> 16) & 255, (argb >> 8) & 255, argb & 255, (argb >> 24) & 255))
    return bytes(data)


class SlotButton(QtWidgets.QToolButton):
    file_dropped = QtCore.Signal(str)

    def __init__(self, label, parent=None):
        super().__init__(parent)
        self.label = label
        self.setCheckable(True)
        self.setAcceptDrops(True)
        self.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        self.setIconSize(QtCore.QSize(64, 84))
        self.setMinimumWidth(78)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

    def dragEnterEvent(self, event):
        if dropped_image(event):
            event.acceptProposedAction()

    def dropEvent(self, event):
        path = dropped_image(event)
        if path:
            event.acceptProposedAction()
            self.file_dropped.emit(path)


class ReferenceSheetPanel(MayaQWidgetDockableMixin, QtWidgets.QWidget):
    OBJECT_NAME = "MayaReferenceSheetPanel"

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName(self.OBJECT_NAME)
        self.setWindowTitle("Reference Sheet（三面図）")
        self.config = builder.load_config()
        self.config.setdefault("views", {})
        self.pixmaps = {}
        self.current = "front"
        self.settings = QtCore.QSettings("DCCLauncher", "MayaReferenceSheet")

        layout_ = QtWidgets.QVBoxLayout(self)
        layout_.setContentsMargins(6, 6, 6, 6)
        layout_.setSpacing(6)

        # slots
        row = QtWidgets.QHBoxLayout()
        self.slot_group = QtWidgets.QButtonGroup(self)
        self.slot_group.setExclusive(True)
        self.slots = {}
        for view in layout.VIEWS:
            button = SlotButton(layout.LABELS[view])
            button.setToolTip(layout.HINTS[view] + "\n画像をドロップして設定できます")
            button.clicked.connect(lambda _=False, v=view: self.select(v))
            button.file_dropped.connect(lambda path, v=view: self.set_image(v, path))
            self.slot_group.addButton(button)
            self.slots[view] = button
            row.addWidget(button)
        layout_.addLayout(row)

        # current slot
        self.hint = QtWidgets.QLabel()
        self.hint.setStyleSheet("color:#9a9a9a;")
        self.hint.setWordWrap(True)
        layout_.addWidget(self.hint)
        row = QtWidgets.QHBoxLayout()
        self.path = QtWidgets.QLineEdit()
        self.path.setReadOnly(True)
        self.path.setPlaceholderText("画像なし")
        row.addWidget(self.path, 1)
        for label, action in (("参照", self.browse), ("クリア", self.clear_slot)):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(action)
            row.addWidget(button)
        layout_.addLayout(row)
        row = QtWidgets.QHBoxLayout()
        self.flip = QtWidgets.QCheckBox("左右反転")
        self.flip.toggled.connect(self.flip_toggled)
        row.addWidget(self.flip)
        detect = QtWidgets.QPushButton("ガイド自動検出")
        detect.clicked.connect(self.detect_current)
        row.addWidget(detect)
        row.addStretch(1)
        self.guide_info = QtWidgets.QLabel()
        self.guide_info.setStyleSheet("color:#9a9a9a;")
        row.addWidget(self.guide_info)
        layout_.addLayout(row)

        # editor / overview
        self.tabs = QtWidgets.QTabWidget()
        self.canvas = GuideCanvas()
        self.canvas.guides_changed.connect(self.guides_edited)
        self.canvas.file_dropped.connect(lambda path: self.set_image(self.current, path))
        self.overview = OverviewCanvas()
        self.tabs.addTab(self.canvas, "ガイド調整")
        self.tabs.addTab(self.overview, "並べて確認")
        layout_.addWidget(self.tabs, 1)

        # settings
        form = QtWidgets.QFormLayout()
        unit = builder.unit_label()
        self.height_box = self._spin(self.config["height"], unit)
        self.height_box.setToolTip("頭頂ガイド〜足元ガイドの高さ（全画像この高さに揃えます）")
        form.addRow("身長（ガイド間）", self.height_box)
        self.distance_box = self._spin(self.config["distance"], unit)
        self.distance_box.setToolTip("原点から板までの距離。モデルより後ろに来るように")
        form.addRow("板までの距離", self.distance_box)
        row = QtWidgets.QHBoxLayout()
        self.opacity = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.opacity.setRange(5, 100)
        self.opacity.setValue(int(round(self.config.get("opacity", 1.0) * 100)))
        self.opacity_label = QtWidgets.QLabel()
        row.addWidget(self.opacity, 1)
        row.addWidget(self.opacity_label)
        form.addRow("不透明度", row)
        self.reference = QtWidgets.QCheckBox("板を選択できないようにする（Reference レイヤー）")
        self.reference.setChecked(self.config.get("reference", True))
        form.addRow(self.reference)
        self.textures = QtWidgets.QCheckBox("ビューポートのテクスチャ表示をオンにする")
        self.textures.setChecked(self.config.get("textures", True))
        form.addRow(self.textures)
        layout_.addLayout(form)
        for widget, signal in ((self.height_box, "valueChanged"), (self.distance_box, "valueChanged"),
                               (self.opacity, "valueChanged"), (self.reference, "toggled"),
                               (self.textures, "toggled")):
            getattr(widget, signal).connect(self.settings_changed)

        row = QtWidgets.QHBoxLayout()
        build = QtWidgets.QPushButton("三面図を作成・更新")
        build.setMinimumHeight(30)
        build.clicked.connect(self.build)
        row.addWidget(build, 1)
        remove = QtWidgets.QPushButton("削除")
        remove.clicked.connect(self.remove)
        row.addWidget(remove)
        layout_.addLayout(row)
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        layout_.addWidget(self.status)

        for view in layout.VIEWS:
            self._load_pixmap(view)
        self.settings_changed(save=False)
        self.select("front")
        self.resize(420, 760)

    @staticmethod
    def _spin(value, unit):
        box = QtWidgets.QDoubleSpinBox()
        box.setRange(0.001, 100000.0)
        box.setDecimals(3)
        box.setSingleStep(1.0)
        box.setSuffix(" " + unit)
        box.setValue(float(value))
        return box

    # ------------------------------------------------------------------ slots
    def entry(self, view=None):
        return self.config["views"].get(view or self.current)

    def select(self, view):
        self.current = view
        self.slots[view].setChecked(True)
        entry = self.entry() or {}
        self.hint.setText("{}: {}".format(layout.LABELS[view], layout.HINTS[view]))
        self.path.setText(entry.get("path", ""))
        self.flip.blockSignals(True)
        self.flip.setChecked(bool(entry.get("flip")))
        self.flip.blockSignals(False)
        self.canvas.set_image(self.pixmaps.get(view), entry.get("size"), entry.get("guides"))
        self.refresh()

    def browse(self):
        start = os.path.dirname((self.entry() or {}).get("path", "")) or self.settings.value("folder", "")
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, layout.LABELS[self.current] + "の画像", start, "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.tga)")
        if filename:
            self.set_image(self.current, filename)

    def set_image(self, view, path):
        reader = QtGui.QImageReader(path)
        size = reader.size()
        if not reader.canRead() or not size.isValid():
            self.status.setText("読み込めない画像です: " + path)
            return
        self.settings.setValue("folder", os.path.dirname(path))
        entry = {"path": path.replace("\\", "/"), "size": [size.width(), size.height()], "flip": False,
                 "guides": layout.default_guides(size.width(), size.height())}
        self.config["views"][view] = entry
        self._load_pixmap(view)
        self._detect(view)
        self.save()
        self.select(view)
        self.status.setText("{}: 画像を設定し、ガイドを自動検出しました。線をドラッグで調整できます。".format(layout.LABELS[view]))

    def clear_slot(self):
        self.config["views"].pop(self.current, None)
        self.pixmaps.pop(self.current, None)
        self.save()
        self.select(self.current)

    def flip_toggled(self, checked):
        entry = self.entry()
        if entry:
            entry["flip"] = checked
            self.save()
            self.refresh()

    def detect_current(self):
        if self.entry():
            self._detect(self.current)
            self.save()
            self.select(self.current)

    def guides_edited(self, guides):
        entry = self.entry()
        if entry:
            entry["guides"] = guides
            self.save()
            self.refresh()

    # ------------------------------------------------------------------ images
    def _load_pixmap(self, view):
        entry = self.entry(view)
        if not entry or not os.path.isfile(entry.get("path", "")):
            self.pixmaps.pop(view, None)
            return
        image = QtGui.QImage(entry["path"])
        if image.isNull():
            self.pixmaps.pop(view, None)
            return
        entry["size"] = [image.width(), image.height()]
        if max(image.width(), image.height()) > DISPLAY_MAX:
            image = image.scaled(DISPLAY_MAX, DISPLAY_MAX, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self.pixmaps[view] = QtGui.QPixmap.fromImage(image)

    def _detect(self, view):
        entry = self.entry(view)
        image = QtGui.QImage(entry["path"])
        if image.isNull():
            return
        small = image.scaledToWidth(min(DETECT_WIDTH, image.width()), QtCore.Qt.SmoothTransformation)
        small = small.convertToFormat(QtGui.QImage.Format_RGBA8888)
        guides = layout.detect_guides(small.width(), small.height(), _rgba_bytes(small))
        entry["guides"] = {k: round(v, 1) for k, v in
                           layout.scale_guides(guides, image.width() / float(small.width())).items()}

    # ------------------------------------------------------------------ settings / state
    def settings_changed(self, *_args, save=True):
        self.config["height"] = self.height_box.value()
        self.config["distance"] = self.distance_box.value()
        self.config["opacity"] = self.opacity.value() / 100.0
        self.config["reference"] = self.reference.isChecked()
        self.config["textures"] = self.textures.isChecked()
        self.opacity_label.setText("{:.2f}".format(self.config["opacity"]))
        if save:
            self.save()

    def save(self):
        builder.save_config(self.config)

    def refresh(self):
        for view, button in self.slots.items():
            pixmap = self.pixmaps.get(view)
            button.setIcon(QtGui.QIcon(pixmap) if pixmap else QtGui.QIcon())
            button.setText(layout.LABELS[view] + ("" if pixmap else "\n（なし）"))
        entry = self.entry()
        if entry and entry.get("guides"):
            g = entry["guides"]
            self.guide_info.setText("頭頂 {:.0f} / 足元 {:.0f} / 中心 {:.0f} px".format(g["top"], g["bottom"], g["center"]))
        else:
            self.guide_info.setText("")
        items = []
        for view in layout.VIEWS:
            entry = self.entry(view)
            if entry and view in self.pixmaps and entry.get("guides"):
                # original pixel guides + original size; the (maybe smaller) pixmap is scaled into place
                items.append((layout.LABELS[view], self.pixmaps[view], entry["size"], entry["guides"],
                              entry.get("flip", False)))
        self.overview.set_items(items)

    # ------------------------------------------------------------------ build
    def build(self):
        self.settings_changed()
        if not any(self.entry(v) for v in layout.VIEWS):
            self.status.setText("画像を1枚以上設定してください。")
            return
        try:
            created, warnings = builder.build(self.config)
        except RuntimeError as error:
            self.status.setText("作成エラー: " + str(error))
            return
        message = "作成: " + ", ".join(created) if created else "作成できる板がありません。"
        self.status.setText(message + ("\n" + "\n".join(warnings) if warnings else ""))

    def remove(self):
        builder.remove()
        self.status.setText("三面図を削除しました（画像の設定は残っています）。")
