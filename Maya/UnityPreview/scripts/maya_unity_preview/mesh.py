"""Extract selected meshes once on the Maya main thread, at mouse release.

Sends MESH_DATA_V2: positions, normals and UVs per corner, plus one submesh per material.
The Unity material is chosen by name: the Maya material node's name (namespace removed),
or the string attribute "unityMaterial" on the material when it is set.
"""
from maya import cmds
from maya.api import OpenMaya as om

from .mesh_payload import build_payload

UNITY_MATERIAL_ATTR = "unityMaterial"


def _short_name(node):
    return node.split("|")[-1].split(":")[-1]


def _material_name(shading_engine):
    shaders = cmds.listConnections(shading_engine + ".surfaceShader", source=True, destination=False) or []
    if not shaders:
        return ""
    material = shaders[0]
    if cmds.attributeQuery(UNITY_MATERIAL_ATTR, node=material, exists=True):
        value = cmds.getAttr(material + "." + UNITY_MATERIAL_ATTR)
        if value:
            return str(value).strip()
    return _short_name(material)


def _extract(shape):
    selection = om.MSelectionList()
    selection.add(shape)
    dag = selection.getDagPath(0)
    mesh = om.MFnMesh(dag)

    points = [(p.x, p.y, p.z) for p in mesh.getPoints(om.MSpace.kWorld)]
    normals = [(n.x, n.y, n.z) for n in mesh.getNormals(om.MSpace.kWorld)]
    _, normal_ids = mesh.getNormalIds()
    vertex_counts, vertex_list = mesh.getVertices()
    triangle_counts, triangle_vertices = mesh.getTriangles()

    shading_engines, face_materials = mesh.getConnectedShaders(dag.instanceNumber())
    material_names = [_material_name(om.MFnDependencyNode(engine).name()) for engine in shading_engines]

    uvs = uv_counts = uv_ids = None
    uv_set = mesh.currentUVSetName()
    if uv_set and mesh.numUVs(uv_set) > 0:
        us, vs = mesh.getUVs(uv_set)
        uvs = list(zip(us, vs))
        uv_counts, uv_ids = mesh.getAssignedUVs(uv_set)
        uv_counts, uv_ids = list(uv_counts), list(uv_ids)

    return build_payload(shape, points, normals, list(normal_ids), list(vertex_counts), list(vertex_list),
                         list(triangle_counts), list(triangle_vertices), list(face_materials), material_names,
                         uvs, uv_counts, uv_ids)


def selected_meshes():
    shapes = set()
    for node in cmds.ls(selection=True, objectsOnly=True, long=True) or []:
        if cmds.nodeType(node) == "mesh":
            shapes.add(node)
        else:
            shapes.update(cmds.listRelatives(node, allDescendents=True, fullPath=True, type="mesh") or [])
    return [_extract(shape) for shape in sorted(shapes) if not cmds.getAttr(shape + ".intermediateObject")]


def meshes_for(paths):
    """Payloads for the given mesh shape paths; missing or intermediate shapes are skipped."""
    result = []
    for path in paths:
        if not cmds.objExists(path) or cmds.nodeType(path) != "mesh":
            continue
        if cmds.getAttr(path + ".intermediateObject"):
            continue
        result.append(_extract(path))
    return result
