"""Pure layout maths for the reference sheet (no Maya / Qt imports, unit tested).

Coordinates
- Image pixels: x to the right, y downwards, (0, 0) = top-left.
- Guides per image: top (head), bottom (feet) rows and the centre column of the character.
- Maya: Y up, the character faces +Z (front camera at +Z), its left side is +X.

Each plane sits *behind* the character as seen from its camera and faces that camera.
With backface culling the plane is invisible from the other side, so the plane between a
camera and the model never hides the model.
"""

VIEWS = ("front", "back", "right", "left")
LABELS = {"front": "正面", "back": "背面", "right": "右側面", "left": "左側面"}
HINTS = {
    "front": "キャラを前から見た図（Maya front カメラ: +Z から見る）",
    "back": "キャラを後ろから見た図（-Z から見る）",
    "right": "キャラの右側を見た図（-X から見る / 顔が画面の右向き）",
    "left": "キャラの左側を見た図（Maya side カメラ: +X から見る / 顔が画面の左向き）",
}

# position: direction of the plane from the origin (times distance)
# rotate_y: plane rotation so it faces its camera (plane normal +Z before rotation)
# right: world direction of "screen right" for the camera looking at this plane
VIEW_SETUP = {
    "front": {"position": (0.0, 0.0, -1.0), "rotate_y": 0.0, "right": (1.0, 0.0, 0.0)},
    "back": {"position": (0.0, 0.0, 1.0), "rotate_y": 180.0, "right": (-1.0, 0.0, 0.0)},
    "right": {"position": (1.0, 0.0, 0.0), "rotate_y": -90.0, "right": (0.0, 0.0, 1.0)},
    "left": {"position": (-1.0, 0.0, 0.0), "rotate_y": 90.0, "right": (0.0, 0.0, -1.0)},
}


def default_guides(width, height):
    return {"top": 0.0, "bottom": float(height), "center": width / 2.0}


def plane_placement(view, image_width, image_height, guides, height, distance, flip=False):
    """Plane size (keeps the image aspect ratio) and transform so that, for every image,
    the head guide is at Y=height, the feet guide at Y=0 and the centre line on the axis."""
    span = float(guides["bottom"]) - float(guides["top"])
    if span <= 0:
        raise ValueError("頭頂ガイドは足元ガイドより上にしてください")
    scale = float(height) / span                      # scene units per pixel
    center = image_width - guides["center"] if flip else guides["center"]
    offset_right = (image_width / 2.0 - center) * scale
    center_y = (guides["bottom"] - image_height / 2.0) * scale
    setup = VIEW_SETUP[view]
    px, _, pz = (v * distance for v in setup["position"])
    rx, _, rz = setup["right"]
    return {
        "width": image_width * scale,
        "height": image_height * scale,
        "translate": (px + rx * offset_right, center_y, pz + rz * offset_right),
        "rotate_y": setup["rotate_y"],
    }


# ---------------------------------------------------------------------- guide detection
def detect_guides(width, height, rgba, edge_threshold=40, min_row_pixels=2):
    """Estimate head / feet rows and the centre column from RGBA bytes (row-major, 4 bytes/pixel).

    Transparent images use alpha. Opaque ones use edge strength, so soft glows and gradients in
    the background (common in generated reference sheets) are ignored and only the line art counts.
    """
    def alpha(x, y):
        return rgba[(y * width + x) * 4 + 3]

    border = [alpha(x, 0) for x in range(width)] + [alpha(x, height - 1) for x in range(width)]
    transparent = sum(1 for a in border if a < 16) > len(border) * 0.5

    luminance = [0.0] * (width * height)
    for i in range(width * height):
        r, g, b = rgba[i * 4], rgba[i * 4 + 1], rgba[i * 4 + 2]
        luminance[i] = 0.299 * r + 0.587 * g + 0.114 * b

    mask_rows = [[] for _ in range(height)]
    for y in range(1, height - 1):
        row = y * width
        xs = mask_rows[y]
        for x in range(1, width - 1):
            if transparent:
                if rgba[(row + x) * 4 + 3] >= 128:
                    xs.append(x)
                continue
            i = row + x
            gradient = abs(luminance[i + 1] - luminance[i - 1]) + abs(luminance[i + width] - luminance[i - width])
            if gradient > edge_threshold:
                xs.append(x)

    rows = [y for y in range(height) if len(mask_rows[y]) >= min_row_pixels]
    if not rows:
        return default_guides(width, height)
    top, bottom = rows[0], rows[-1] + 1

    # centre: median x of the outline in the lower part (legs), unaffected by spread arms
    start = top + int((bottom - top) * 0.65)
    xs = sorted(x for y in range(start, bottom) for x in mask_rows[y])
    center = xs[len(xs) // 2] if xs else width / 2.0
    return {"top": float(top), "bottom": float(bottom), "center": float(center)}


def scale_guides(guides, factor):
    return {key: value * factor for key, value in guides.items()}
