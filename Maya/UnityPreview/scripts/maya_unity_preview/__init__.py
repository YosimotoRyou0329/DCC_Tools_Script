"""Public launcher entry point. Maya imports are deferred until show()."""
_controller = None


def controller():
    """The sync engine lives as long as Maya; the panel can be closed and reopened."""
    global _controller
    if _controller is None:
        from .engine import PreviewController   # module name must not shadow controller()
        _controller = PreviewController()
    return _controller


# Opened as a tab of the first of these that is shown (Channel Box / Layer Editor, Attribute
# Editor, Modeling Toolkit, Outliner). Its tab can then be dragged to any other panel or tab.
DOCK_TARGETS = ("ChannelBoxLayerEditor", "AttributeEditor", "NEXDockControl", "Outliner")


def show():
    from maya import cmds
    from .ui import PreviewPanel
    workspace = PreviewPanel.OBJECT_NAME + "WorkspaceControl"
    if cmds.workspaceControl(workspace, query=True, exists=True):
        cmds.deleteUI(workspace)
    panel = PreviewPanel(controller())
    panel.show(dockable=True, floating=True, retain=False)
    # A lone floating window only has the thin blue grip on its left to drag it into the
    # layout. As a tab it gets a normal tab that can be dragged anywhere (and no grip).
    for target in DOCK_TARGETS:
        try:
            if (cmds.workspaceControl(target, query=True, exists=True)
                    and cmds.workspaceControl(target, query=True, visible=True)):
                cmds.workspaceControl(workspace, edit=True, tabToControl=(target, -1))
                cmds.workspaceControl(workspace, edit=True, restore=True)
                break
        except RuntimeError:
            continue
    return panel


def toggle_unity_window():
    """Hide / show the Unity preview window (assign this to a Maya hotkey or shelf button)."""
    controller().toggle_unity_window()
