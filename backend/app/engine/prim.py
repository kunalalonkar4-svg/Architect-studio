"""Vector drawing primitives. View coordinates are model millimetres; text height,
line weight and dash lengths are in PAPER millimetres (so annotation stays legible at any scale)."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

# layer -> (ACI colour for DXF, (r,g,b) 0-1 for PDF/SVG, lineweight paper mm, description)
LAYERS = {
    "A-WALL": (7, (0.10, 0.10, 0.10), 0.35, "Walls (cut)"),
    "A-WALL-PARAPET": (7, (0.10, 0.10, 0.10), 0.25, "Parapet"),
    "A-DOOR": (3, (0.0, 0.0, 0.0), 0.18, "Doors and swings"),
    "A-GLAZ": (5, (0.0, 0.0, 0.0), 0.15, "Windows / glazing"),
    "A-STAIR": (6, (0.0, 0.0, 0.0), 0.15, "Stairs"),
    "A-FURN": (8, (0.35, 0.35, 0.35), 0.10, "Fixtures and furniture"),
    "A-ANNO-DIMS": (1, (0.0, 0.0, 0.0), 0.10, "Dimensions"),
    "A-ANNO-TEXT": (7, (0.0, 0.0, 0.0), 0.13, "Text and labels"),
    "A-ANNO-SYMB": (2, (0.0, 0.0, 0.0), 0.15, "Symbols, tags, markers"),
    "A-GRID": (4, (0.45, 0.45, 0.45), 0.08, "Reference axes"),
    "A-SITE-BNDY": (1, (0.0, 0.0, 0.0), 0.35, "Plot boundary"),
    "A-SITE-SETB": (30, (0.5, 0.0, 0.0), 0.15, "Setback lines"),
    "A-SITE-BLDG": (7, (0.0, 0.0, 0.0), 0.30, "Building footprint"),
    "A-SITE-MISC": (8, (0.4, 0.4, 0.4), 0.12, "Road / parking / open areas"),
    "A-ELEV-OUT": (7, (0.0, 0.0, 0.0), 0.35, "Elevation outline"),
    "A-ELEV-OPEN": (3, (0.0, 0.0, 0.0), 0.15, "Elevation openings"),
    "A-ELEV-GRND": (7, (0.0, 0.0, 0.0), 0.50, "Ground line"),
    "A-SECT-CUT": (7, (0.10, 0.10, 0.10), 0.40, "Section cut elements"),
    "A-SECT-BEYOND": (8, (0.35, 0.35, 0.35), 0.12, "Section elements beyond"),
    "A-ROOF": (7, (0.0, 0.0, 0.0), 0.30, "Roof / terrace"),
    "A-SCALE": (2, (0.0, 0.0, 0.0), 0.25, "Graphic scale bar (6 m test segment)"),
    "A-SHEET": (7, (0.0, 0.0, 0.0), 0.35, "Sheet frame, title block"),
    "A-TABLE": (7, (0.0, 0.0, 0.0), 0.18, "Schedule tables"),
}

EM = 1.3     # font size (em) = text height h * EM
CW = 0.72    # average glyph advance = h * CW

DASH = {"cont": [], "dash": [2.5, 1.2], "center": [8.0, 1.5, 1.5, 1.5], "hidden": [1.5, 1.0]}


@dataclass
class Line:
    x1: float; y1: float; x2: float; y2: float
    layer: str = "A-ANNO-DIMS"; lt: str = "cont"; w: Optional[float] = None
    kind: str = "line"


@dataclass
class Poly:
    pts: list
    layer: str = "A-WALL"; closed: bool = True; fill: Optional[str] = None  # None|'wall'|'light'|'mid'|'glass'
    lt: str = "cont"; w: Optional[float] = None
    kind: str = "poly"


@dataclass
class Arc:
    cx: float; cy: float; r: float; a0: float; a1: float  # degrees, counter-clockwise a0->a1
    layer: str = "A-DOOR"; lt: str = "cont"; w: Optional[float] = None
    kind: str = "arc"


@dataclass
class Circle:
    cx: float; cy: float; r: float
    layer: str = "A-ANNO-SYMB"; fill: Optional[str] = None; w: Optional[float] = None
    kind: str = "circle"


@dataclass
class Text:
    x: float; y: float; s: str
    h: float = 2.5                    # paper mm
    layer: str = "A-ANNO-TEXT"; anchor: str = "l"   # l|c|r
    valign: str = "b"                  # b|m|t
    rot: float = 0.0; bold: bool = False
    kind: str = "text"


Prim = Line | Poly | Arc | Circle | Text


@dataclass
class ViewResult:
    """A view built in model space at a particular scale denominator."""
    id: str
    title: str
    prims: list
    bbox: tuple          # (xmin, ymin, xmax, ymax) model mm including annotations
    scale: int           # denominator; 0 means NTS / paper units
    meta: dict = field(default_factory=dict)
    caption_scale: bool = True


def bbox_of(prims: list, S: float) -> tuple:
    xs, ys = [], []
    for p in prims:
        if p.kind == "line":
            xs += [p.x1, p.x2]; ys += [p.y1, p.y2]
        elif p.kind == "poly":
            for x, y in p.pts:
                xs.append(x); ys.append(y)
        elif p.kind in ("arc", "circle"):
            r = p.r
            xs += [p.cx - r, p.cx + r]; ys += [p.cy - r, p.cy + r]
        elif p.kind == "text":
            w = len(p.s) * p.h * CW * S
            hh = p.h * S
            rot = p.rot % 180
            if rot == 90:
                w, hh = hh, w
            if p.anchor == "c":
                xs += [p.x - w / 2, p.x + w / 2]
            elif p.anchor == "r":
                xs += [p.x - w, p.x]
            else:
                xs += [p.x, p.x + w]
            ys += [p.y - (hh if p.valign == "t" else 0) - (hh / 2 if p.valign == "m" else 0),
                   p.y + (hh if p.valign == "b" else hh / 2 if p.valign == "m" else 0)]
    if not xs:
        return (0, 0, 1, 1)
    return (min(xs), min(ys), max(xs), max(ys))


def to_dict(p) -> dict:
    return asdict(p)


def transform(prims: list, S: float, ox: float, oy: float, bx0: float, by0: float) -> list:
    """Map model-space prims to paper space (mm): p = o + (m - b0)/S. Text/line weights stay in paper mm."""
    k = 1.0 / S if S else 1.0
    out = []
    for p in prims:
        q = _copy(p)
        if q.kind == "line":
            q.x1 = ox + (q.x1 - bx0) * k; q.x2 = ox + (q.x2 - bx0) * k
            q.y1 = oy + (q.y1 - by0) * k; q.y2 = oy + (q.y2 - by0) * k
        elif q.kind == "poly":
            q.pts = [(ox + (x - bx0) * k, oy + (y - by0) * k) for x, y in q.pts]
        elif q.kind in ("arc", "circle"):
            q.cx = ox + (q.cx - bx0) * k; q.cy = oy + (q.cy - by0) * k; q.r = q.r * k
        elif q.kind == "text":
            q.x = ox + (q.x - bx0) * k; q.y = oy + (q.y - by0) * k
        out.append(q)
    return out


def _copy(p):
    import copy
    return copy.copy(p)
