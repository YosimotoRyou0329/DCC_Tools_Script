import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from maya_unity_preview.mesh_payload import build_payload


def cube_face_data():
    """Two quads sharing an edge (vertices 1 and 2), each with its own material."""
    points = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (2, 0, 0), (2, 1, 0)]
    vertex_counts = [4, 4]
    vertex_list = [0, 1, 2, 3, 1, 4, 5, 2]
    triangle_counts = [2, 2]
    triangle_vertices = [0, 1, 2, 0, 2, 3, 1, 4, 5, 1, 5, 2]
    return points, vertex_counts, vertex_list, triangle_counts, triangle_vertices


class MeshPayloadTests(unittest.TestCase):
    def test_soft_edge_shares_vertices_and_splits_materials(self):
        points, counts, verts, tri_counts, tris = cube_face_data()
        normals = [(0, 0, 1)]
        payload = build_payload("|plane|planeShape", points, normals, [0] * 8, counts, verts,
                                tri_counts, tris, [0, 1], ["MT_A", "MT_B"])
        self.assertEqual(payload["type"], "MESH_DATA_V2")
        self.assertEqual(len(payload["positions"]) // 3, 6)  # shared edge merged
        self.assertEqual(payload["uvs"], [])
        self.assertEqual([s["material"] for s in payload["submeshes"]], ["MT_A", "MT_B"])
        self.assertEqual(payload["submeshes"][0]["triangles"], [0, 1, 2, 0, 2, 3])

    def test_hard_edge_and_uv_seam_split_vertices(self):
        points, counts, verts, tri_counts, tris = cube_face_data()
        normals = [(0, 0, 1), (1, 0, 0)]
        normal_ids = [0, 0, 0, 0, 1, 1, 1, 1]  # different normal on each face -> hard edge
        uvs = [(0, 0), (1, 0), (1, 1), (0, 1)]
        payload = build_payload("s", points, normals, normal_ids, counts, verts, tri_counts, tris,
                                [0, 0], ["MT_A"], uvs, [4, 4], [0, 1, 2, 3, 0, 1, 2, 3])
        self.assertEqual(len(payload["positions"]) // 3, 8)
        self.assertEqual(len(payload["uvs"]), 16)
        self.assertEqual(len(payload["submeshes"]), 1)
        self.assertEqual(len(payload["submeshes"][0]["triangles"]), 12)

    def test_faces_without_uv_or_material(self):
        points, counts, verts, tri_counts, tris = cube_face_data()
        uvs = [(0, 0), (1, 0), (1, 1), (0, 1)]
        payload = build_payload("s", points, [(0, 0, 1)], [0] * 8, counts, verts, tri_counts, tris,
                                [-1, 0], ["MT_A"], uvs, [4, 0], [0, 1, 2, 3])
        self.assertEqual([s["material"] for s in payload["submeshes"]], ["", "MT_A"])
        self.assertEqual(len(payload["uvs"]) // 2, len(payload["positions"]) // 3)
        for triangle_list in (s["triangles"] for s in payload["submeshes"]):
            self.assertTrue(all(0 <= i < len(payload["positions"]) // 3 for i in triangle_list))


if __name__ == "__main__":
    unittest.main()
