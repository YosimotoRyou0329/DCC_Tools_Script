"""Pure layout maths for the reference sheet (no Maya / Qt imports, unit tested).

Coordinates
- Image pixels: x to the right, y downwards, (0, 0) = top-left.
- Guides per image: top (head), bottom (feet) rows and the centre column of the character.
- Maya: Y up, the character faces +Z (front camera at +Z), its left side is +X.

Each plane sits *behind* the character as seen from its camera and faces that camera.
With backface culling the plane is invisible from the other side, so the plane between a
camera and the model never hides the model.

Alignment (landmarks)
- Every image maps pixel rows to world height linearly: Y = origin - scale * row
  (one uniform scale per image, so the image is never stretched).
- The master image defines the world: its head guide is at `height`, its feet guide at 0.
- Other images are fitted to the master on the landmarks marked "align" (eyes, chin...):
  1 landmark -> height only, 2 or more -> scale and height by least squares.
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


# Landmark presets: key (ASCII, used for Maya node names), label, default position as a ratio
# of the head-to-feet span (typical anime proportions; drag them onto the image).
LANDMARK_PRESETS = (
    ("eye", "目", 0.10), ("chin", "あご", 0.16), ("neck", "首", 0.19), ("shoulder", "肩", 0.22),
    ("chest", "胸", 0.32), ("waist", "腰", 0.45), ("crotch", "股", 0.52), ("knee", "膝", 0.73),
    ("ankle", "足首", 0.95),
)
LANDMARK_COLORS = ("#ffd166", "#f78c6b", "#c77dff", "#06d6a0", "#ef476f", "#90be6d", "#f9c74f",
                   "#4cc9f0", "#ff9f1c", "#b5179e")


def default_landmarks():
    return [{"key": "top", "name": "頭頂", "align": True},
            {"key": "bottom", "name": "足元", "align": True}]


def default_guides(width, height):
    return {"top": 0.0, "bottom": float(height), "center": width / 2.0}


def initial_row(guides, ratio):
    """Row for a new landmark: `ratio` of the way from the head guide to the feet guide."""
    return guides["top"] + (guides["bottom"] - guides["top"]) * ratio


def landmark_ratio(guides, key):
    span = guides["bottom"] - guides["top"]
    return (guides[key] - guides["top"]) / span if span > 0 and key in guides else None


# ---------------------------------------------------------------------- alignment
def own_fit(guides, height):
    """Scale / origin from the image's own head and feet guides."""
    span = float(guides["bottom"]) - float(guides["top"])
    if span <= 0:
        raise ValueError("頭頂ガイドは足元ガイドより上にしてください")
    scale = float(height) / span
    return scale, scale * guides["bottom"]


def fit_image(guides, targets, keys, height):
    """(scale, origin) so that guides[key] rows land on targets[key] world heights."""
    pairs = [(float(guides[k]), float(targets[k])) for k in keys if k in guides and k in targets]
    rows = {round(r, 3) for r, _ in pairs}
    if len(pairs) >= 2 and len(rows) >= 2:
        mean_r = sum(r for r, _ in pairs) / len(pairs)
        mean_h = sum(h for _, h in pairs) / len(pairs)
        variance = sum((r - mean_r) ** 2 for r, _ in pairs)
        scale = -sum((r - mean_r) * (h - mean_h) for r, h in pairs) / variance
        if scale > 0:
            return scale, mean_h + scale * mean_r
    scale, origin = own_fit(guides, height)
    if pairs:   # keep the own scale, move so the landmarks match on average
        origin = sum(h + scale * r for r, h in pairs) / len(pairs)
    return scale, origin


def fit_all(views, master, height, align_keys):
    """views: {view: guides}. Returns {view: {"scale", "origin", "residuals": {key: world error}}}
    and the world height of every landmark of the master: (fits, targets)."""
    if master not in views:
        master = next((v for v in VIEWS if v in views), None)
    if master is None:
        return {}, {}
    scale0, origin0 = own_fit(views[master], height)
    targets = {k: origin0 - scale0 * row for k, row in views[master].items() if k != "center"}
    fits = {}
    keys = [k for k in align_keys if k != "center"]
    for view, guides in views.items():
        if view == master:
            scale, origin = scale0, origin0
        else:
            scale, origin = fit_image(guides, targets, keys, height)
        residuals = {k: (origin - scale * guides[k]) - targets[k] for k in keys if k in guides and k in targets}
        fits[view] = {"scale": scale, "origin": origin, "residuals": residuals}
    return fits, targets


def placement_from_fit(view, image_width, image_height, center, scale, origin, distance, flip=False):
    """Plane size (image aspect ratio) and transform for a fitted image."""
    center = image_width - center if flip else center
    offset_right = (image_width / 2.0 - center) * scale
    center_y = origin - scale * image_height / 2.0
    setup = VIEW_SETUP[view]
    px, _, pz = (v * distance for v in setup["position"])
    rx, _, rz = setup["right"]
    return {
        "width": image_width * scale,
        "height": image_height * scale,
        "translate": (px + rx * offset_right, center_y, pz + rz * offset_right),
        "rotate_y": setup["rotate_y"],
    }


def plane_placement(view, image_width, image_height, guides, height, distance, flip=False):
    """Placement aligned on the image's own head / feet guides (no landmarks)."""
    scale, origin = own_fit(guides, height)
    return placement_from_fit(view, image_width, image_height, guides["center"], scale, origin, distance, flip)


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
