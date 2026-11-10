"""Free-form floor plans designed by Claude. Claude chooses the rooms, their rectangles and how they connect;
this module validates every rule, derives walls/doors/windows/stairs and produces the canonical mm model.
Coordinates in a PlanSpec are wall-centreline mm in the plot-local frame: x along the road frontage (left to right
when looking in from the road), y away from the road, origin at the front-left corner of the buildable envelope."""
from __future__ import annotations

import math
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .layout import (ImpossibleLayout, effective_setbacks, local_to_world, refresh_walls, stair_flight)
from .model import Assumption, Brief, LayoutParams, Level, Opening, ProjectModel, Space, Stair

KINDS = ["living", "dining", "kitchen", "bedroom", "toilet", "store", "study", "entry", "stair", "parking", "sitout",
         "balcony", "passage", "pooja", "utility", "terrace"]
OPEN_KINDS = {"parking", "sitout", "balcony", "terrace"}      # no walls on edges that face outside
PRIVATE = {"bedroom", "toilet", "store", "study", "kitchen", "pooja", "utility"}
NEEDS_LIGHT = {"bedroom", "living", "kitchen", "study"}
GRID = 25.0
TOL = 1.0


class PlanRoom(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    name: str
    kind: Literal["living", "dining", "kitchen", "bedroom", "toilet", "store", "study", "entry", "stair", "parking", "sitout",
                  "balcony", "passage", "pooja", "utility", "terrace"]
    level: Literal["GF", "FF"] = "GF"
    x: float
    y: float
    w: float
    h: float


class PlanConn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    a: str
    b: str
    type: Literal["door", "open"] = "door"


class PlanSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rooms: list[PlanRoom]
    connections: list[PlanConn]
    entry_room: str
    rationale: str = ""


def envelope(brief: Brief, use_assumptions: bool, params: LayoutParams | None = None):
    """Buildable envelope (centreline) in the local frame: (BW, BD, setbacks, source, assumptions)."""
    if not (brief.plot_frontage_mm and brief.plot_depth_mm and brief.road_side):
        raise ImpossibleLayout(["Plot size and road side are required"], ["Provide plot size and the road-facing side"])
    sb, source, asm = effective_setbacks(brief, use_assumptions)
    t = (params or LayoutParams()).ext_t
    BW = brief.plot_frontage_mm - sb["left"] - sb["right"] - t
    BD = brief.plot_depth_mm - sb["front"] - sb["rear"] - t
    if BW < 3000 or BD < 3000:
        raise ImpossibleLayout([f"Buildable envelope is only {BW:.0f} x {BD:.0f} mm after open spaces"], ["Reduce the open space values", "Use a larger plot"])
    BW, BD = math.floor(BW / GRID) * GRID, math.floor(BD / GRID) * GRID   # whole 25 mm so Claude can tile exactly
    return BW, BD, sb, source, asm


def _snap(v: float) -> float:
    return round(v / GRID) * GRID


class _R:
    def __init__(self, r: PlanRoom):
        self.r = r
        self.key, self.level, self.kind = r.key, r.level, r.kind
        self.x, self.y = _snap(r.x), _snap(r.y)
        self.x2, self.y2 = _snap(r.x + r.w), _snap(r.y + r.h)

    @property
    def w(self): return self.x2 - self.x
    @property
    def h(self): return self.y2 - self.y


def _shared(a: _R, b: _R):
    """Shared wall segment between two rooms: ('h'|'v', c, lo, hi) or None."""
    if abs(a.y2 - b.y) < TOL or abs(b.y2 - a.y) < TOL:
        c = a.y2 if abs(a.y2 - b.y) < TOL else a.y
        lo, hi = max(a.x, b.x), min(a.x2, b.x2)
        if hi - lo > TOL:
            return ("h", c, lo, hi)
    if abs(a.x2 - b.x) < TOL or abs(b.x2 - a.x) < TOL:
        c = a.x2 if abs(a.x2 - b.x) < TOL else a.x
        lo, hi = max(a.y, b.y), min(a.y2, b.y2)
        if hi - lo > TOL:
            return ("v", c, lo, hi)
    return None


def _check(plan: PlanSpec, BW: float, BD: float, level_h: float):
    reasons: list[str] = []
    sugg: list[str] = []
    rooms = [_R(r) for r in plan.rooms]
    keys = [r.key for r in rooms]
    if len(set(keys)) != len(keys):
        raise ImpossibleLayout(["Room keys must be unique across all floors"], ["Rename duplicate keys (e.g. f_bed1 for first-floor rooms)"])
    if not any(r.level == "GF" for r in rooms):
        raise ImpossibleLayout(["The plan has no ground floor rooms"], ["Add ground floor rooms"])
    by_key = {r.key: r for r in rooms}
    for r in rooms:
        if r.w < 900 or r.h < 900:
            reasons.append(f"{r.r.name} ({r.key}) is {r.w:.0f} x {r.h:.0f} mm; every room must be at least 900 mm in both directions")
        if r.x < -TOL or r.y < -TOL or r.x2 > BW + TOL or r.y2 > BD + TOL:
            reasons.append(f"{r.r.name} ({r.key}) spans x {r.x:.0f}..{r.x2:.0f}, y {r.y:.0f}..{r.y2:.0f} but the buildable envelope is x 0..{BW:.0f}, y 0..{BD:.0f} mm")
    levels = sorted({r.level for r in rooms}, key=lambda l: ["GF", "FF"].index(l))
    boxes = {}
    for lv in levels:
        rs = [r for r in rooms if r.level == lv]
        xs = sorted({round(v, 3) for r in rs for v in (r.x, r.x2)})
        ys = sorted({round(v, 3) for r in rs for v in (r.y, r.y2)})
        boxes[lv] = (xs[0], ys[0], xs[-1], ys[-1])
        gaps, overs = [], []
        for x0, x1 in zip(xs, xs[1:]):
            for y0, y1 in zip(ys, ys[1:]):
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                n = [r for r in rs if r.x < cx < r.x2 and r.y < cy < r.y2]
                if not n:
                    gaps.append((x0, y0, x1, y1))
                elif len(n) > 1:
                    overs.append((x0, y0, x1, y1, [r.key for r in n]))
        name = "ground floor" if lv == "GF" else "first floor"
        for g in gaps[:4]:
            reasons.append(f"Gap on the {name}: nothing covers x {g[0]:.0f}..{g[2]:.0f}, y {g[1]:.0f}..{g[3]:.0f} mm. Rooms must tile one rectangle with no holes (extend a room or add a passage/store).")
        for o in overs[:4]:
            reasons.append(f"Overlap on the {name} at x {o[0]:.0f}..{o[2]:.0f}, y {o[1]:.0f}..{o[3]:.0f} mm between {' and '.join(o[4])}")
    if len(levels) == 2 and boxes["GF"] != boxes["FF"]:
        b0, b1 = boxes["GF"], boxes["FF"]
        reasons.append(f"The first floor footprint {b1} must equal the ground floor footprint {b0} (x0, y0, x1, y1 in mm). Use balcony/terrace rooms to fill unused first-floor area.")
    # connections
    adj: dict[str, set[str]] = {r.key: set() for r in rooms}
    for c in plan.connections:
        a, b = by_key.get(c.a), by_key.get(c.b)
        if not a or not b:
            reasons.append(f"Connection {c.a} - {c.b} refers to a room key that does not exist")
            continue
        if a.level != b.level:
            reasons.append(f"Connection {c.a} - {c.b} joins different floors; floors are linked by stair rooms with identical rectangles")
            continue
        seg = _shared(a, b)
        need = 1100 if c.type == "door" else 600
        if not seg or seg[3] - seg[2] < need:
            reasons.append(f"{a.r.name} ({c.a}) and {b.r.name} ({c.b}) do not share a wall at least {need:.0f} mm long, so a {c.type} cannot go between them")
            continue
        adj[c.a].add(c.b); adj[c.b].add(c.a)
    # stairs
    stairs = {lv: [r for r in rooms if r.level == lv and r.kind == "stair"] for lv in levels}
    for lv in levels:
        if len(stairs[lv]) > 1:
            reasons.append("Use only one stair room per floor")
    if len(levels) == 2:
        s0, s1 = (stairs["GF"] or [None])[0], (stairs["FF"] or [None])[0]
        if not s0 or not s1:
            reasons.append("A two-floor plan needs a stair room (kind 'stair') on both floors")
        elif (abs(s0.x - s1.x), abs(s0.y - s1.y), abs(s0.x2 - s1.x2), abs(s0.y2 - s1.y2)) != (0, 0, 0, 0):
            reasons.append("The first floor stair room must have exactly the same rectangle as the ground floor stair room")
        else:
            adj[s0.key].add(s1.key); adj[s1.key].add(s0.key)
    for lv in levels:
        for s in stairs[lv][:1]:
            try:
                stair_flight(s.w, s.h, level_h)
            except ImpossibleLayout as e:
                reasons.append(f"Stair room {s.key} ({s.w:.0f} x {s.h:.0f} mm): " + "; ".join(e.reasons))
                sugg += e.suggestions
    ent = by_key.get(plan.entry_room)
    if not ent or ent.level != "GF":
        reasons.append("entry_room must be a ground floor room key")
    # reachability
    if ent:
        seen, todo = {ent.key}, [ent.key]
        while todo:
            for n in adj[todo.pop()]:
                if n not in seen:
                    seen.add(n); todo.append(n)
        for r in rooms:
            if r.key not in seen:
                reasons.append(f"{r.r.name} ({r.key}) cannot be reached from the entry through doors/open connections/stairs; add a connection")
    return rooms, by_key, boxes, reasons, sugg


def _exterior_edges(r: _R, box):
    """Edges of room r lying on the outer boundary of its floor: list of (orient, c, lo, hi, outward_sign)."""
    x0, y0, x1, y1 = box
    out = []
    if abs(r.y - y0) < TOL: out.append(("h", r.y, r.x, r.x2, -1))
    if abs(r.y2 - y1) < TOL: out.append(("h", r.y2, r.x, r.x2, 1))
    if abs(r.x - x0) < TOL: out.append(("v", r.x, r.y, r.y2, -1))
    if abs(r.x2 - x1) < TOL: out.append(("v", r.x2, r.y, r.y2, 1))
    return out


def build_model_from_plan(brief: Brief, plan: PlanSpec, params: LayoutParams | None = None, overrides: dict | None = None,
                          use_assumptions: bool = False, roof_approved: bool = False) -> ProjectModel:
    p = (params or LayoutParams()).model_copy(deep=True)
    BW, BD, sb, source, asm = envelope(brief, use_assumptions, p)
    rooms, by_key, boxes, reasons, sugg = _check(plan, BW, BD, p.level_height)
    # exterior edge availability for rooms that need daylight
    for r in rooms:
        if r.kind in NEEDS_LIGHT and not any(e[3] - e[2] >= 900 for e in _exterior_edges(r, boxes[r.level])):
            reasons.append(f"{r.r.name} ({r.key}) has no outside wall of at least 900 mm, so it cannot get a window; move it to the building perimeter")
    ent = by_key.get(plan.entry_room)
    entry_edge = None
    if ent and not reasons:
        ex = [e for e in _exterior_edges(ent, boxes["GF"]) if e[3] - e[2] >= 1200]
        road = [e for e in ex if e[0] == "h" and e[4] == -1]
        pick = (road or sorted(ex, key=lambda e: -(e[3] - e[2])))
        if not pick:
            reasons.append(f"The entry room {ent.key} needs an outside wall at least 1200 mm long for the main door")
        else:
            entry_edge = pick[0]
    if reasons:
        raise ImpossibleLayout(reasons, sugg or ["Fix the listed problems and send the corrected plan"])
    # ---- spaces
    open_to: dict[str, list[str]] = {r.key: [] for r in rooms}
    for c in plan.connections:
        if c.type == "open":
            open_to[c.a].append(c.b); open_to[c.b].append(c.a)
    W, D = brief.plot_frontage_mm, brief.plot_depth_mm
    pt, vec, PWw, PHh = local_to_world(brief.road_side, W, D)
    bx0, by0 = sb["left"] + p.ext_t / 2, sb["front"] + p.ext_t / 2
    spaces = []
    for i, r in enumerate(rooms):
        x1, y1 = pt(bx0 + r.x, by0 + r.y); x2, y2 = pt(bx0 + r.x2, by0 + r.y2)
        spaces.append(Space(id=f"S{i+1:02d}", level=r.level, key=r.key, name=r.r.name, kind=r.kind,
                            x=min(x1, x2), y=min(y1, y2), w=abs(x2 - x1), h=abs(y2 - y1),
                            open_to=open_to[r.key], open_boundary=r.kind in OPEN_KINDS))
    levels = [Level(id="GF", name="Ground Floor", elevation=0.0, height=p.level_height)]
    if any(r.level == "FF" for r in rooms):
        levels.append(Level(id="FF", name="First Floor", elevation=p.level_height, height=p.level_height))
    model = ProjectModel(plot=dict(w=PWw, h=PHh, frontage=W, depth=D, road_side=brief.road_side, setbacks=sb, setback_source=source,
                                   local_origin=[bx0, by0], bw=BW, bd=BD),
                         levels=levels, spaces=spaces, params=p, opening_overrides=dict(overrides or {}),
                         assumptions=list(brief.assumptions) + asm, roof_approved=roof_approved, plan=plan.model_dump())
    # ---- openings
    ops: list[dict] = []
    order = {r.key: i for i, r in enumerate(rooms)}
    def add(key, typ, level, u, v, width, height, sill, swing, hinge="start", note="", rk=""):
        ops.append(dict(key=key, type=typ, level=level, u=u, v=v, width=width, height=height, sill=sill, swing=swing, hinge=hinge, note=note, ord=order.get(rk, 0)))
    # main entrance
    o, c, lo, hi, sgn = entry_edge
    mid = (lo + hi) / 2
    if o == "h":
        add("entry", "door", "GF", mid, c, 1000.0 if hi - lo >= 1500 else 900.0, 2100.0, 0.0, (0, -sgn), note="Main entrance", rk=ent.key)
    else:
        add("entry", "door", "GF", c, mid, 1000.0 if hi - lo >= 1500 else 900.0, 2100.0, 0.0, (-sgn, 0), note="Main entrance", rk=ent.key)
    for cn in plan.connections:
        if cn.type != "door":
            continue
        a, b = by_key[cn.a], by_key[cn.b]
        kind, c, lo, hi = _shared(a, b)
        # leaf swings into the more private room (smaller room if both or neither are private)
        pa, pb = a.kind in PRIVATE, b.kind in PRIVATE
        into = a if (pa and not pb) else b if (pb and not pa) else (a if a.w * a.h <= b.w * b.h else b)
        other = b if into is a else a
        width = 750.0 if "toilet" in (a.kind, b.kind) else 800.0 if "store" in (a.kind, b.kind) else 900.0
        width = min(width, hi - lo - 200)
        mid = (lo + hi) / 2
        if kind == "h":
            s = 1 if (into.y >= other.y2 - TOL) else -1
            add(f"door_{cn.a}_{cn.b}", "door", a.level, mid, c, width, 2100.0, 0.0, (0, s), rk=into.key)
        else:
            s = 1 if (into.x >= other.x2 - TOL) else -1
            add(f"door_{cn.a}_{cn.b}", "door", a.level, c, mid, width, 2100.0, 0.0, (s, 0), rk=into.key)
    # windows on the longest outside wall (a second one on a corner room's other wall)
    for r in rooms:
        if r.kind in OPEN_KINDS or r.kind in ("stair", "passage", "entry"):
            continue
        ex = sorted(_exterior_edges(r, boxes[r.level]), key=lambda e: -(e[3] - e[2]))
        if r.kind == "toilet":
            spec = (600.0, 450.0, 1500.0, 900.0)
        elif r.kind == "kitchen":
            spec = (1000.0, 1000.0, 1000.0, 1600.0)
        elif r.kind in ("store", "utility", "pooja"):
            spec = (600.0, 450.0, 1500.0, 900.0)
        else:
            spec = (1500.0, 1200.0, 900.0, 1500.0)
        for j, e in enumerate(ex[:2]):
            ln = e[3] - e[2]
            if ln < spec[3] or (j == 1 and r.kind not in ("bedroom", "living")) or (j == 1 and ln < 1800):
                continue
            # free stretches of this wall not taken by a door (keep 150 mm clear on each side)
            taken = sorted((o_["u"] if e[0] == "h" else o_["v"]) - o_["width"] / 2 - 150 for o_ in ops
                           if o_["level"] == r.level and abs((o_["v"] if e[0] == "h" else o_["u"]) - e[1]) < TOL
                           and e[2] - 1 <= (o_["u"] if e[0] == "h" else o_["v"]) <= e[3] + 1)
            spans = [((o_["u"] if e[0] == "h" else o_["v"]) - o_["width"] / 2 - 150, (o_["u"] if e[0] == "h" else o_["v"]) + o_["width"] / 2 + 150) for o_ in ops
                     if o_["level"] == r.level and abs((o_["v"] if e[0] == "h" else o_["u"]) - e[1]) < TOL
                     and e[2] - 1 <= (o_["u"] if e[0] == "h" else o_["v"]) <= e[3] + 1]
            free, cur = [], e[2]
            for a0, a1 in sorted(spans):
                if a0 > cur: free.append((cur, min(a0, e[3])))
                cur = max(cur, a1)
            if cur < e[3]: free.append((cur, e[3]))
            free = [f for f in free if f[1] - f[0] >= 600 + 200]
            if not free:
                continue
            f0, f1 = max(free, key=lambda f: f[1] - f[0])
            fl_ = f1 - f0
            wd = max(600.0, min(spec[0], fl_ - 700.0 if r.kind not in ("toilet", "store", "utility", "pooja") else spec[0], fl_ - 200))
            m = (f0 + f1) / 2
            key = f"win_{r.key}" if j == 0 else f"win_{r.key}_2"
            if e[0] == "h":
                add(key, "window", r.level, m, e[1], wd, spec[1], spec[2], (0, 1), rk=r.key)
            else:
                add(key, "window", r.level, e[1], m, wd, spec[1], spec[2], (0, 1), rk=r.key)
    li = {l.id: i for i, l in enumerate(levels)}
    di = wi = 0
    for o in sorted(ops, key=lambda o: (0 if o["type"] == "door" else 1, li[o["level"]], o["ord"], o["key"])):
        if o["type"] == "door":
            di += 1; mark = f"D{di}"
        else:
            wi += 1; mark = f"W{wi}"
        wx, wy = pt(bx0 + o["u"], by0 + o["v"])
        sx, sy = vec(*o["swing"])
        ov = (overrides or {}).get(o["key"], {})
        op = Opening(id=f"O-{o['key']}", key=o["key"], mark=mark, level=o["level"], type=o["type"], cx=wx, cy=wy,
                     width=ov.get("width", o["width"]), height=ov.get("height", o["height"]), sill=ov.get("sill", o["sill"]),
                     swing=[sx, sy], hinge=ov.get("hinge", o["hinge"]), note=o["note"])
        sh = ov.get("shift", 0.0)
        if sh:
            if abs(sx) > 0.5: op.cy += sh
            else: op.cx += sh
        model.openings.append(op)
    # ---- stairs: the up flight starts at the end nearest the door or opening that serves the stair
    for lv in levels:
        sr = next((r for r in rooms if r.level == lv.id and r.kind == "stair"), None)
        if not sr:
            continue
        sp = next(s for s in model.spaces if s.key == sr.key)
        fl = stair_flight(sp.w, sp.h, p.level_height)
        run_local = "y" if sr.h >= sr.w else "x"
        pos = None
        for cn in plan.connections:
            if sr.key in (cn.a, cn.b):
                other = by_key[cn.b if cn.a == sr.key else cn.a]
                seg = _shared(sr, other)
                if seg:
                    k, c, lo, hi = seg
                    pos = (c if k == "h" else (lo + hi) / 2) if run_local == "y" else (c if k == "v" else (lo + hi) / 2)
                    break
        lo_, hi_ = (sr.y, sr.y2) if run_local == "y" else (sr.x, sr.x2)
        at_high = (pos is not None) and abs(pos - hi_) < abs(pos - lo_) if pos is not None else True
        sv_local = ((0, 1) if at_high else (0, -1)) if run_local == "y" else ((1, 0) if at_high else (-1, 0))
        sv = vec(*sv_local)
        run = "y" if sp.h >= sp.w else "x"
        model.stairs.append(Stair(id="ST1" if lv.id == "GF" else "ST2", level=lv.id, space_id=sp.id, x=sp.x, y=sp.y, w=sp.w, h=sp.h,
                                  run_axis=run, flight=fl, start=[float(sv[0]), float(sv[1])]))
    refresh_walls(model)
    return model
