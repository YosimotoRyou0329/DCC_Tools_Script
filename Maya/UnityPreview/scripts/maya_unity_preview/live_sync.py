"""Viewport mouse events only. No timer, idle callback or mesh polling."""
from .qt import QtCore, QtWidgets, wrapInstance
from maya import cmds, OpenMayaUI


class LiveSync(QtCore.QObject):
    def __init__(self, callback, parent):
        super().__init__(parent)
        self.callback = callback
        self.pressed = False
        self.active = False

    def start(self):
        if not self.active:
            QtWidgets.QApplication.instance().installEventFilter(self)
            self.active = True

    def stop(self):
        QtWidgets.QApplication.instance().removeEventFilter(self)
        self.active = False
        self.pressed = False

    def in_viewport(self, target):
        if not isinstance(target, QtWidgets.QWidget):
            return False
        for panel in cmds.getPanel(type="modelPanel") or []:
            control = cmds.modelPanel(panel, query=True, control=True)
            pointer = OpenMayaUI.MQtUtil.findControl(control) if control else None
            if pointer:
                widget = wrapInstance(int(pointer), QtWidgets.QWidget)
                if widget == target or widget.isAncestorOf(target):
                    return True
        return False

    def eventFilter(self, target, event):
        if event.type() == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.LeftButton:
            self.pressed = self.in_viewport(target)
        elif event.type() == QtCore.QEvent.MouseButtonRelease and event.button() == QtCore.Qt.LeftButton:
            if self.pressed:
                self.pressed = False
                # Queued invocation lets Maya finish its release handler first.
                self.callback()
        elif event.type() == QtCore.QEvent.ApplicationDeactivate:
            self.pressed = False
        return False
