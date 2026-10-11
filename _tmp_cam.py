import io, math
from maya import cmds
LOG = r"D:/DCC/Tools/_tmp_log.txt"
def _state():
    t = cmds.xform('persp', q=True, ws=True, t=True)
    r = cmds.xform('persp', q=True, ws=True, ro=True)
    coi = cmds.camera('persp', q=True, coi=True)
    return t, r, coi
def cam_save():
    global _CAM_SAVED
    _CAM_SAVED = _state()
    io.open(LOG, "w", encoding="utf-8").write("saved %r\n" % (_CAM_SAVED,))
def cam_report(tag):
    t, r, coi = _state()
    io.open(LOG, "a", encoding="utf-8").write("%s t=%r r=%r coi=%r\n" % (tag, t, r, coi))
def cam_restore():
    t, r, coi = _CAM_SAVED
    cmds.xform('persp', ws=True, t=t, ro=r)
    cmds.camera('persp', e=True, coi=coi)
    cmds.setToolTo('selectSuperContext')
