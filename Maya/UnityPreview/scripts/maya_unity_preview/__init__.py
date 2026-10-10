"""Public launcher entry point. Maya imports are deferred until show()."""
_window = None


def show():
    global _window
    from .ui import PreviewTool
    if _window is None or _window.closed:
        _window = PreviewTool()
    _window.show()
    _window.raise_()
    _window.activateWindow()


def toggle_unity_window():
    """Hide / show the Unity preview window (assign this to a Maya hotkey or shelf button)."""
    if _window is not None and not _window.closed:
        _window.toggle_unity_window()
