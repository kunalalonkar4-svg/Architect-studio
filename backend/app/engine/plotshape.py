"""Irregular (convex) plots. The house is still a rectangle, so we fit the largest axis-aligned rectangle that stays inside the plot
after the open-space values you gave, and hand the engine the equivalent margins to the plot's bounding box.
Convex plots only (trapezium, kite, angled corners, pentagon). L-shaped or concave plots are refused with a clear reason."""
from __future__ import annotations

from .layout import ImpossibleLayout

LEFT_OF = {"s": "w", "n": "e", "e": "s", "w": "n"}      # world side on the left when you stand at the road looking in
OPP = {"n": "s", "s": "n", "e": "w", "w": "e"}
MAX_PTS = 12


def _cross(o, a, b): return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def normalise(points) -> list[list[float]]:
    """Validate and return vertices counter-clockwise, shifted so the bounding box starts at (0, 0)."""
    try:
        pts = [(float(p[0]), float(p[1])) for p in points]
    except (TypeError, ValueError, IndexError):
        raise ImpossibleLayout(["The plot corners must be numbers (x, y)"], ["Enter each corner as two numbers"])
    if not (3 <= len(pts) <= MAX_PTS):
        raise ImpossibleLayout([f"A plot needs 3 to {MAX_PTS} corners (got {len(pts)})"], ["Add or remove corners"])
    area2 = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    if abs(area2) < 1e6:
        raise ImpossibleLayout(["The corners enclose almost no area"], ["Check the corner order and units"])
    if area2 < 0:
        pts.reverse()
    n = len(pts)
    for i in range(n):
        if abs(pts[i][0] - pts[(i + 1) % n][0]) + abs(pts[i][1] - pts[(i + 1) % n][1]) < 1.0:
            raise ImpossibleLayout(["Two corners are at the same point"], ["Remove the duplicate corner"])
    for i in range(n):
        if _cross(pts[i], pts[(i + 1) % n], pts[(i + 2) % n]) < -1e-6:
            raise ImpossibleLayout(["This plot shape has an inward (concave) corner, for example an L-shaped plot"],
                                   ["Enter the largest convex part of the plot", "Or use the bounding rectangle and set larger open space on the cut-off sides"])
    x0 = min(p[0] for p in pts); y0 = min(p[1] for p in pts)
    return [[p[0] - x0, p[1] - y0] for p in pts]


def bbox(pts) -> tuple[float, float]:
    return max(p[0] for p in pts), max(p[1] for p in pts)


def frontage_depth(pts, road: str) -> tuple[float, float]:
    w, h = bbox(pts)
    return (w, h) if road in ("n", "s") else (h, w)


def _clip(poly, nx, ny, c):
    """Keep the part of a convex polygon where nx*x + ny*y <= c."""
    out = []
    for i, p in enumerate(poly):
        q = poly[(i + 1) % len(poly)]
        fp, fq = nx * p[0] + ny * p[1] - c, nx * q[0] + ny * q[1] - c
        if fp <= 0:
            out.append(p)
        if (fp < 0 < fq) or (fq < 0 < fp):
            t = fp / (fp - fq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def inset(pts, sb_world: dict) -> list:
    """Move every edge inward by the open space of the side it faces (slanted edges blend the two nearest sides)."""
    poly = [tuple(p) for p in pts]
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = (dx * dx + dy * dy) ** 0.5
        nx, ny = dy / L, -dx / L                       # outward normal for a counter-clockwise polygon
        d = abs(nx) * sb_world["e" if nx > 0 else "w"] + abs(ny) * sb_world["n" if ny > 0 else "s"]
        poly = _clip(poly, nx, ny, nx * a[0] + ny * a[1] - d)
        if len(poly) < 3:
            return []
    return poly


def _yrange(poly, x):
    ys = []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        if (p[0] - x) * (q[0] - x) <= 0 and p[0] != q[0]:
            t = (x - p[0]) / (q[0] - p[0]); ys.append(p[1] + t * (q[1] - p[1]))
        elif p[0] == q[0] == x:
            ys += [p[1], q[1]]
    return (min(ys), max(ys)) if ys else None


def best_rect(poly, steps: int = 140):
    xs = [p[0] for p in poly]; lo, hi = min(xs), max(xs)
    cand = sorted({lo + (hi - lo) * i / steps for i in range(steps + 1)} | set(xs))
    best, area = None, 0.0
    for i, xa in enumerate(cand):
        ra = _yrange(poly, xa)
        if not ra:
            continue
        for xb in cand[i + 1:]:
            rb = _yrange(poly, xb)
            if not rb:
                continue
            y0, y1 = max(ra[0], rb[0]), min(ra[1], rb[1])
            a = (xb - xa) * (y1 - y0)
            if y1 > y0 and a > area:
                best, area = (xa, y0, xb, y1), a
    return best


def fit(points, road: str, sb: dict) -> dict:
    """sb: front/rear/left/right open space in mm. Returns the polygon, the inset polygon, the fitted rectangle and the equivalent
    margins (front/rear/left/right) from the plot's bounding box to that rectangle."""
    pts = normalise(points)
    W, H = bbox(pts)
    world = {road: sb["front"], OPP[road]: sb["rear"], LEFT_OF[road]: sb["left"], OPP[LEFT_OF[road]]: sb["right"]}
    q = inset(pts, world)
    rect = best_rect(q) if q else None
    if not rect:
        raise ImpossibleLayout(["After the open space on each side, nothing is left to build on"], ["Reduce the open space values", "Check the corner coordinates"])
    import math
    x0, y0 = float(math.ceil(rect[0] - 1e-6)), float(math.ceil(rect[1] - 1e-6))          # round inward to whole mm
    x1, y1 = float(math.floor(rect[2] + 1e-6)), float(math.floor(rect[3] + 1e-6))
    m = {"w": x0, "e": W - x1, "s": y0, "n": H - y1}
    named = {"front": m[road], "rear": m[OPP[road]], "left": m[LEFT_OF[road]], "right": m[OPP[LEFT_OF[road]]]}
    return dict(polygon=pts, inset=[list(p) for p in q], rect=[x0, y0, x1, y1], margins=named, bbox=[W, H],
                area_plot=abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))) / 2,
                user_setbacks=dict(sb))
