"""Qt widgets: guide editor for one image, and an aligned overview of every image."""
from .qt import QtCore, QtGui, QtWidgets

BUILTIN_COLORS = {"top": "#ff6b6b", "bottom": "#62e27a", "center": "#4fd3ff"}
PICK_DISTANCE = 8
IMAGE_FILTER = ("png", "jpg", "jpeg", "bmp", "tif", "tiff", "tga")


def event_pos(event):
    return event.position() if hasattr(event, "position") else QtCore.QPointF(event.pos())


def dropped_image(event):
    """Local image file from a drag (Explorer etc.), or None."""
    mime = event.mimeData()
    for url in mime.urls() if mime.hasUrls() else []:
        path = url.toLocalFile()
        if path and path.lower().rsplit(".", 1)[-1] in IMAGE_FILTER:
            return path
    return None


def landmark_color(landmark):
    return QtGui.QColor(BUILTIN_COLORS.get(landmark["key"]) or landmark.get("color") or "#ffd166")


class GuideCanvas(QtWidgets.QWidget):
    """One image (never stretched) with draggable horizontal guides (head, feet, landmarks)
    and the vertical centre guide. Dashed lines show where the master image's landmarks land
    on this image after alignment: the gap is the remaining mismatch."""
    guides_changed = QtCore.Signal(dict)     # emitted when a drag ends
    file_dropped = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 280)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.pixmap = None
        self.image_size = (0, 0)
        self.guides = None
        self.expected = {}
        self.landmarks = []
        self.drag = None
        self.hover = None

    def set_landmarks(self, landmarks):
        self.landmarks = list(landmarks)
        self.update()

    def set_image(self, pixmap, image_size, guides, expected=None):
        self.pixmap = pixmap
        self.image_size = tuple(image_size or (0, 0))
        self.guides = dict(guides) if guides else None
        self.expected = dict(expected or {})
        self.drag = self.hover = None
        self.update()

    def set_expected(self, expected):
        self.expected = dict(expected or {})
        self.update()

    # ------------------------------------------------------------------ geometry
    def _fit(self):
        width, height = self.image_size
        if not width or not height:
            return None
        area = QtCore.QRectF(self.rect()).adjusted(10, 10, -10, -10)
        scale = min(area.width() / width, area.height() / height)
        return scale, area.x() + (area.width() - width * scale) / 2, area.y() + (area.height() - height * scale) / 2

    def _horizontal(self):
        return [l for l in self.landmarks if self.guides and l["key"] in self.guides]

    def _hit(self, pos):
        fit = self._fit()
        if not fit or not self.guides:
            return None
        scale, ox, oy = fit
        best, best_distance = None, PICK_DISTANCE
        candidates = [(l["key"], False) for l in self._horizontal()] + [("center", True)]
        for key, vertical in candidates:
            value = self.guides[key] * scale
            distance = abs(pos.x() - (ox + value)) if vertical else abs(pos.y() - (oy + value))
            if distance <= best_distance:
                best, best_distance = key, distance
        return best

    # ------------------------------------------------------------------ painting
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor("#262626"))
        fit = self._fit()
        if self.pixmap is None or fit is None:
            painter.setPen(QtGui.QColor("#8a8a8a"))
            painter.drawText(self.rect(), QtCore.Qt.AlignCenter, "画像をここにドロップ\nまたは「参照」")
            return
        scale, ox, oy = fit
        width, height = self.image_size
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        painter.drawPixmap(QtCore.QRectF(ox, oy, width * scale, height * scale), self.pixmap,
                           QtCore.QRectF(self.pixmap.rect()))
        if not self.guides:
            return
        right = ox + width * scale
        for landmark in self._horizontal():
            key = landmark["key"]
            color = landmark_color(landmark)
            if key in self.expected:            # master's landmark on this image (after alignment)
                pen = QtGui.QPen(color, 1.2, QtCore.Qt.DashLine)
                painter.setPen(pen)
                y = oy + self.expected[key] * scale
                painter.drawLine(QtCore.QPointF(ox, y), QtCore.QPointF(right, y))
            active = key in (self.drag, self.hover)
            painter.setPen(QtGui.QPen(color, 3 if active else 1.5))
            y = oy + self.guides[key] * scale
            painter.drawLine(QtCore.QPointF(ox, y), QtCore.QPointF(right, y))
            painter.drawText(QtCore.QPointF(ox + 4, y - 4), landmark["name"])
        active = "center" in (self.drag, self.hover)
        painter.setPen(QtGui.QPen(QtGui.QColor(BUILTIN_COLORS["center"]), 3 if active else 1.5))
        x = ox + self.guides["center"] * scale
        painter.drawLine(QtCore.QPointF(x, oy), QtCore.QPointF(x, oy + height * scale))
        painter.drawText(QtCore.QPointF(x + 4, oy + 14), "中心")

    # ------------------------------------------------------------------ mouse
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.drag = self._hit(event_pos(event))

    def mouseMoveEvent(self, event):
        pos = event_pos(event)
        fit = self._fit()
        if self.drag and fit:
            scale, ox, oy = fit
            width, height = self.image_size
            if self.drag == "center":
                value = min(max((pos.x() - ox) / scale, 0.0), float(width))
            else:
                value = min(max((pos.y() - oy) / scale, 0.0), float(height))
                if self.drag == "top":
                    value = min(value, self.guides["bottom"] - 1)
                elif self.drag == "bottom":
                    value = max(value, self.guides["top"] + 1)
            self.guides[self.drag] = round(value, 1)
            self.update()
            return
        hover = self._hit(pos)
        if hover != self.hover:
            self.hover = hover
            if hover == "center":
                self.setCursor(QtCore.Qt.SizeHorCursor)
            elif hover:
                self.setCursor(QtCore.Qt.SizeVerCursor)
            else:
                self.unsetCursor()
            self.update()

    def mouseReleaseEvent(self, event):
        if self.drag:
            self.drag = None
            self.guides_changed.emit(dict(self.guides))
            self.update()

    # ------------------------------------------------------------------ drop
    def dragEnterEvent(self, event):
        if dropped_image(event):
            event.acceptProposedAction()

    def dropEvent(self, event):
        path = dropped_image(event)
        if path:
            event.acceptProposedAction()
            self.file_dropped.emit(path)


class OverviewCanvas(QtWidgets.QWidget):
    """Every image placed exactly as it will be in Maya (same world scale, aligned on the
    checked landmarks), with the landmark heights drawn across all of them."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 280)
        self.items = []          # (label, pixmap, (w, h), guides, flip, fit)
        self.lines = []          # (name, world height, QColor)
        self.height_value = 1.0
        self._mirrored = {}

    def set_items(self, items, lines, height):
        self.items = items
        self.lines = lines
        self.height_value = max(1e-6, float(height))
        self._mirrored = {}
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor("#262626"))
        if not self.items:
            painter.setPen(QtGui.QColor("#8a8a8a"))
            painter.drawText(self.rect(), QtCore.Qt.AlignCenter, "画像を設定すると、ここで揃い具合を確認できます")
            return
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        column = self.width() / float(len(self.items))
        head_y = 28.0
        feet_y = self.height() - 16.0
        units = (feet_y - head_y) / self.height_value          # screen pixels per world unit
        for index, (label, pixmap, size, guides, flip, fit) in enumerate(self.items):
            width, height = size
            k = fit["scale"] * units                            # screen pixels per image pixel
            center = width - guides["center"] if flip else guides["center"]
            cx = column * index + column / 2
            target = QtCore.QRectF(cx - center * k, feet_y - fit["origin"] * units, width * k, height * k)
            if flip:
                if index not in self._mirrored:
                    self._mirrored[index] = pixmap.transformed(QtGui.QTransform().scale(-1, 1))
                pixmap = self._mirrored[index]
            painter.save()
            painter.setClipRect(QtCore.QRectF(column * index, 0, column, self.height()))
            painter.drawPixmap(target, pixmap, QtCore.QRectF(pixmap.rect()))
            painter.setPen(QtGui.QPen(QtGui.QColor(BUILTIN_COLORS["center"]), 1, QtCore.Qt.DashLine))
            painter.drawLine(QtCore.QPointF(cx, 0), QtCore.QPointF(cx, self.height()))
            painter.restore()
            painter.setPen(QtGui.QColor("#dddddd"))
            painter.drawText(QtCore.QRectF(column * index, 4, column, 20), QtCore.Qt.AlignCenter, label)
        for name, world, color in self.lines:
            y = feet_y - world * units
            painter.setPen(QtGui.QPen(color, 1.5))
            painter.drawLine(QtCore.QPointF(0, y), QtCore.QPointF(self.width(), y))
            painter.drawText(QtCore.QPointF(4, y - 3), name)
