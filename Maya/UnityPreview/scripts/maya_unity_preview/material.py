"""Maya material <-> Unity material definition (MATERIAL_DEF).

The Maya material is the source of truth:
- base colour texture / normal map are real Maya file nodes, so UVs and texture placement
  are visible in the Maya viewport;
- the Unity shader (template) and any extra Unity texture slots are stored as string
  attributes on the material (unityTemplate / unityTextures);
- the Unity material name is the Maya material name (or its unityMaterial attribute).
All edits go through maya.cmds, so they are undoable.
"""
import json
import os
import re

from maya import cmds

UNITY_MATERIAL_ATTR = "unityMaterial"
UNITY_TEMPLATE_ATTR = "unityTemplate"
UNITY_TEXTURES_ATTR = "unityTextures"
COLOR_ATTRS = ("baseColor", "color")          # standardSurface / aiStandardSurface / openPBR, lambert family
PLACE2D_ATTRS = ("coverage", "translateFrame", "rotateFrame", "mirrorU", "mirrorV", "stagger", "wrapU",
                 "wrapV", "repeatUV", "offset", "rotateUV", "noiseUV", "vertexUvOne", "vertexUvTwo",
                 "vertexUvThree", "vertexCameraOne")


# ---------------------------------------------------------------------- reading
def short_name(node):
    return node.split("|")[-1].split(":")[-1]


def _string_attr(node, attr):
    if cmds.attributeQuery(attr, node=node, exists=True):
        return cmds.getAttr(node + "." + attr) or ""
    return ""


def unity_name(material):
    return _string_attr(material, UNITY_MATERIAL_ATTR).strip() or short_name(material)


def material_of(shading_engine):
    shaders = cmds.listConnections(shading_engine + ".surfaceShader", source=True, destination=False) or []
    return shaders[0] if shaders else None


def color_attr(material):
    for attr in COLOR_ATTRS:
        if cmds.attributeQuery(attr, node=material, exists=True):
            return attr
    return None


def _upstream(plug, node_type):
    for node in cmds.listConnections(plug, source=True, destination=False) or []:
        if cmds.nodeType(node) == node_type:
            return node
        found = cmds.ls(cmds.listHistory(node) or [], type=node_type)
        if found:
            return found[0]
    return None


def base_file(material):
    attr = color_attr(material)
    return _upstream(material + "." + attr, "file") if attr else None


def normal_nodes(material):
    """(bump2d, file) for a tangent-space normal map on normalCamera, or (None, None)."""
    if not cmds.attributeQuery("normalCamera", node=material, exists=True):
        return None, None
    bump = _upstream(material + ".normalCamera", "bump2d")
    if not bump:
        return None, None
    return bump, _upstream(bump + ".bumpValue", "file")


def file_path(file_node):
    """Absolute, forward-slash path of a file node's texture ('' when empty)."""
    path = (cmds.getAttr(file_node + ".fileTextureName") or "").replace("\\", "/")
    if path and not (os.path.isabs(path) or re.match(r"^[A-Za-z]:/", path)):
        path = cmds.workspace(expandName=path).replace("\\", "/")   # project-relative path
    return os.path.normpath(path).replace("\\", "/") if path else ""


def extra_textures(material):
    try:
        data = json.loads(_string_attr(material, UNITY_TEXTURES_ATTR) or "{}")
    except ValueError:
        data = {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str) and v}


def state(material):
    """What the panel shows for a material."""
    base = base_file(material)
    _, normal = normal_nodes(material)
    return {"name": unity_name(material),
            "template": _string_attr(material, UNITY_TEMPLATE_ATTR),
            "base": file_path(base) if base else "",
            "normal": file_path(normal) if normal else "",
            "extras": extra_textures(material)}


def definition(material):
    """(MATERIAL_DEF dict, dependency nodes to watch, texture paths to watch)."""
    textures, deps = [], [material]
    attr = color_attr(material)
    base = base_file(material)
    if base:
        textures.append({"prop": "@base", "path": file_path(base)})
        deps.append(base)
        base_color = [1.0, 1.0, 1.0, 1.0]
    elif attr:
        value = cmds.getAttr(material + "." + attr)[0]
        base_color = [round(float(v), 5) for v in value] + [1.0]
    else:
        base_color = [0.7, 0.7, 0.7, 1.0]
    bump, normal = normal_nodes(material)
    if normal:
        textures.append({"prop": "@normal", "path": file_path(normal)})
        deps.extend([bump, normal])
    for prop, path in sorted(extra_textures(material).items()):
        textures.append({"prop": prop, "path": path.replace("\\", "/")})
    data = {"type": "MATERIAL_DEF", "name": unity_name(material),
            "template": _string_attr(material, UNITY_TEMPLATE_ATTR),
            "baseColor": base_color, "textures": textures}
    return data, deps, [t["path"] for t in textures if t["path"]]


def materials_of_meshes(mesh_paths):
    result = []
    for shape in mesh_paths:
        for engine in cmds.listConnections(shape, type="shadingEngine") or []:
            material = material_of(engine)
            if material and material not in result:
                result.append(material)
    return result


# ---------------------------------------------------------------------- editing
def _ensure_string_attr(node, attr):
    if not cmds.attributeQuery(attr, node=node, exists=True):
        cmds.addAttr(node, longName=attr, dataType="string")


def set_template(material, template):
    _ensure_string_attr(material, UNITY_TEMPLATE_ATTR)
    cmds.setAttr(material + "." + UNITY_TEMPLATE_ATTR, template or "", type="string")


def _new_file_node(color_space):
    file_node = cmds.shadingNode("file", asTexture=True, isColorManaged=True)
    place = cmds.shadingNode("place2dTexture", asUtility=True)
    for attr in PLACE2D_ATTRS:
        cmds.connectAttr(place + "." + attr, file_node + "." + attr, force=True)
    cmds.connectAttr(place + ".outUV", file_node + ".uv", force=True)
    cmds.connectAttr(place + ".outUvFilterSize", file_node + ".uvFilterSize", force=True)
    cmds.setAttr(file_node + ".colorSpace", color_space, type="string")
    return file_node


def set_base_texture(material, path):
    attr = color_attr(material)
    if not attr:
        raise RuntimeError("カラー入力のないマテリアルです: " + material)
    file_node = base_file(material)
    if not path:
        if file_node:
            cmds.disconnectAttr(file_node + ".outColor", material + "." + attr)
        return
    if not file_node:
        file_node = _new_file_node("sRGB")
        cmds.connectAttr(file_node + ".outColor", material + "." + attr, force=True)
    cmds.setAttr(file_node + ".fileTextureName", path, type="string")


def set_normal_texture(material, path):
    if not cmds.attributeQuery("normalCamera", node=material, exists=True):
        raise RuntimeError("ノーマル入力のないマテリアルです: " + material)
    bump, file_node = normal_nodes(material)
    if not path:
        if bump:
            cmds.disconnectAttr(bump + ".outNormal", material + ".normalCamera")
        return
    if not bump:
        bump = cmds.shadingNode("bump2d", asUtility=True)
        cmds.setAttr(bump + ".bumpInterp", 1)            # tangent space normals
        cmds.connectAttr(bump + ".outNormal", material + ".normalCamera", force=True)
    if not file_node:
        file_node = _new_file_node("Raw")
        cmds.connectAttr(file_node + ".outAlpha", bump + ".bumpValue", force=True)
    cmds.setAttr(file_node + ".fileTextureName", path, type="string")


def set_extra_texture(material, prop, path):
    data = extra_textures(material)
    if path:
        data[prop] = path
    else:
        data.pop(prop, None)
    _ensure_string_attr(material, UNITY_TEXTURES_ATTR)
    cmds.setAttr(material + "." + UNITY_TEXTURES_ATTR, json.dumps(data, sort_keys=True), type="string")


def create_material(name, template, targets):
    """New lambert (+ shading group) assigned to targets (objects or faces)."""
    material = cmds.shadingNode("lambert", asShader=True, name=name or "MT_New")
    engine = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=material + "SG")
    cmds.connectAttr(material + ".outColor", engine + ".surfaceShader", force=True)
    set_template(material, template)
    if targets:
        cmds.sets(targets, edit=True, forceElement=engine)
    return material


def reload_file_nodes(path):
    """Make Maya re-read a texture that changed on disk (same path)."""
    wanted = os.path.normcase(os.path.normpath(path))
    for file_node in cmds.ls(type="file") or []:
        current = file_path(file_node)
        if current and os.path.normcase(os.path.normpath(current)) == wanted:
            value = cmds.getAttr(file_node + ".fileTextureName")
            cmds.setAttr(file_node + ".fileTextureName", value, type="string")
