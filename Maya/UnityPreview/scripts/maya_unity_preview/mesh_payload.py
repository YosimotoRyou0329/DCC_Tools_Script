"""Build the MESH_DATA_V2 payload from plain Python lists. No Maya imports, so it can be unit tested.

Every triangle corner is identified by (vertex id, normal id, uv id). Corners that share all three
are merged into one Unity vertex; corners that differ (hard edges, UV seams) become separate vertices.
"""

PROTOCOL_TYPE = "MESH_DATA_V2"
_DIGITS = 6


def build_payload(name, points, normals, normal_ids, vertex_counts, vertex_list,
                  triangle_counts, triangle_vertices, face_materials, material_names,
                  uvs=None, uv_counts=None, uv_ids=None):
    """
    points            : [(x, y, z)] world-space vertex positions
    normals           : [(x, y, z)] world-space normals, indexed by normal_ids
    normal_ids        : normal id per face-vertex (same order as vertex_list)
    vertex_counts     : vertex count per face
    vertex_list       : vertex ids per face-vertex
    triangle_counts   : triangle count per face
    triangle_vertices : vertex ids of every triangle corner, face by face
    face_materials    : material slot per face (-1 = no material)
    material_names    : Unity material name per slot
    uvs               : [(u, v)] or None when the mesh has no UVs
    uv_counts         : per face, 0 (no UVs on that face) or the face's vertex count
    uv_ids            : uv id per face-vertex, only for faces that have UVs
    """
    has_uv = bool(uvs) and uv_counts is not None and uv_ids is not None
    corner_lookup = {}
    out_positions, out_normals, out_uvs = [], [], []
    submeshes = {}  # material name -> triangle index list (insertion ordered)

    face_vertex_offset = 0
    uv_offset = 0
    triangle_offset = 0
    for face, count in enumerate(vertex_counts):
        local_index = {}
        for local, vertex_id in enumerate(vertex_list[face_vertex_offset:face_vertex_offset + count]):
            local_index.setdefault(vertex_id, local)
        face_uv_count = uv_counts[face] if has_uv else 0

        slot = face_materials[face] if face < len(face_materials) else -1
        material = material_names[slot] if 0 <= slot < len(material_names) else ""
        triangles = submeshes.setdefault(material, [])

        corner_total = triangle_counts[face] * 3
        for corner in triangle_vertices[triangle_offset:triangle_offset + corner_total]:
            local = local_index[corner]
            normal_id = normal_ids[face_vertex_offset + local]
            uv_id = uv_ids[uv_offset + local] if face_uv_count else -1
            key = (corner, normal_id, uv_id)
            index = corner_lookup.get(key)
            if index is None:
                index = len(out_positions) // 3
                corner_lookup[key] = index
                out_positions.extend(round(value, _DIGITS) for value in points[corner][:3])
                out_normals.extend(round(value, _DIGITS) for value in normals[normal_id][:3])
                if has_uv:
                    u, v = uvs[uv_id] if uv_id >= 0 else (0.0, 0.0)
                    out_uvs.extend((round(u, _DIGITS), round(v, _DIGITS)))
            triangles.append(index)

        triangle_offset += corner_total
        face_vertex_offset += count
        uv_offset += face_uv_count

    return {
        "type": PROTOCOL_TYPE,
        "name": name,
        "positions": out_positions,
        "normals": out_normals,
        "uvs": out_uvs,
        "submeshes": [{"material": material, "triangles": triangles}
                      for material, triangles in submeshes.items() if triangles],
    }
