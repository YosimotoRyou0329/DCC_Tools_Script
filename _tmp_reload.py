import io, sys
from maya import cmds
log = io.open(r"D:/DCC/Tools/_tmp_log.txt", "w", encoding="utf-8")
try:
    import maya_unity_preview as package
    old = getattr(package, "_controller", None)
    if old is not None:
        try:
            old.shutdown()
        except Exception as error:
            log.write("shutdown: %r\n" % error)
    for name in [m for m in list(sys.modules) if m == "maya_unity_preview" or m.startswith("maya_unity_preview.")]:
        del sys.modules[name]
    DEV = r"D:/DCC/Tools/Maya/UnityPreview/scripts"
    if DEV in sys.path:
        sys.path.remove(DEV)
    sys.path.insert(0, DEV)
    import maya_unity_preview
    controller = maya_unity_preview.controller()
    maya_unity_preview.show()
    log.write("ok %s %s %s\n" % (maya_unity_preview.__file__, controller.sync_list.items(), controller.exe_path))
except Exception:
    import traceback
    log.write(traceback.format_exc())
log.close()
