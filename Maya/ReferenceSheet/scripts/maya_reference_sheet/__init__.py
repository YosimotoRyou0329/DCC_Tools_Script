"""Reference Sheet: up to 4 images (front / back / right / left) -> aligned reference planes."""


def show():
    from maya import cmds
    from .ui import ReferenceSheetPanel
    workspace = ReferenceSheetPanel.OBJECT_NAME + "WorkspaceControl"
    if cmds.workspaceControl(workspace, query=True, exists=True):
        cmds.deleteUI(workspace)
    panel = ReferenceSheetPanel()
    panel.show(dockable=True, floating=True, retain=False)
    return panel
