"""Maya material -> MATERIAL_DEF (read only; this tool never edits Maya materials).

Model and texture in Maya as usual. What Unity receives per Maya material:
- name      : the Maya material name (or its unityMaterial string attribute)
- baseColor : the colour, or white when a texture is connected
- @base     : file texture connected to color / baseColor
- @normal   : file texture behind bump2d on normalCamera (tangent space normal map)
The Unity shader and its values are chosen in the PreviewHost Inspector and saved there.
"""
import os
import re

from maya import cmds

UNITY_MATERIAL_ATTR = "unityMaterial"
COLOR_ATTRS = ("baseColor", "color")          # standardSurface / aiStandardSurface / openPBR, lambert family


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
    data = {"type": "MATERIAL_DEF", "name": unity_name(material),
            "baseColor": base_color, "textures": textures}
    return data, deps, [t["path"] for t in textures if t["path"]]


# ---------------------------------------------------------------------- texture reload
def reload_file_nodes(path):
    """Make Maya re-read a texture that changed on disk (same path)."""
    wanted = os.path.normcase(os.path.normpath(path))
    for file_node in cmds.ls(type="file") or []:
        current = file_path(file_node)
        if current and os.path.normcase(os.path.normpath(current)) == wanted:
            value = cmds.getAttr(file_node + ".fileTextureName")
            cmds.setAttr(file_node + ".fileTextureName", value, type="string")
