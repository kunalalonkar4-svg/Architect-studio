"""Sheet composition: paper sizes, scale, title block, viewport packing, overflow detection."""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import ProjectModel, SheetDef, ViewDef
from .prim import Line, Poly, Text, ViewResult, transform, to_dict
from .views import build_view
from .model import digest

PAPERS = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0), "A1": (841.0, 594.0), "A0": (1189.0, 841.0)}
SCALES = [20, 25, 50, 100, 200, 500]
TABLE_KINDS = {"schedules", "index", "rooms", "openings"}
STATUS_TEXT = "CONCEPT DRAFT — NOT REVIEWED. No signature, stamp or authority approval is implied."


class SheetOverflow(Exception):
    def __init__(self, sheet_number, needed, avail, suggestions):
        super().__init__(f"Sheet {sheet_number}: drawing needs {needed[0]:.0f} x {needed[1]:.0f} mm but only {avail[0]:.0f} x {avail[1]:.0f} mm is available")
        self.sheet_number, self.needed, self.avail, self.suggestions = sheet_number, needed, avail, suggestions


@dataclass
class SheetResult:
    sheet_id: str
    number: str
    title: str
    paper: str
    orientation: str
    size: tuple
    scale: int
    prims: list                      # paper-space prims
    placed: list                     # [{view, result, ox, oy}]
    meta: dict = field(default_factory=dict)
    logo: dict | None = None          # {"data": bytes, "mime": str, "x","y","w","h"}


def paper_size(paper: str, orientation: str) -> tuple:
    w, h = PAPERS[paper]
    return (w, h) if orientation == "landscape" else (h, w)


def frame_geometry(W, H):
    fx0, fy0, fx1, fy1 = 15.0, 8.0, W - 8.0, H - 8.0
    tb = 70.0 if W >= 280 else 58.0
    area = (fx0 + 4, fy0 + 4, fx1 - tb - 4, fy1 - 4)
    return (fx0, fy0, fx1, fy1), tb, area


def _pack(items, area, gap=6.0, cap_h=9.0):
    """Shelf-pack rectangles (w,h) top-left -> returns list of (x,y_bottom) or None if it doesn't fit."""
    ax0, ay0, ax1, ay1 = area
    x, y_top, row_h = ax0, ay1, 0.0
    out = []
    for w, h in items:
        h2 = h + cap_h
        if w > ax1 - ax0 + 1e-6 or h2 > ay1 - ay0 + 1e-6:
            return None
        if x + w > ax1 + 1e-6:
            x = ax0; y_top -= row_h + gap; row_h = 0.0
        if y_top - h2 < ay0 - 1e-6:
            return None
        out.append((x, y_top - h2))
        x += w + gap
        row_h = max(row_h, h2)
    return out


def _views_for(model: ProjectModel, sd: SheetDef):
    return [next(v for v in model.views if v.id == vid) for vid in sd.views]


def build_sheet_views(model: ProjectModel, sd: SheetDef, scale: int, project: dict) -> list[ViewResult]:
    out = []
    for vd in _views_for(model, sd):
        S = 1 if vd.type in TABLE_KINDS else scale
        out.append(build_view(model, vd, S, project))
    return out


def sheet_signature(model: ProjectModel, sd: SheetDef, project: dict, with_titleblock: bool = False) -> str:
    """Content signature of a sheet. Without the title block it decides whether the sheet's revision
    label advances; with it, whether a stored render can be reused."""
    sc = 0 if sd.kind in TABLE_KINDS else (sd.scale or 100)
    vs = build_sheet_views(model, sd, sc or 1, project)
    payload = [[to_dict(p) for p in v.prims] for v in vs]
    extra = [project.get("title_block_sig"), project.get("sheet_rev", {}).get(sd.number)] if with_titleblock else None
    return digest([sd.model_dump(), payload, extra])


def _fits(views, W, H, S_of):
    _, tb, area = frame_geometry(W, H)
    items = []
    for v in views:
        bw = (v.bbox[2] - v.bbox[0]) / (v.scale or 1)
        bh = (v.bbox[3] - v.bbox[1]) / (v.scale or 1)
        items.append((bw, bh))
    return _pack(items, area), items, area


def compose_sheet(model: ProjectModel, sd: SheetDef, project: dict, paper: str | None = None,
                  scale: int | None = None, orientation: str | None = None) -> SheetResult:
    paper = paper or sd.paper
    orientation = orientation or sd.orientation
    table_sheet = sd.kind in TABLE_KINDS
    sc = 0 if table_sheet else (scale or sd.scale or 100)
    views = build_sheet_views(model, sd, sc or 1, project)
    W, H = paper_size(paper, orientation)
    pos, items, area = _fits(views, W, H, sc)
    if pos is None:
        needed = (max(i[0] for i in items), sum(i[1] + 9 for i in items)) if len(items) > 1 else (items[0][0], items[0][1] + 9)
        sug = []
        names = list(PAPERS)
        for pn in names[names.index(paper) + 1:] if paper in names else []:
            ww, hh = paper_size(pn, orientation)
            if _fits(views, ww, hh, sc)[0] is not None:
                sug.append({"kind": "paper", "value": pn, "text": f"Use a larger sheet: {pn}"}); break
        if not table_sheet:
            for s2 in SCALES:
                if s2 <= sc:
                    continue
                v2 = build_sheet_views(model, sd, s2, project)
                if _fits(v2, W, H, s2)[0] is not None:
                    sug.append({"kind": "scale", "value": s2, "text": f"Use a smaller scale: 1:{s2} on {paper}"}); break
        if len(views) > 1:
            sug.append({"kind": "split", "value": "split", "text": "Split the sheet: one view per sheet"})
        raise SheetOverflow(sd.number, needed, (area[2] - area[0], area[3] - area[1]), sug)
    prims: list = []
    placed = []
    meta = {}
    for v, (px, py), (bw, bh) in zip(views, pos, items):
        # centre single views inside the free area
        ox, oy = px, py
        if len(views) == 1:
            ox = area[0] + (area[2] - area[0] - bw) / 2
            oy = area[1] + (area[3] - area[1] - (bh + 9)) / 2
        S = v.scale or 1
        prims += transform(v.prims, S, ox, oy, v.bbox[0], v.bbox[1])
        cap_y = oy + bh + 2.5
        cap = v.title + (f"      SCALE 1:{S}" if v.scale else "      NOT TO SCALE")
        prims.append(Text(ox, cap_y, cap, 3.2, "A-ANNO-TEXT", "l", "b", 0, True))
        prims.append(Line(ox, cap_y - 0.8, ox + min(bw, 160), cap_y - 0.8, "A-ANNO-TEXT", "cont", 0.5))
        placed.append(dict(view=v.id, result=v, ox=ox, oy=oy, bw=bw, bh=bh))
        meta[v.id] = v.meta
    sh = SheetResult(sd.id, sd.number, sd.title, paper, orientation, (W, H), sc, prims, placed, meta)
    _frame_and_title(sh, sd, project, paper, sc)
    return sh


def _frame_and_title(sh: SheetResult, sd: SheetDef, project: dict, paper: str, sc: int):
    W, H = sh.size
    (fx0, fy0, fx1, fy1), tb, _ = frame_geometry(W, H)
    P = sh.prims
    P.append(Poly([(5, 5), (W - 5, 5), (W - 5, H - 5), (5, H - 5)], "A-SHEET", True, None, "cont", 0.25))
    P.append(Poly([(fx0, fy0), (fx1, fy0), (fx1, fy1), (fx0, fy1)], "A-SHEET", True, None, "cont", 0.7))
    tx = fx1 - tb
    P.append(Line(tx, fy0, tx, fy1, "A-SHEET", "cont", 0.5))
    y = fy1
    def cell(h_, label=None, value=None, vh=2.6, bold=False, lines=None):
        nonlocal y
        P.append(Line(tx, y - h_, fx1, y - h_, "A-SHEET", "cont", 0.25))
        if label:
            P.append(Text(tx + 1.5, y - 1.2, label, 1.6, "A-SHEET", "l", "t"))
        if value is not None:
            P.append(Text(tx + 1.5, y - h_ + 1.8, value, vh, "A-SHEET", "l", "b", 0, bold))
        if lines:
            yy = y - 4.2
            for ln, hh, bd in lines:
                P.append(Text(tx + 1.5, yy, ln, hh, "A-SHEET", "l", "t", 0, bd)); yy -= hh * 1.55
        y -= h_
    from .views import _wrap
    # firm / logo
    lh = 22.0
    cell(lh)
    firm = project.get("firm_name") or "Studio"
    if project.get("logo"):
        sh.logo = dict(data=project["logo"]["data"], mime=project["logo"]["mime"], x=tx + 2, y=y + 2.0, w=22.0, h=lh - 4)
        P.append(Text(tx + 27, y + lh - 6, firm[:28], 3.0, "A-SHEET", "l", "t", 0, True))
        if project.get("firm_line"):
            P.append(Text(tx + 27, y + lh - 12, project["firm_line"][:34], 1.9, "A-SHEET", "l", "t"))
    else:
        P.append(Text(tx + 2, y + lh - 6, firm[:30], 3.4, "A-SHEET", "l", "t", 0, True))
        if project.get("firm_line"):
            P.append(Text(tx + 2, y + lh - 13, project["firm_line"][:38], 1.9, "A-SHEET", "l", "t"))
    cell(14, "PROJECT", (project.get("project_name") or "Untitled")[:30], 3.0, True)
    cell(10, "CLIENT / SITE", (project.get("client") or "—")[:36], 2.2)
    wrapped = _wrap(project.get("address") or "—", tb - 4, 2.0)[:2]
    cell(10, "ADDRESS", None, lines=[(w_, 2.0, False) for w_ in wrapped])
    tl = _wrap(sd.title.upper(), tb - 4, 3.0)[:3]
    cell(18, "DRAWING TITLE", None, lines=[(w_, 3.0, True) for w_ in tl])
    half = tb / 2
    cell(10, "SHEET NO.", sd.number, 4.0, True)
    cell(10, "SCALE", ("NOT TO SCALE" if not sc else f"1:{sc}"), 2.8, True)
    cell(10, "PAPER / PRINT", f"{paper} {sh.orientation}  •  Actual Size", 2.1)
    cell(10, "DATE", project.get("date", ""), 2.4)
    rev = project.get("sheet_rev", {}).get(sd.number, project.get("revision", "0"))
    cell(10, "REVISION", f"Rev {rev}", 2.8, True)
    hist = project.get("revision_history", [])[-4:]
    ln = [(f"{r['n']}  {r['date']}  {r['text'][:30]}", 1.7, False) for r in hist] or [("—", 1.7, False)]
    cell(8 + 3.1 * len(ln), "REVISION HISTORY", None, lines=ln)
    st = _wrap(STATUS_TEXT, tb - 4, 1.8)
    cell(4 + 3.0 * len(st) + 3, "STATUS / REVIEW", None, lines=[(w_, 1.8, False) for w_ in st])
    ps = _wrap(f"Print on {paper} ({W:.0f} x {H:.0f} mm) at 100% / Actual Size. Do not 'Fit to page'.", tb - 4, 1.8)
    cell(4 + 3.0 * len(ps) + 3, "PRINT INSTRUCTIONS", None, lines=[(w_, 1.8, False) for w_ in ps])
    pr = _wrap("AI-assisted concept draft generated by AI Architect Studio. Not a signed or stamped drawing.", tb - 4, 1.7)
    cell(4 + 2.8 * len(pr) + 3, None, None, lines=[(w_, 1.7, False) for w_ in pr])
