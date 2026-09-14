"""Extract selected meshes once on the Maya main thread, at mouse release."""
from maya import cmds
from maya.api import OpenMaya as om


def selected_meshes():
    shapes = set()
    for node in cmds.ls(selection=True, objectsOnly=True, long=True) or []:
        if cmds.nodeType(node) == "mesh":
            shapes.add(node)
        else:
            shapes.update(cmds.listRelatives(node, allDescendents=True, fullPath=True, type="mesh") or [])
    result = []
    for shape in sorted(shapes):
        if cmds.getAttr(shape + ".intermediateObject"):
            continue
        selection = om.MSelectionList()
        selection.add(shape)
        mesh = om.MFnMesh(selection.getDagPath(0))
        points = mesh.getPoints(om.MSpace.kWorld)
        _, triangles = mesh.getTriangles()
        result.append({"type": "MESH_DATA", "name": shape,
                       "vertex_count": len(points), "triangle_index_count": len(triangles),
                       "vertices": [{"x": p.x, "y": p.y, "z": p.z} for p in points],
                       "triangles": list(triangles)})
    return result
