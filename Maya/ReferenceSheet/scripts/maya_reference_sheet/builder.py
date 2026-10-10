"""Create / update / remove the reference planes in Maya (one undo step each).

ReferenceSheet_GRP            (the group can be moved; its transform is kept on update)
  RS_front_PLN ... RS_left_PLN  polygon planes, image aspect ratio, backface culled,
                                not rendered, unlit surfaceShader + file texture
ReferenceSheet_LYR            display layer (Reference = not selectable, optional)
The editor settings are stored in the scene (fileInfo), so reopening the tool restores them.
"""
import base64
import json
import os

from maya import cmds
from maya.api import OpenMaya as om

from . import layout

GROUP = "ReferenceSheet_GRP"
LAYER = "ReferenceSheet_LYR"
FILE_INFO_KEY = "mayaReferenceSheet"
TAG_ATTR = "referenceSheetView"
PLACE2D_ATTRS = ("coverage", "translateFrame", "rotateFrame", "mirrorU", "mirrorV", "stagger", "wrapU",
                 "wrapV", "repeatUV", "offset", "rotateUV", "noiseUV", "vertexUvOne", "vertexUvTwo",
                 "vertexUvThree", "vertexCameraOne")


# ---------------------------------------------------------------------- settings in the scene
def default_height():
    """160 cm in the scene's linear unit."""
    return round(om.MDistance(160.0, om.MDistance.kCentimeters).asUnits(om.MDistance.uiUnit()), 4)


def unit_label():
    return cmds.currentUnit(query=True, linear=True)


def default_config():
    height = default_height()
    return {"height": height, "distance": round(height * 0.5, 4), "opacity": 1.0,
            "reference": True, "textures": True, "views": {}}


def load_config():
    config = default_config()
    values = cmds.fileInfo(FILE_INFO_KEY, query=True) or []
    if values:
        try:   # base64 so Japanese paths and quotes survive Maya's fileInfo escaping
            config.update(json.loads(base64.b64decode(values[0]).decode("utf-8")))
        except (ValueError, UnicodeError, TypeError):
            pass
    return config


def save_config(config):
    data = json.dumps(config, ensure_ascii=False).encode("utf-8")
    cmds.fileInfo(FILE_INFO_KEY, base64.b64encode(data).decode("ascii"))


# ---------------------------------------------------------------------- build
def build(config):
    """(Re)create every plane that has an image. Returns (created plane names, warnings)."""
    created, warnings = [], []
    cmds.undoInfo(openChunk=True, chunkName="ReferenceSheet")
    try:
        group = GROUP if cmds.objExists(GROUP) else cmds.group(empty=True, name=GROUP)
        _remove_planes()
        for view in layout.VIEWS:
            entry = config.get("views", {}).get(view) or {}
            path = entry.get("path") or ""
            if not path:
                continue
            if not os.path.isfile(path):
                warnings.append("{}: 画像が見つかりません {}".format(layout.LABELS[view], path))
                continue
            width, height = entry.get("size") or (0, 0)
            if not width or not height:
                warnings.append("{}: 画像サイズが不明です".format(layout.LABELS[view]))
                continue
            try:
                placement = layout.plane_placement(view, width, height, entry["guides"], config["height"],
                                                   config["distance"], entry.get("flip", False))
            except (KeyError, ValueError) as error:
                warnings.append("{}: {}".format(layout.LABELS[view], error))
                continue
            created.append(_make_plane(group, view, path, placement, entry.get("flip", False), config["opacity"]))
        _apply_layer(group, config.get("reference", True))
        if config.get("textures", True):
            _show_textures()
        save_config(config)
    finally:
        cmds.undoInfo(closeChunk=True)
    return created, warnings


def remove():
    cmds.undoInfo(openChunk=True, chunkName="ReferenceSheetRemove")
    try:
        _remove_planes()
        for node in (GROUP, LAYER):
            if cmds.objExists(node):
                cmds.delete(node)
    finally:
        cmds.undoInfo(closeChunk=True)


def _make_plane(group, view, path, placement, flip, opacity):
    name = "RS_{}_PLN".format(view)
    plane = cmds.polyPlane(name=name, width=placement["width"], height=placement["height"],
                           subdivisionsX=1, subdivisionsY=1, axis=(0, 0, 1), constructionHistory=False)[0]
    _set_uvs(plane)
    plane = cmds.parent(plane, group, relative=True)[0]     # local values, whatever the group's transform
    cmds.setAttr(plane + ".translate", *placement["translate"])
    cmds.setAttr(plane + ".rotate", 0.0, placement["rotate_y"], 0.0)
    cmds.addAttr(plane, longName=TAG_ATTR, dataType="string")
    cmds.setAttr(plane + "." + TAG_ATTR, view, type="string")

    shape = cmds.listRelatives(plane, shapes=True, fullPath=True)[0]
    cmds.setAttr(shape + ".backfaceCulling", 3)       # invisible from behind -> never hides the model
    for attr in ("castsShadows", "receiveShadows", "primaryVisibility", "visibleInReflections",
                 "visibleInRefractions"):
        cmds.setAttr(shape + "." + attr, 0)
    for attr in ("translate", "rotate", "scale"):     # keep the alignment; move the group instead
        cmds.setAttr(plane + "." + attr, lock=True)

    shader = cmds.shadingNode("surfaceShader", asShader=True, name="RS_{}_MAT".format(view))
    engine = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=shader + "SG")
    cmds.connectAttr(shader + ".outColor", engine + ".surfaceShader", force=True)
    file_node = cmds.shadingNode("file", asTexture=True, isColorManaged=True, name="RS_{}_FILE".format(view))
    place = cmds.shadingNode("place2dTexture", asUtility=True, name="RS_{}_P2D".format(view))
    for attr in PLACE2D_ATTRS:
        cmds.connectAttr(place + "." + attr, file_node + "." + attr, force=True)
    cmds.connectAttr(place + ".outUV", file_node + ".uv", force=True)
    cmds.connectAttr(place + ".outUvFilterSize", file_node + ".uvFilterSize", force=True)
    cmds.setAttr(file_node + ".fileTextureName", path, type="string")
    cmds.setAttr(file_node + ".colorSpace", "sRGB", type="string")
    cmds.setAttr(file_node + ".alphaGain", max(0.0, min(1.0, float(opacity))))
    if flip:                                            # mirror in UV, never with negative scale
        cmds.setAttr(place + ".repeatU", -1)
    cmds.connectAttr(file_node + ".outColor", shader + ".outColor", force=True)
    cmds.connectAttr(file_node + ".outTransparency", shader + ".outTransparency", force=True)
    for node in (shader, engine, file_node, place):
        cmds.addAttr(node, longName=TAG_ATTR, dataType="string")
        cmds.setAttr(node + "." + TAG_ATTR, view, type="string")
    cmds.sets(plane, edit=True, forceElement=engine)
    return plane


def _set_uvs(plane):
    """Explicit UVs: u = 0 at local -X (screen left), v = 0 at local -Y (bottom)."""
    for index in range(4):
        vertex = "{}.vtx[{}]".format(plane, index)
        x, y, _ = cmds.pointPosition(vertex, local=True)
        uvs = cmds.polyListComponentConversion(vertex, toUV=True)
        cmds.polyEditUV(uvs, uValue=0.0 if x < 0 else 1.0, vValue=0.0 if y < 0 else 1.0, relative=False)


def _remove_planes():
    tagged = [n for n in cmds.ls("RS_*", long=True) or []
              if cmds.objExists(n) and cmds.attributeQuery(TAG_ATTR, node=n, exists=True)]
    transforms = [n for n in tagged if cmds.nodeType(n) == "transform"]
    for node in transforms:
        for attr in ("translate", "rotate", "scale"):
            cmds.setAttr(node + "." + attr, lock=False)
    others = [n for n in tagged if n not in transforms]
    for nodes in (transforms, others):
        existing = [n for n in nodes if cmds.objExists(n)]
        if existing:
            cmds.delete(existing)


def _apply_layer(group, reference):
    if not cmds.objExists(LAYER):
        cmds.createDisplayLayer(name=LAYER, empty=True, noRecurse=True)
    cmds.editDisplayLayerMembers(LAYER, group, noRecurse=True)
    cmds.setAttr(LAYER + ".displayType", 2 if reference else 0)   # 2 = Reference (not selectable)


def _show_textures():
    for panel in cmds.getPanel(type="modelPanel") or []:
        try:
            cmds.modelEditor(panel, edit=True, displayTextures=True)
        except RuntimeError:
            pass


def existing_views():
    return sorted(cmds.getAttr(n + "." + TAG_ATTR) for n in cmds.ls("RS_*_PLN") or []
                  if cmds.attributeQuery(TAG_ATTR, node=n, exists=True))
