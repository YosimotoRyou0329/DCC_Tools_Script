"""Use the Qt binding bundled with Maya (Qt6 in 2025+, Qt5 in 2024)."""
try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance
