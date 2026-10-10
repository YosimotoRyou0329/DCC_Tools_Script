import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from maya_reference_sheet.layout import plane_placement, detect_guides, fit_all, placement_from_fit, aligned_keys, VIEWS


def close(a, b):
    return all(abs(x - y) < 1e-6 for x, y in zip(a, b))


class PlacementTests(unittest.TestCase):
    guides = {"top": 100.0, "bottom": 900.0, "center": 400.0}   # 1000 x 1000 image

    def test_keeps_aspect_ratio_and_height(self):
        p = plane_placement("front", 1000, 1500, self.guides, 160.0, 80.0)
        self.assertAlmostEqual(p["height"] / p["width"], 1.5)
        self.assertAlmostEqual(p["width"], 1000 * 160.0 / 800.0)

    def test_feet_on_ground_and_centre_on_axis(self):
        p = plane_placement("front", 1000, 1000, self.guides, 160.0, 80.0)
        scale = 160.0 / 800.0
        # pixel row 900 -> Y = centre_y + (500 - 900) * scale must be 0
        self.assertAlmostEqual(p["translate"][1] + (500 - 900) * scale, 0.0)
        # pixel column 400 -> X = centre_x + (400 - 500) * scale must be 0 (front: screen right = +X)
        self.assertAlmostEqual(p["translate"][0] + (400 - 500) * scale, 0.0)
        self.assertTrue(close((p["translate"][2],), (-80.0,)))   # behind the model

    def test_each_view_faces_its_camera(self):
        rot = {v: plane_placement(v, 1000, 1000, self.guides, 160.0, 80.0)["rotate_y"] for v in VIEWS}
        self.assertEqual(rot, {"front": 0.0, "back": 180.0, "right": -90.0, "left": 90.0})
        left = plane_placement("left", 1000, 1000, self.guides, 160.0, 80.0)["translate"]
        right = plane_placement("right", 1000, 1000, self.guides, 160.0, 80.0)["translate"]
        self.assertAlmostEqual(left[0], -80.0)    # seen from +X -> plane on -X
        self.assertAlmostEqual(right[0], 80.0)
        # centre column (400) must land on Z=0: left view screen right = -Z, right view = +Z
        scale = 160.0 / 800.0
        self.assertAlmostEqual(left[2] + (-1.0) * (400 - 500) * scale, 0.0)
        self.assertAlmostEqual(right[2] + (+1.0) * (400 - 500) * scale, 0.0)

    def test_flip_mirrors_the_centre(self):
        normal = plane_placement("front", 1000, 1000, self.guides, 160.0, 80.0)
        flipped = plane_placement("front", 1000, 1000, self.guides, 160.0, 80.0, flip=True)
        self.assertAlmostEqual(normal["translate"][0], -flipped["translate"][0])

    def test_rejects_inverted_guides(self):
        with self.assertRaises(ValueError):
            plane_placement("front", 10, 10, {"top": 8, "bottom": 2, "center": 5}, 1, 1)


class FitTests(unittest.TestCase):
    master = {"top": 0.0, "bottom": 1000.0, "center": 500.0, "eye": 100.0, "chin": 200.0}

    def world(self, fit, row):
        return fit["origin"] - fit["scale"] * row

    def test_master_defines_the_world(self):
        fits, targets = fit_all({"front": self.master}, "front", 160.0, ["top", "bottom"])
        self.assertAlmostEqual(targets["top"], 160.0)
        self.assertAlmostEqual(targets["bottom"], 0.0)
        self.assertAlmostEqual(targets["eye"], 160.0 - 16.0)

    def test_two_landmarks_match_exactly(self):
        # side image: head drawn bigger and higher (eye 50 -> chin 250), body proportions differ
        side = {"top": 0.0, "bottom": 1100.0, "center": 400.0, "eye": 50.0, "chin": 250.0}
        fits, targets = fit_all({"front": self.master, "left": side}, "front", 160.0, ["eye", "chin"])
        fit = fits["left"]
        self.assertAlmostEqual(self.world(fit, side["eye"]), targets["eye"])
        self.assertAlmostEqual(self.world(fit, side["chin"]), targets["chin"])
        self.assertTrue(all(abs(e) < 1e-9 for e in fit["residuals"].values()))
        self.assertAlmostEqual(fit["scale"], 16.0 / 200.0)    # uniform: never stretched

    def test_one_landmark_moves_only(self):
        side = {"top": 0.0, "bottom": 800.0, "center": 400.0, "eye": 60.0}
        fits, targets = fit_all({"front": self.master, "left": side}, "front", 160.0, ["eye"])
        self.assertAlmostEqual(fits["left"]["scale"], 160.0 / 800.0)   # own head-to-feet scale
        self.assertAlmostEqual(self.world(fits["left"], 60.0), targets["eye"])

    def test_least_squares_with_three(self):
        side = dict(self.master, eye=110.0, chin=190.0)
        fits, _ = fit_all({"front": self.master, "left": side}, "front", 160.0, ["top", "eye", "chin"])
        residuals = fits["left"]["residuals"]
        self.assertAlmostEqual(sum(residuals.values()), 0.0)   # balanced error, nothing exact
        self.assertTrue(max(abs(e) for e in residuals.values()) < 2.0)

    def test_at_most_two_lines_and_they_match_exactly(self):
        landmarks = [{"key": "top", "align": True}, {"key": "bottom", "align": True},
                     {"key": "eye", "align": True, "order": 5}, {"key": "chin", "align": True, "order": 6}]
        keys = aligned_keys(landmarks)
        self.assertEqual(keys, ["eye", "chin"])
        # side image: whole body proportions differ, head drawn bigger -> eye and chin still exact
        side = {"top": 30.0, "bottom": 1200.0, "center": 400.0, "eye": 140.0, "chin": 290.0}
        fits, targets = fit_all({"front": self.master, "left": side}, "front", 160.0, keys)
        for key in keys:
            self.assertAlmostEqual(self.world(fits["left"], side[key]), targets[key])

    def test_placement_from_fit_matches_plane_placement(self):
        guides = {"top": 100.0, "bottom": 900.0, "center": 400.0}
        a = plane_placement("left", 1000, 1200, guides, 160.0, 50.0, True)
        scale = 160.0 / 800.0
        b = placement_from_fit("left", 1000, 1200, 400.0, scale, scale * 900.0, 50.0, True)
        self.assertEqual(a, b)


class DetectTests(unittest.TestCase):
    @staticmethod
    def image(width, height, box, background=(10, 10, 20, 255), figure=(240, 240, 240, 255)):
        x0, y0, x1, y1 = box
        data = bytearray()
        for y in range(height):
            for x in range(width):
                data += bytes(figure if x0 <= x < x1 and y0 <= y < y1 else background)
        return bytes(data)

    def test_opaque_image_uses_outline(self):
        g = detect_guides(60, 80, self.image(60, 80, (20, 10, 40, 70)))
        self.assertTrue(8 <= g["top"] <= 11 and 69 <= g["bottom"] <= 72, g)
        self.assertTrue(18 <= g["center"] <= 41, g)

    def test_transparent_image_uses_alpha(self):
        g = detect_guides(60, 80, self.image(60, 80, (20, 10, 40, 70), background=(0, 0, 0, 0)))
        self.assertEqual((g["top"], g["bottom"]), (10.0, 70.0))
        self.assertTrue(20 <= g["center"] <= 40, g)

    def test_soft_gradient_is_ignored(self):
        # vertical luminance ramp (like a glow) with no figure: no edges -> full image
        data = bytearray()
        for y in range(50):
            for x in range(40):
                v = min(255, x * 3)
                data += bytes((v, v, v, 255))
        g = detect_guides(40, 50, bytes(data))
        self.assertEqual((g["top"], g["bottom"]), (0.0, 50.0))


if __name__ == "__main__":
    unittest.main()
