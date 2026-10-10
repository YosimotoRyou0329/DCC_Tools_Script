"""Qt widgets: guide editor for one image, and an aligned overview of every image."""
from .qt import QtCore, QtGui, QtWidgets

GUIDE_KEYS = ("top", "bottom", "center")
GUIDE_COLORS = {"top": "#ff6b6b", "bottom": "#62e27a", "center": "#4fd3ff"}
GUIDE_NAMES = {"top": "頭頂", "bottom": "足元", "center": "中心"}
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


class GuideCanvas(QtWidgets.QWidget):
    """Shows one image (never stretched) with draggable head / feet / centre guides."""
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
        self.drag = None
        self.hover = None

    def set_image(self, pixmap, image_size, guides):
        self.pixmap = pixmap
        self.image_size = tuple(image_size or (0, 0))
        self.guides = dict(guides) if guides else None
        self.drag = self.hover = None
        self.update()

    # ------------------------------------------------------------------ geometry
    def _fit(self):
        width, height = self.image_size
        if not width or not height:
            return None
        area = QtCore.QRectF(self.rect()).adjusted(10, 10, -10, -10)
        scale = min(area.width() / width, area.height() / height)
        return scale, area.x() + (area.width() - width * scale) / 2, area.y() + (area.height() - height * scale) / 2

    def _hit(self, pos):
        fit = self._fit()
        if not fit or not self.guides:
            return None
        scale, ox, oy = fit
        best, best_distance = None, PICK_DISTANCE
        for key in GUIDE_KEYS:
            value = self.guides[key] * scale
            distance = abs(pos.x() - (ox + value)) if key == "center" else abs(pos.y() - (oy + value))
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
        for key in GUIDE_KEYS:
            active = key in (self.drag, self.hover)
            pen = QtGui.QPen(QtGui.QColor(GUIDE_COLORS[key]), 3 if active else 1.5)
            painter.setPen(pen)
            value = self.guides[key] * scale
            if key == "center":
                x = ox + value
                painter.drawLine(QtCore.QPointF(x, oy), QtCore.QPointF(x, oy + height * scale))
                painter.drawText(QtCore.QPointF(x + 4, oy + 14), GUIDE_NAMES[key])
            else:
                y = oy + value
                painter.drawLine(QtCore.QPointF(ox, y), QtCore.QPointF(ox + width * scale, y))
                painter.drawText(QtCore.QPointF(ox + 4, y - 4), GUIDE_NAMES[key])

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
                else:
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
    """Every image scaled by its guides: heads and feet line up when the guides are right."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 280)
        self.items = []          # (label, pixmap, (w, h), guides, flip)
        self._mirrored = {}

    def set_items(self, items):
        self.items = items
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
        span = feet_y - head_y
        for index, (label, pixmap, size, guides, flip) in enumerate(self.items):
            width, height = size
            scale = span / max(1.0, guides["bottom"] - guides["top"])
            center = width - guides["center"] if flip else guides["center"]
            cx = column * index + column / 2
            target = QtCore.QRectF(cx - center * scale, feet_y - guides["bottom"] * scale, width * scale, height * scale)
            if flip:
                if index not in self._mirrored:
                    self._mirrored[index] = pixmap.transformed(QtGui.QTransform().scale(-1, 1))
                pixmap = self._mirrored[index]
            painter.save()
            painter.setClipRect(QtCore.QRectF(column * index, 0, column, self.height()))
            painter.drawPixmap(target, pixmap, QtCore.QRectF(pixmap.rect()))
            painter.setPen(QtGui.QPen(QtGui.QColor(GUIDE_COLORS["center"]), 1, QtCore.Qt.DashLine))
            painter.drawLine(QtCore.QPointF(cx, head_y), QtCore.QPointF(cx, feet_y))
            painter.restore()
            painter.setPen(QtGui.QColor("#dddddd"))
            painter.drawText(QtCore.QRectF(column * index, 4, column, 20), QtCore.Qt.AlignCenter, label)
        for key, y in (("top", head_y), ("bottom", feet_y)):
            painter.setPen(QtGui.QPen(QtGui.QColor(GUIDE_COLORS[key]), 1.5))
            painter.drawLine(QtCore.QPointF(0, y), QtCore.QPointF(self.width(), y))
