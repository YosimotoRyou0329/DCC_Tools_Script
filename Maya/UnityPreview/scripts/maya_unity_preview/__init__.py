"""Public launcher entry point. Maya imports are deferred until show()."""
_controller = None


def controller():
    """The sync engine lives as long as Maya; the panel can be closed and reopened."""
    global _controller
    if _controller is None:
        from .controller import PreviewController
        _controller = PreviewController()
    return _controller


def show():
    from maya import cmds
    from .ui import PreviewPanel
    workspace = PreviewPanel.OBJECT_NAME + "WorkspaceControl"
    if cmds.workspaceControl(workspace, query=True, exists=True):
        cmds.deleteUI(workspace)
    panel = PreviewPanel(controller())
    panel.show(dockable=True, floating=True, retain=False)
    return panel


def toggle_unity_window():
    """Hide / show the Unity preview window (assign this to a Maya hotkey or shelf button)."""
    controller().toggle_unity_window()
