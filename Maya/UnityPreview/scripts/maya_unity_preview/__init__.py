"""Public launcher entry point. Maya imports are deferred until show()."""
_window = None


def show():
    global _window
    from .ui import PreviewTool
    if _window is None:
        _window = PreviewTool()
    _window.show()
    _window.raise_()
    _window.activateWindow()
