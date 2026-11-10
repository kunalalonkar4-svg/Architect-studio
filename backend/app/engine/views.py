"""View builders: every view is generated from the single ProjectModel (no images)."""
from __future__ import annotations

import math
from typing import Optional

from .layout import clear_rect, room_metrics, wall_offset, AREA_METHOD
from .model import ProjectModel, ViewDef, SIDE_NAMES, Space, Wall, Opening
from .prim import Arc, Circle, Line, Poly, Text, ViewResult, bbox_of, CW
from ..units import fmt_ft_in


class B:
    """Primitive builder for one view at scale denominator S (1 for tables)."""

    def __init__(self, S: float):
        self.S = float(S) or 1.0
        self.prims: list = []

    def p(self, mm: float) -> float:       # paper mm -> model mm
        return mm * self.S

    def line(self, x1, y1, x2, y2, layer="A-ANNO-DIMS", lt="cont", w=None):
        self.prims.append(Line(x1, y1, x2, y2, layer, lt, w))

    def poly(self, pts, layer="A-WALL", closed=True, fill=None, lt="cont", w=None):
        self.prims.append(Poly([tuple(p) for p in pts], layer, closed, fill, lt, w))

    def rect(self, x1, y1, x2, y2, layer, fill=None, lt="cont", w=None):
        self.poly([(x1, y1), (x2, y1), (x2, y2), (x1, y2)], layer, True, fill, lt, w)

    def arc(self, cx, cy, r, a0, a1, layer="A-DOOR", lt="cont", w=None):
        self.prims.append(Arc(cx, cy, r, a0, a1, layer, lt, w))

    def circle(self, cx, cy, r, layer="A-ANNO-SYMB", fill=None, w=None):
        self.prims.append(Circle(cx, cy, r, layer, fill, w))

    def text(self, x, y, s, h=2.5, layer="A-ANNO-TEXT", anchor="l", valign="b", rot=0.0, bold=False):
        self.prims.append(Text(x, y, s, h, layer, anchor, valign, rot, bold))

    # ---- dimensions -------------------------------------------------
    def dim_h(self, x1, x2, y_feat, y_line, txt=None, h=2.2, rotate=False):
        sgn = 1 if y_line >= y_feat else -1
        self.line(x1, y_feat + sgn * self.p(1.0), x1, y_line + sgn * self.p(1.5))
        self.line(x2, y_feat + sgn * self.p(1.0), x2, y_line + sgn * self.p(1.5))
        self.line(x1, y_line, x2, y_line)
        for x in (x1, x2):
            self.line(x - self.p(0.9), y_line - self.p(0.9), x + self.p(0.9), y_line + self.p(0.9), w=0.25)
        t = txt if txt is not None else f"{abs(x2 - x1):.0f}"
        narrow = abs(x2 - x1) / self.S < len(t) * h * CW + 1.2
        if narrow or rotate:
            self.text((x1 + x2) / 2, y_line + sgn * self.p(0.8), t, min(h, 1.8), anchor="l" if sgn > 0 else "r", valign="m", rot=90)
        else:
            self.text((x1 + x2) / 2, y_line + (self.p(0.7) if sgn > 0 else -self.p(0.7) - self.p(h)), t, h, anchor="c")

    def dim_v(self, y1, y2, x_feat, x_line, txt=None, h=2.2):
        sgn = 1 if x_line >= x_feat else -1
        self.line(x_feat + sgn * self.p(1.0), y1, x_line + sgn * self.p(1.5), y1)
        self.line(x_feat + sgn * self.p(1.0), y2, x_line + sgn * self.p(1.5), y2)
        self.line(x_line, y1, x_line, y2)
        for y in (y1, y2):
            self.line(x_line - self.p(0.9), y - self.p(0.9), x_line + self.p(0.9), y + self.p(0.9), w=0.25)
        t = txt if txt is not None else f"{abs(y2 - y1):.0f}"
        self.text(x_line - sgn * self.p(0.8), (y1 + y2) / 2, t, min(h, 2.2), anchor="c", valign="b" if sgn < 0 else "t", rot=90)

    def bubble(self, x, y, label, r=3.2):
        self.circle(x, y, self.p(r), "A-GRID")
        self.text(x, y, label, 2.4, "A-GRID", "c", "m", bold=True)

    def level_mark(self, x, y, label, side=1):
        a = self.p(1.8)
        self.poly([(x, y), (x - a, y + a * 1.5), (x + a, y + a * 1.5)], "A-ANNO-SYMB", True, None)
        self.line(x - self.p(6), y, x + self.p(14), y, "A-ANNO-SYMB", w=0.15)
        self.text(x + self.p(2.8), y + self.p(0.6), label, 2.2, anchor="l")

    def north_arrow(self, x, y, r=7.0):
        R = self.p(r)
        self.circle(x, y, R, "A-ANNO-SYMB")
        self.poly([(x, y + R), (x - R * 0.45, y - R * 0.7), (x, y - R * 0.3), (x + R * 0.45, y - R * 0.7)], "A-ANNO-SYMB", True, "mid")
        self.text(x, y + R + self.p(1.0), "N", 3.2, anchor="c", bold=True)

    def scale_bar(self, x, y, S):
        total = 6000.0 if S >= 50 else 3000.0
        step = total / 6 if total == 6000 else total / 3
        h = self.p(1.6)
        self.line(x, y, x + total, y, "A-SCALE", w=0.35)          # the 6 m / 3 m calibration segment
        i = 0
        v = 0.0
        while v < total - 1e-6:
            if i % 2 == 0:
                self.rect(x + v, y, x + v + step, y + h, "A-SCALE", "mid")
            else:
                self.rect(x + v, y, x + v + step, y + h, "A-SCALE")
            i += 1; v += step
        n = int(round(total / step))
        for k in range(n + 1):
            xx = x + k * step
            self.line(xx, y, xx, y + h + self.p(0.8), "A-SCALE", w=0.15)
            self.text(xx, y + h + self.p(1.2), f"{k * step / 1000:g}", 1.8, anchor="c")
        self.text(x + total + self.p(3), y, "m", 1.8, anchor="l")
        self.text(x, y - self.p(4), f"GRAPHIC SCALE  1:{int(S)}  (bar = {total:.0f} mm)", 1.9, anchor="l", valign="t")


def _unit(v):
    n = math.hypot(*v) or 1.0
    return (v[0] / n, v[1] / n)


def _wall_dir(w: Wall):
    return (1.0, 0.0) if w.horizontal else (0.0, 1.0)


def _opening_gaps(model: ProjectModel, w: Wall):
    out = []
    for o in model.openings:
        if o.host == w.id:
            c = (o.cx - min(w.x1, w.x2)) if w.horizontal else (o.cy - min(w.y1, w.y2))
            out.append((c - o.width / 2, c + o.width / 2, o))
    return sorted(out, key=lambda g: g[0])


def draw_walls_plan(b: B, model: ProjectModel, level="GF"):
    for w in model.walls:
        if w.level != level:
            continue
        d = _wall_dir(w)
        n = (-d[1], d[0])
        L = w.length
        ox, oy = min(w.x1, w.x2), min(w.y1, w.y2)
        t2 = w.thickness / 2
        pts_along = []
        cur = 0.0
        for g0, g1, o in _opening_gaps(model, w):
            if g0 > cur + 0.5:
                pts_along.append((cur, g0))
            cur = max(cur, g1)
        if cur < L - 0.5:
            pts_along.append((cur, L))
        for a, c in pts_along:
            a2 = a - (t2 if a <= 0.5 else 0)
            c2 = c + (t2 if c >= L - 0.5 else 0)
            P = lambda s, off: (ox + d[0] * s + n[0] * off, oy + d[1] * s + n[1] * off)
            b.poly([P(a2, -t2), P(c2, -t2), P(c2, t2), P(a2, t2)], "A-WALL", True, "wall")
        # jamb end lines are implied by polygons


def draw_openings_plan(b: B, model: ProjectModel):
    for o in model.openings:
        w = next((x for x in model.walls if x.id == o.host), None)
        if not w:
            continue
        d = _wall_dir(w)
        n = (-d[1], d[0])
        t2 = w.thickness / 2
        c = (o.cx, o.cy)
        s0 = (c[0] - d[0] * o.width / 2, c[1] - d[1] * o.width / 2)
        s1 = (c[0] + d[0] * o.width / 2, c[1] + d[1] * o.width / 2)
        if o.type == "window":
            for off in (-t2, -t2 / 3, t2 / 3, t2):
                b.line(s0[0] + n[0] * off, s0[1] + n[1] * off, s1[0] + n[0] * off, s1[1] + n[1] * off, "A-GLAZ")
        else:
            hinge = s0 if o.hinge == "start" else s1
            other = s1 if o.hinge == "start" else s0
            sw = _unit(o.swing)
            leaf_end = (hinge[0] + sw[0] * o.width, hinge[1] + sw[1] * o.width)
            # leaf as a thin rectangle for readability
            lt = b.p(0.5)
            b.line(hinge[0], hinge[1], leaf_end[0], leaf_end[1], "A-DOOR", w=0.25)
            jd = _unit((other[0] - hinge[0], other[1] - hinge[1]))
            aj = math.degrees(math.atan2(jd[1], jd[0])) % 360
            al = math.degrees(math.atan2(sw[1], sw[0])) % 360
            if abs(((al - aj) % 360) - 90) < 1:
                b.arc(hinge[0], hinge[1], o.width, aj, aj + 90)
            else:
                b.arc(hinge[0], hinge[1], o.width, al, al + 90)
            for s in (s0, s1):   # door frame ticks
                b.line(s[0] - n[0] * t2, s[1] - n[1] * t2, s[0] + n[0] * t2, s[1] + n[1] * t2, "A-DOOR", w=0.18)
        # tag
        side = -1 if o.type == "window" else 1
        sw = _unit(o.swing) if o.type == "door" else n
        if o.type == "door":
            tag = (c[0] + sw[0] * (o.width * 0.5 + b.p(4.0)), c[1] + sw[1] * (o.width * 0.5 + b.p(4.0)))
            tag = (c[0] + sw[0] * (o.width + b.p(3.2)), c[1] + sw[1] * (o.width + b.p(3.2)))
        else:
            ext = _exterior_normal(model, w, o)
            tag = (c[0] + ext[0] * (t2 + b.p(4.0)), c[1] + ext[1] * (t2 + b.p(4.0)))
        b.circle(tag[0], tag[1], b.p(2.4), "A-ANNO-SYMB")
        b.text(tag[0], tag[1], o.mark, 1.7, "A-ANNO-SYMB", "c", "m")


def _exterior_normal(model: ProjectModel, w: Wall, o: Opening):
    fp = model.footprint()
    d = _wall_dir(w); n = (-d[1], d[0])
    cx = (fp[0] + fp[2]) / 2; cy = (fp[1] + fp[3]) / 2
    v = (o.cx - cx, o.cy - cy)
    return n if (n[0] * v[0] + n[1] * v[1]) >= 0 else (-n[0], -n[1])


def draw_stair_plan(b: B, model: ProjectModel):
    for st in model.stairs:
        f = st.flight
        if not f:
            continue
        x0, y0, x1, y1 = st.x, st.y, st.x + st.w, st.y + st.h
        sp = next((s for s in model.spaces if s.id == st.space_id), None)
        cx0, cy0, cx1, cy1 = clear_rect(model, sp) if sp else (x0, y0, x1, y1)
        along = st.run_axis
        # local frame: u along run (towards far end), v across
        if along == "y":
            run0, run1, acr0, acr1 = cy0, cy1, cx0, cx1
        else:
            run0, run1, acr0, acr1 = cx0, cx1, cy0, cy1
        sv = st.start[1] if along == "y" else st.start[0]
        start_at_low = sv < 0
        gap = (acr1 - acr0) - 2 * f.flight_width
        T = f.treads_per_flight
        def P(u, v):  # u = distance from start end along run, v = distance across from acr0
            run = run0 + u if start_at_low else run1 - u
            return (acr0 + v, run) if along == "y" else (run, acr0 + v)
        # flight 1 (up): v in [0, fw]
        for i in range(T + 1):
            u = i * f.tread_mm
            a = P(u, 0); c = P(u, f.flight_width)
            b.line(a[0], a[1], c[0], c[1], "A-STAIR")
        for (va, vb) in ((0, 0), (f.flight_width, f.flight_width)):
            a = P(0, va); c = P(T * f.tread_mm, vb)
            b.line(a[0], a[1], c[0], c[1], "A-STAIR")
        # landing
        lu0, lu1 = T * f.tread_mm, T * f.tread_mm + f.landing
        pl = [P(lu0, 0), P(lu0, acr1 - acr0), P(lu1, acr1 - acr0), P(lu1, 0)]
        b.poly(pl, "A-STAIR", True, None)
        # flight 2 (return): v in [fw+gap, 2fw+gap]
        v0 = acr1 - acr0 - f.flight_width
        for i in range(T + 1):
            u = lu1 - (i * f.tread_mm) - f.landing + f.landing
            u = T * f.tread_mm - i * f.tread_mm
            a = P(u, v0); c = P(u, v0 + f.flight_width)
            b.line(a[0], a[1], c[0], c[1], "A-STAIR", lt="dash")
        for vv in (v0, v0 + f.flight_width):
            a = P(0, vv); c = P(T * f.tread_mm, vv)
            b.line(a[0], a[1], c[0], c[1], "A-STAIR", lt="dash")
        # arrow
        a = P(0.0, f.flight_width / 2); c = P(T * f.tread_mm + f.landing * 0.5, f.flight_width / 2)
        b.line(a[0], a[1], c[0], c[1], "A-STAIR", w=0.25)
        d = _unit((c[0] - a[0], c[1] - a[1])); nrm = (-d[1], d[0]); hs = b.p(2.2)
        b.poly([c, (c[0] - d[0] * hs * 1.6 + nrm[0] * hs * .6, c[1] - d[1] * hs * 1.6 + nrm[1] * hs * .6),
                (c[0] - d[0] * hs * 1.6 - nrm[0] * hs * .6, c[1] - d[1] * hs * 1.6 - nrm[1] * hs * .6)], "A-STAIR", True, "mid")
        b.text(a[0] + nrm[0] * b.p(3), a[1] + nrm[1] * b.p(3), "UP", 1.8, "A-STAIR", "c", "m", rot=0)


def _door_for(model: ProjectModel, key: str):
    for o in model.openings:
        if o.type == "door" and key in (o.from_space, o.to_space):
            return o
    return None


def draw_furniture(b: B, model: ProjectModel):
    for s in model.spaces:
        x0, y0, x1, y1 = clear_rect(model, s)
        w, h = x1 - x0, y1 - y0
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if s.kind in ("bedroom", "study"):
            door = _door_for(model, s.key)
            dx, dy = (door.cx, door.cy) if door else (x0, y0)
            if s.kind == "study":
                # desk
                b.rect(x0 + 150, y1 - 150 - 600, x0 + 150 + 1400, y1 - 150, "A-FURN")
                continue
            bw, bl = (1800.0 if w >= 3100 else 1500.0), 2000.0
            # head against the wall farthest from the door
            cand = {"bottom": abs(dy - y1), "top": abs(dy - y0), "left": abs(dx - x1), "right": abs(dx - x0)}
            far = {"bottom": None}
            door_edge = min({"bottom": abs(dy - y0), "top": abs(dy - y1), "left": abs(dx - x0), "right": abs(dx - x1)}.items(), key=lambda kv: kv[1])[0]
            far_edge = {"bottom": "top", "top": "bottom", "left": "right", "right": "left"}[door_edge]
            if far_edge in ("top", "bottom"):
                bx0 = cx - bw / 2
                by0 = (y1 - bl - 100) if far_edge == "top" else (y0 + 100)
                b.rect(bx0, by0, bx0 + bw, by0 + bl, "A-FURN")
                py = by0 + bl - 450 if far_edge == "top" else by0
                for px in (bx0 + 100, bx0 + bw / 2 + 50):
                    b.rect(px, py + (0 if far_edge == "bottom" else 0), px + bw / 2 - 150, py + 450, "A-FURN")
                for sx in (bx0 - 450, bx0 + bw + 50):
                    b.rect(sx, (y1 - 500 - 100) if far_edge == "top" else (y0 + 100), sx + 400, (y1 - 100) if far_edge == "top" else (y0 + 500), "A-FURN")
            else:
                bx0 = (x1 - bl - 100) if far_edge == "right" else (x0 + 100)
                by0 = cy - bw / 2
                b.rect(bx0, by0, bx0 + bl, by0 + bw, "A-FURN")
        elif s.kind == "kitchen":
            ext_edges = []
            # counter along the longest wall that is exterior (window wall) else bottom
            win = next((o for o in model.openings if o.type == "window" and s.key in (o.from_space, o.to_space)), None)
            along_top = True if not win else (win.cy > cy if abs(win.cy - cy) > abs(win.cx - cx) else None)
            if win and abs(win.cy - cy) > abs(win.cx - cx):
                top = win.cy > cy
                yy0, yy1 = (y1 - 600, y1) if top else (y0, y0 + 600)
                b.rect(x0, yy0, x1, yy1, "A-FURN")
                b.rect(x0 + w * 0.2, yy0 + 100, x0 + w * 0.2 + 500, yy1 - 100, "A-FURN")      # sink
                for k in (0, 1):
                    for l in (0, 1):
                        b.circle(x0 + w * 0.65 + k * 260, (yy0 + yy1) / 2 + (l - 0.5) * 260, 90, "A-FURN")
            elif win:
                right = win.cx > cx
                xx0, xx1 = (x1 - 600, x1) if right else (x0, x0 + 600)
                b.rect(xx0, y0, xx1, y1, "A-FURN")
                b.rect(xx0 + 100, y0 + h * 0.2, xx1 - 100, y0 + h * 0.2 + 500, "A-FURN")
            else:
                b.rect(x0, y0, x1, y0 + 600, "A-FURN")
        elif s.kind == "toilet":
            door = _door_for(model, s.key)
            if w >= h:
                wy = y1 - 150
                b.rect(x1 - 650, y1 - 550 - 100, x1 - 100, y1 - 100 - 0, "A-FURN")
                b.circle(x1 - 375, y1 - 100 - 275, 200, "A-FURN")
                b.rect(x0 + 100, y1 - 450 - 100, x0 + 100 + 500, y1 - 100, "A-FURN")
            else:
                b.rect(cx - 190, y1 - 650, cx + 190, y1 - 100, "A-FURN")
                b.circle(cx, y1 - 650 - 120, 190, "A-FURN")
                b.rect(x1 - 450 - 100, y0 + 100, x1 - 100, y0 + 100 + 500, "A-FURN")
        elif s.kind == "parking":
            cw, cl = 1800.0, 4500.0
            if h >= w:
                b.poly([(cx - cw / 2, cy - cl / 2), (cx + cw / 2, cy - cl / 2), (cx + cw / 2, cy + cl / 2), (cx - cw / 2, cy + cl / 2)], "A-FURN", True, None, "dash")
                b.line(cx - cw / 2, cy + cl / 2 - 900, cx + cw / 2, cy + cl / 2 - 900, "A-FURN")
                b.line(cx - cw / 2, cy - cl / 2 + 900, cx + cw / 2, cy - cl / 2 + 900, "A-FURN")
            else:
                b.poly([(cx - cl / 2, cy - cw / 2), (cx + cl / 2, cy - cw / 2), (cx + cl / 2, cy + cw / 2), (cx - cl / 2, cy + cw / 2)], "A-FURN", True, None, "dash")
        elif s.kind == "living":
            sw, sd = 2000.0, 850.0
            b.rect(x0 + 150, y0 + 150, x0 + 150 + sd, y0 + 150 + sw, "A-FURN")
            b.rect(x0 + 150 + sd + 400, y0 + 150 + sw / 2 - 350, x0 + 150 + sd + 400 + 600, y0 + 150 + sw / 2 + 350, "A-FURN")
        elif s.kind == "dining":
            tx, ty = x0 + w * 0.15, cy - 450
            b.rect(tx, ty, tx + 1500, ty + 900, "A-FURN")
            for i in range(3):
                b.rect(tx + 150 + i * 450, ty + 900 + 40, tx + 150 + i * 450 + 380, ty + 900 + 420, "A-FURN")
                b.rect(tx + 150 + i * 450, ty - 420, tx + 150 + i * 450 + 380, ty - 40, "A-FURN")


def _fit_label(b: B, s_name: str, cx, cy, rw_mm, rh_mm, lines: list[tuple[str, float, bool]]):
    """Place stacked centred labels; shrink or rotate when the room is narrow at this scale."""
    S = b.S
    rw, rh = rw_mm / S, rh_mm / S
    longest = max(len(t) * hh * CW for t, hh, _ in lines)
    rot = 0.0
    scale = 1.0
    if longest > rw * 0.92:
        scale = max(0.62, rw * 0.92 / longest)
        if rw * 0.92 / longest < 0.62 and rh > rw:
            rot = 90.0
            longest_v = longest
            scale = max(0.62, min(1.0, rh * 0.92 / longest))
    total = sum(hh * scale * 1.35 for _, hh, _ in lines)
    y = total / 2
    for t, hh, bold in lines:
        hh2 = hh * scale
        if rot:
            b.text(cx + b.p(y - hh2 * .7), cy, t, hh2, anchor="c", valign="m", rot=90, bold=bold)
        else:
            b.text(cx, cy + b.p(y - hh2), t, hh2, anchor="c", valign="b", bold=bold)
        y -= hh2 * 1.35


def draw_room_labels(b: B, model: ProjectModel, detail=True):
    meta = []
    for s in model.spaces:
        m = room_metrics(model, s)
        x0, y0, x1, y1 = clear_rect(model, s)
        lines = [(s.name.upper() if len(s.name) < 14 else s.name, 2.3, True)]
        if detail:
            lines.append((f"{m['clear_w']:.0f} x {m['clear_d']:.0f}", 1.8, False))
        lines.append((f"{m['area_m2']:.2f} m²", 1.8, False))
        _fit_label(b, s.name, (x0 + x1) / 2, (y0 + y1) / 2 + (b.p(2.5) if s.kind in ("bedroom",) else 0), x1 - x0, y1 - y0, lines)
        meta.append(dict(key=s.key, name=s.name, clear_w=round(m["clear_w"], 1), clear_d=round(m["clear_d"], 1), area_m2=round(m["area_m2"], 3)))
    return meta


def plan_axes(model: ProjectModel):
    xs = sorted({round(w.x1, 1) for w in model.walls if not w.horizontal and (w.length >= 1900 or w.kind == "ext")})
    ys = sorted({round(w.y1, 1) for w in model.walls if w.horizontal and (w.length >= 1900 or w.kind == "ext")})
    def dedupe(v):
        out = []
        for a in v:
            if not out or a - out[-1] > 150:
                out.append(a)
        return out
    return dedupe(xs), dedupe(ys)


def draw_plan_dims(b: B, model: ProjectModel):
    ob = model.outer_bounds()
    X0, Y0, X1, Y1 = ob
    xs, ys = plan_axes(model)
    c1, c2, cb = b.p(10), b.p(18), b.p(27)
    # top chain (axis to axis) + overall
    for a, c in zip(xs, xs[1:]):
        b.dim_h(a, c, Y1, Y1 + c1)
    b.dim_h(X0, X1, Y1, Y1 + c2, f"{X1 - X0:.0f}")
    for a, c in zip(ys, ys[1:]):
        b.dim_v(a, c, X0, X0 - c1)
    b.dim_v(Y0, Y1, X0, X0 - c2, f"{Y1 - Y0:.0f}")
    b.dim_h(X0, X1, Y0, Y0 - c1, f"{X1 - X0:.0f}")
    b.dim_v(Y0, Y1, X1, X1 + c1, f"{Y1 - Y0:.0f}")
    # axis bubbles and lines
    for i, x in enumerate(xs):
        b.line(x, Y1 + b.p(3), x, Y1 + cb - b.p(3.2), "A-GRID", "center")
        b.line(x, Y0 - b.p(3), x, Y0 + b.p(0), "A-GRID", "center")
        b.bubble(x, Y1 + cb, str(i + 1))
    for j, y in enumerate(ys):
        b.line(X0 - cb + b.p(3.2), y, X0 - b.p(3), y, "A-GRID", "center")
        b.bubble(X0 - cb, y, chr(ord("A") + j) if j < 26 else str(j))
    return xs, ys


def section_marks_plan(b: B, model: ProjectModel):
    ob = model.outer_bounds()
    for v in model.views:
        if v.type != "section" or not v.cut:
            continue
        c = v.cut; at = c["at"]; lab = c.get("label", "A")
        ext = b.p(14)
        look = c["look"]
        if c["axis"] == "x":
            y0, y1 = ob[1] - ext, ob[3] + ext
            b.line(at, y0, at, ob[1] - b.p(2), "A-ANNO-SYMB", "center", w=0.35); b.line(at, ob[3] + b.p(2), at, y1, "A-ANNO-SYMB", "center", w=0.35)
            dxv = -1 if look == "w" else 1
            for yy, ys_ in ((y0, 1), (y1, -1)):
                b.line(at, yy, at + dxv * b.p(6), yy, "A-ANNO-SYMB", w=0.4)
                b.poly([(at + dxv * b.p(6), yy), (at + dxv * b.p(3.6), yy + b.p(1.2)), (at + dxv * b.p(3.6), yy - b.p(1.2))], "A-ANNO-SYMB", True, "mid")
                b.circle(at, yy + (-b.p(4) if yy == y0 else b.p(4)), b.p(2.6), "A-ANNO-SYMB")
                b.text(at, yy + (-b.p(4) if yy == y0 else b.p(4)), lab, 2.4, "A-ANNO-SYMB", "c", "m", bold=True)
        else:
            x0, x1 = ob[0] - ext, ob[2] + ext
            b.line(x0, at, ob[0] - b.p(2), at, "A-ANNO-SYMB", "center", w=0.35); b.line(ob[2] + b.p(2), at, x1, at, "A-ANNO-SYMB", "center", w=0.35)
            dyv = 1 if look == "n" else -1
            for xx in (x0, x1):
                b.line(xx, at, xx, at + dyv * b.p(6), "A-ANNO-SYMB", w=0.4)
                b.poly([(xx, at + dyv * b.p(6)), (xx + b.p(1.2), at + dyv * b.p(3.6)), (xx - b.p(1.2), at + dyv * b.p(3.6))], "A-ANNO-SYMB", True, "mid")
                b.circle(xx + (-b.p(4) if xx == x0 else b.p(4)), at, b.p(2.6), "A-ANNO-SYMB")
                b.text(xx + (-b.p(4) if xx == x0 else b.p(4)), at, lab, 2.4, "A-ANNO-SYMB", "c", "m", bold=True)


def plan_view(model: ProjectModel, vd: ViewDef, S: int, project: dict) -> ViewResult:
    b = B(S)
    draw_walls_plan(b, model, vd.level)
    draw_furniture(b, model)
    draw_openings_plan(b, model)
    draw_stair_plan(b, model)
    rooms = draw_room_labels(b, model, detail=True)
    xs, ys = draw_plan_dims(b, model)
    section_marks_plan(b, model)
    ob = model.outer_bounds()
    lvl_el = model.level(vd.level).elevation
    b.level_mark(ob[0] + b.p(3), ob[1] - b.p(17), "±0.000 FFL" if lvl_el == 0 else f"+{lvl_el/1000:.3f} FFL")
    b.north_arrow(ob[2] + b.p(24), ob[3] + b.p(6))
    b.scale_bar(ob[0], ob[1] - b.p(36), S)
    for fl in project.get("future_levels", []):
        b.text(ob[0], ob[1] - b.p(44), f"Note: {fl} is planned (future). Stair is sized for upward continuation; the upper floor is not drawn.", 1.9, valign="t")
    plan_title = f"{model.level(vd.level).name.upper()} PLAN"
    meta = dict(openings=[dict(mark=o.mark, type=o.type, width=o.width, height=o.height, sill=o.sill) for o in model.openings if o.host],
                rooms=rooms, stair=model.stairs[0].flight.model_dump() if model.stairs else None, axes=dict(x=xs, y=ys))
    return ViewResult(vd.id, plan_title, b.prims, bbox_of(b.prims, S), S, meta)


def site_view(model: ProjectModel, vd: ViewDef, S: int, project: dict) -> ViewResult:
    b = B(S)
    pl = model.plot
    PW, PH = pl["w"], pl["h"]
    ob = model.outer_bounds()
    b.rect(0, 0, PW, PH, "A-SITE-BNDY", None, w=0.5)
    sbk = pl["setbacks"]; src = pl["setback_source"]
    rs = pl["road_side"]
    # setback lines (front is road side)
    by_world = {"s": {"front": "bottom", "rear": "top", "left": "left", "right": "right"},
                "n": {"front": "top", "rear": "bottom", "left": "right", "right": "left"},
                "e": {"front": "right", "rear": "left", "left": "bottom", "right": "top"},
                "w": {"front": "left", "rear": "right", "left": "top", "right": "bottom"}}[rs]
    sbw = {by_world[k]: v for k, v in sbk.items()}
    srcw = {by_world[k]: src[k] for k in sbk}
    L, Rr, Bm, T = sbw["left"], sbw["right"], sbw["bottom"], sbw["top"]
    b.rect(L, Bm, PW - Rr, PH - T, "A-SITE-SETB", None, "dash")
    # building footprint
    b.rect(ob[0], ob[1], ob[2], ob[3], "A-SITE-BLDG", "light", w=0.4)
    fp = model.footprint()
    for s in model.spaces:
        if s.kind in ("parking", "sitout"):
            b.rect(s.x, s.y, s.x2, s.y2, "A-SITE-MISC", None, "dash")
            b.text(s.x + s.w / 2, s.y + s.h / 2, s.name.upper(), 2.0, "A-SITE-MISC", "c", "m")
    b.text((ob[0] + ob[2]) / 2, (ob[1] + ob[3]) / 2, "PROPOSED BUILDING (GROUND FLOOR)" if len(model.levels) == 1 else f"PROPOSED BUILDING (G+{len(model.levels) - 1}, GROUND FLOOR FOOTPRINT)", 2.4, "A-ANNO-TEXT", "c", "m", bold=True)
    b.text((ob[0] + ob[2]) / 2, (ob[1] + ob[3]) / 2 - b.p(3.5), f"Footprint {(ob[2]-ob[0])*(ob[3]-ob[1])/1e6:.1f} m²  |  Plot {PW*PH/1e6:.1f} m²  |  Coverage {(ob[2]-ob[0])*(ob[3]-ob[1])/(PW*PH)*100:.0f}%", 1.9, "A-ANNO-TEXT", "c", "m")
    # road strip on the road side
    rd = b.p(12)
    if rs == "s":
        b.rect(-b.p(8), -rd - b.p(4), PW + b.p(8), -b.p(4), "A-SITE-MISC", "light"); b.text(PW / 2, -rd / 2 - b.p(4), "ROAD (width not surveyed)", 2.2, "A-SITE-MISC", "c", "m")
    elif rs == "n":
        b.rect(-b.p(8), PH + b.p(4), PW + b.p(8), PH + rd + b.p(4), "A-SITE-MISC", "light"); b.text(PW / 2, PH + rd / 2 + b.p(4), "ROAD (width not surveyed)", 2.2, "A-SITE-MISC", "c", "m")
    elif rs == "e":
        b.rect(PW + b.p(4), -b.p(8), PW + rd + b.p(4), PH + b.p(8), "A-SITE-MISC", "light"); b.text(PW + rd / 2 + b.p(4), PH / 2, "ROAD (width not surveyed)", 2.2, "A-SITE-MISC", "c", "m", rot=90)
    else:
        b.rect(-rd - b.p(4), -b.p(8), -b.p(4), PH + b.p(8), "A-SITE-MISC", "light"); b.text(-rd / 2 - b.p(4), PH / 2, "ROAD (width not surveyed)", 2.2, "A-SITE-MISC", "c", "m", rot=90)
    # open-space dims
    def lab(v, s): return f"{v:.0f} ({'user' if s == 'user' else 'assumed'})"
    mx, my = (ob[0] + ob[2]) / 2, (ob[1] + ob[3]) / 2
    b.dim_v(0, ob[1], mx, mx, lab(Bm, srcw["bottom"])) if False else None
    b.dim_v(0, ob[1], mx - b.p(0), mx, lab(Bm, srcw["bottom"])) if False else None
    if Bm > 0: b.dim_v(0, ob[1], mx, mx, lab(ob[1], srcw["bottom"]) if False else f"{ob[1]:.0f} {srcw['bottom']}")
    if T > 0: b.dim_v(ob[3], PH, mx, mx, f"{PH - ob[3]:.0f} {srcw['top']}")
    if L > 0: b.dim_h(0, ob[0], my, my, f"{ob[0]:.0f} {srcw['left']}")
    if Rr > 0: b.dim_h(ob[2], PW, my, my, f"{PW - ob[2]:.0f} {srcw['right']}")
    # plot dims outside
    off = b.p(18) if rs != "s" else b.p(18)
    b.dim_h(0, PW, PH, PH + b.p(10) if rs != "n" else PH + b.p(26), f"{PW:.0f}  ({fmt_ft_in(PW)})")
    b.dim_v(0, PH, 0, -b.p(10) if rs != "w" else -b.p(26), f"{PH:.0f}  ({fmt_ft_in(PH)})")
    for k, nm in (("bottom", "S"), ("top", "N")):
        pass
    # open area labels
    if T > b.p(8): b.text(PW / 2, PH - T / 2, "OPEN SPACE", 1.8, "A-SITE-MISC", "c", "m")
    b.text(PW / 2, -b.p(26) if rs != "s" else -rd - b.p(14), "", 1.8)
    # access note
    b.text(0, -b.p(36) if rs != "s" else -rd - b.p(24), "Vehicular / pedestrian access: from the road frontage (gate position to be confirmed by the owner).", 1.9, valign="t")
    b.north_arrow(PW + b.p(30) if rs != "e" else PW + rd + b.p(30), PH + b.p(4))
    b.scale_bar(0, -b.p(60) if rs != "s" else -rd - b.p(44), S)
    b.text(0, -b.p(50) if rs != "s" else -rd - b.p(34), "Setback / open-space values: 'user' = supplied by the user, 'assumed' = concept assumption, verify with local authority rules.", 1.9, valign="t")
    meta = dict(plot=[PW, PH], footprint=[ob[2] - ob[0], ob[3] - ob[1]], setbacks=sbk, source=src)
    return ViewResult(vd.id, "SITE PLAN", b.prims, bbox_of(b.prims, S), S, meta)


def roof_view(model: ProjectModel, vd: ViewDef, S: int, project: dict) -> ViewResult:
    b = B(S)
    ob = model.outer_bounds()
    lv = model.level(vd.level)
    pt = 230.0
    b.rect(ob[0], ob[1], ob[2], ob[3], "A-ROOF", "light", w=0.4)
    b.rect(ob[0] + pt, ob[1] + pt, ob[2] - pt, ob[3] - pt, "A-ROOF", None, w=0.25)
    b.text((ob[0] + ob[2]) / 2, (ob[1] + ob[3]) / 2 + b.p(4), "TERRACE / ROOF SLAB", 2.6, "A-ANNO-TEXT", "c", "m", bold=True)
    b.text((ob[0] + ob[2]) / 2, (ob[1] + ob[3]) / 2, f"Parapet {lv.parapet:.0f} high x {pt:.0f} thick", 2.0, "A-ANNO-TEXT", "c", "m")
    # indicative slope toward rear
    pl = model.plot
    rear = {"s": (0, 1), "n": (0, -1), "e": (-1, 0), "w": (1, 0)}[pl["road_side"]]
    cx, cy = (ob[0] + ob[2]) / 2, (ob[1] + ob[3]) / 2
    ln = min(ob[2] - ob[0], ob[3] - ob[1]) * 0.28
    a = (cx - rear[0] * ln, cy - rear[1] * ln - b.p(10)); c = (cx + rear[0] * ln, cy + rear[1] * ln - b.p(10))
    b.line(a[0], a[1], c[0], c[1], "A-ROOF", w=0.25)
    hs = b.p(2.4)
    nrm = (-rear[1], rear[0])
    b.poly([c, (c[0] - rear[0] * hs * 1.6 + nrm[0] * hs * .6, c[1] - rear[1] * hs * 1.6 + nrm[1] * hs * .6), (c[0] - rear[0] * hs * 1.6 - nrm[0] * hs * .6, c[1] - rear[1] * hs * 1.6 - nrm[1] * hs * .6)], "A-ROOF", True, "mid")
    b.text(cx, cy - b.p(12), "INDICATIVE SLOPE 1:100 TOWARDS REAR (to be confirmed)", 1.8, "A-ANNO-TEXT", "c", "m")
    st = model.stairs[0] if model.stairs else None
    if st:
        b.rect(st.x, st.y, st.x + st.w, st.y + st.h, "A-STAIR", None, "dash")
        b.text(st.x + st.w / 2, st.y + st.h / 2, "STAIR\nBELOW", 1.8, "A-STAIR", "c", "m")
    for rear_corner in ((ob[0] + pt * 2, ob[1] + pt * 2), (ob[2] - pt * 2, ob[3] - pt * 2)):
        pass
    b.dim_h(ob[0], ob[2], ob[3], ob[3] + b.p(10), f"{ob[2]-ob[0]:.0f}")
    b.dim_v(ob[1], ob[3], ob[0], ob[0] - b.p(10), f"{ob[3]-ob[1]:.0f}")
    b.north_arrow(ob[2] + b.p(24), ob[3] + b.p(4))
    b.scale_bar(ob[0], ob[1] - b.p(20), S)
    status = "Roof geometry APPROVED by user" if model.roof_approved else "CONCEPT: roof geometry, slope and drainage not yet approved by the user"
    b.text(ob[0], ob[1] - b.p(32), status + "; roof access via the stair (headroom cabin not modelled).", 1.9, valign="t")
    return ViewResult(vd.id, "ROOF / TERRACE PLAN", b.prims, bbox_of(b.prims, S), S,
                      dict(parapet=lv.parapet, approved=model.roof_approved, size=[ob[2] - ob[0], ob[3] - ob[1]]))


def _facade(model: ProjectModel, facing: str):
    fp = model.footprint()
    walls = []
    for w in model.walls:
        if w.kind != "ext":
            continue
        if facing == "s" and w.horizontal and abs(w.y1 - fp[1]) < 1: walls.append(w)
        if facing == "n" and w.horizontal and abs(w.y1 - fp[3]) < 1: walls.append(w)
        if facing == "e" and not w.horizontal and abs(w.x1 - fp[2]) < 1: walls.append(w)
        if facing == "w" and not w.horizontal and abs(w.x1 - fp[0]) < 1: walls.append(w)
    return walls


def _u(facing: str, x: float, y: float) -> float:
    return {"s": x, "n": -x, "e": y, "w": -y}[facing]


def elevation_view(model: ProjectModel, vd: ViewDef, S: int, project: dict) -> ViewResult:
    b = B(S)
    f = vd.facing or "s"
    lv = model.levels[0]
    H, par, plinth = lv.height, lv.parapet, lv.plinth
    TOP = model.total_height()
    ob = model.outer_bounds()
    u0, u1 = sorted((_u(f, ob[0], ob[1]), _u(f, ob[2], ob[3])))
    if f in ("s", "n"):
        us = sorted([_u(f, ob[0], 0), _u(f, ob[2], 0)])
    else:
        us = sorted([_u(f, 0, ob[1]), _u(f, 0, ob[3])])
    u0, u1 = us
    b.rect(u0, -plinth, u1, 0, "A-ELEV-OUT", "light")
    b.rect(u0, 0, u1, TOP, "A-ELEV-OUT", None)
    b.rect(u0 - 40, TOP, u1 + 40, TOP + lv.slab * 0, "A-ELEV-OUT", None)
    b.rect(u0, TOP, u1, TOP + par, "A-ELEV-OUT", None)
    b.line(u0 - 40, TOP, u1 + 40, TOP, "A-ELEV-OUT", w=0.45)
    for lx in model.levels[1:]:   # intermediate floor slab lines
        b.line(u0 - 40, lx.elevation, u1 + 40, lx.elevation, "A-ELEV-OUT", w=0.35)
        b.line(u0, lx.elevation - lx.slab, u1, lx.elevation - lx.slab, "A-ELEV-OUT", "dash", w=0.15)
    b.line(u0 - b.p(25), -plinth, u1 + b.p(25), -plinth, "A-ELEV-GRND")
    marks = []
    # open bays (porch / parking) on this facade
    fp = model.footprint()
    for s in model.spaces:
        if not s.open_boundary:
            continue
        on = {"s": abs(s.y - fp[1]) < 1, "n": abs(s.y2 - fp[3]) < 1, "e": abs(s.x2 - fp[2]) < 1, "w": abs(s.x - fp[0]) < 1}[f]
        if not on:
            continue
        a, c = sorted((_u(f, s.x, s.y), _u(f, s.x2, s.y2)))
        if f in ("e", "w"):
            a, c = sorted((_u(f, 0, s.y), _u(f, 0, s.y2)))
        else:
            a, c = sorted((_u(f, s.x, 0), _u(f, s.x2, 0)))
        z0 = model.level(s.level).elevation
        if s.kind == "balcony":
            b.rect(a, z0, c, z0 + 1000, "A-ELEV-OPEN", None, "dash")
            b.line(a, z0 + 1000, c, z0 + 1000, "A-ELEV-OPEN", w=0.3)
            b.text((a + c) / 2, z0 + 500, s.name.upper() + " (OPEN, RAILING)", 1.6, "A-ANNO-TEXT", "c", "m")
        else:
            b.rect(a, z0, c, z0 + H - 500, "A-ELEV-OPEN", None, "dash")
            b.line(a, z0 + H - 500, c, z0 + H - 500, "A-ELEV-OPEN", w=0.3)
            b.text((a + c) / 2, z0 + H / 2, s.name.upper() + " (OPEN)", 1.9, "A-ANNO-TEXT", "c", "m")
    for w in _facade(model, f):
        for o in model.openings:
            if o.host != w.id:
                continue
            uc = _u(f, o.cx, o.cy)
            a, c = uc - o.width / 2, uc + o.width / 2
            el = model.level(o.level).elevation
            z0, z1 = o.sill + el, o.sill + el + o.height
            if o.type == "window":
                b.rect(a - 40, z0 - 40, c + 40, z1 + 40, "A-ELEV-OPEN", None)
                b.rect(a, z0, c, z1, "A-ELEV-OPEN", "glass")
                b.line((a + c) / 2, z0, (a + c) / 2, z1, "A-ELEV-OPEN")
                b.line(a - 90, z0 - 40, c + 90, z0 - 40, "A-ELEV-OPEN", w=0.3)
                b.line(a - 90, z1 + 40, c + 90, z1 + 40, "A-ELEV-OPEN", w=0.2)
            else:
                b.rect(a, z0, c, z1, "A-ELEV-OPEN", "glass")
                b.line(a - 60, z1 + 60, c + 60, z1 + 60, "A-ELEV-OPEN", w=0.25)
                b.line((a + c) / 2, z0, (a + c) / 2, z1, "A-ELEV-OPEN")
            b.circle(uc, z1 + b.p(5.5), b.p(2.4), "A-ANNO-SYMB")
            b.text(uc, z1 + b.p(5.5), o.mark, 1.7, "A-ANNO-SYMB", "c", "m")
            marks.append(dict(mark=o.mark, type=o.type, width=o.width, height=o.height, sill=o.sill))
    # level marks and dims
    xr = u1 + b.p(16)
    marks_z = [(-plinth, f"GL  -{plinth/1000:.3f}"), (0, "FFL  ±0.000")]
    marks_z += [(lx.elevation, f"{lx.name.upper()}  +{lx.elevation/1000:.3f}") for lx in model.levels[1:]]
    marks_z += [(TOP, f"ROOF SLAB  +{TOP/1000:.3f}"), (TOP + par, f"PARAPET TOP  +{(TOP+par)/1000:.3f}")]
    for z, lab in marks_z:
        b.level_mark(xr - b.p(2), z, lab)
        b.line(u1 + b.p(1), z, xr - b.p(6), z, "A-ANNO-DIMS", "dash", w=0.08)
    xd = u0 - b.p(12)
    b.dim_v(-plinth, 0, u0, xd, f"{plinth:.0f}")
    for lx in model.levels:
        b.dim_v(lx.elevation, lx.elevation + lx.height, u0, xd, f"{lx.height:.0f}")
    b.dim_v(TOP, TOP + par, u0, xd, f"{par:.0f}")
    b.dim_h(u0, u1, -plinth, -plinth - b.p(10), f"{u1-u0:.0f}")
    b.scale_bar(u0, -plinth - b.p(26), S)
    nm = SIDE_NAMES[f].upper()
    road = " (ROAD SIDE)" if model.plot and model.plot["road_side"] == f else ""
    return ViewResult(vd.id, f"{nm} ELEVATION{road}", b.prims, bbox_of(b.prims, S), S, dict(facing=f, openings=marks, width=u1 - u0, height=TOP + par))


def default_sections(model: ProjectModel) -> list[dict]:
    st = model.stairs[0] if model.stairs else None
    ob = model.outer_bounds()
    out = []
    if st:
        if st.run_axis == "y":
            out.append(dict(axis="x", at=st.x + st.w / 2, look="w", label="A"))
        else:
            out.append(dict(axis="y", at=st.y + st.h / 2, look="n", label="A"))
    else:
        out.append(dict(axis="x", at=(ob[0] + ob[2]) / 2, look="w", label="A"))
    return out


def section_view(model: ProjectModel, vd: ViewDef, S: int, project: dict) -> ViewResult:
    b = B(S)
    cut = vd.cut
    axis, at, look, lab = cut["axis"], cut["at"], cut["look"], cut.get("label", "A")
    lv = model.levels[0]
    slab, plinth, par = lv.slab, lv.plinth, lv.parapet
    H = model.total_height()           # top of roof slab
    ob = model.outer_bounds()
    # along-view coordinate
    if axis == "x":   # plane x=at, line runs along y
        U = (lambda x, y: y) if look == "w" else (lambda x, y: -y)
        lo, hi = sorted((U(0, ob[1]), U(0, ob[3])))
    else:
        U = (lambda x, y: x) if look == "n" else (lambda x, y: -x)
        lo, hi = sorted((U(ob[0], 0), U(ob[2], 0)))
    # floor slab and roof slab across the building
    b.rect(lo, -plinth - 150, hi, -150, "A-SECT-CUT", None, w=0.2)
    b.line(lo - b.p(15), -plinth, hi + b.p(15), -plinth, "A-ELEV-GRND")
    b.rect(lo, -150, hi, 0, "A-SECT-CUT", "wall")
    b.rect(lo, H - slab, hi, H, "A-SECT-CUT", "wall")
    for lx in model.levels[1:]:
        b.rect(lo, lx.elevation - lx.slab, hi, lx.elevation, "A-SECT-CUT", "wall")
    cut_walls = []
    for w in model.walls:
        if w.horizontal:
            if axis != "y" and min(w.x1, w.x2) - 1 <= at <= max(w.x1, w.x2) + 1:
                c = U(at, w.y1)
            elif False:
                continue
            else:
                continue
            if axis == "x":
                pass
        else:
            if axis == "y" and min(w.y1, w.y2) - 1 <= at <= max(w.y1, w.y2) + 1:
                c = U(w.x1, at)
            else:
                continue
        # (axis x: horizontal walls are crossed; axis y: vertical walls are crossed)
        if (axis == "x" and not w.horizontal) or (axis == "y" and w.horizontal):
            continue
        t2 = w.thickness / 2
        wl = model.level(w.level)
        bottom, top = (-plinth if wl.elevation == 0 else wl.elevation), wl.elevation + wl.height - wl.slab
        segs = [(bottom, top)]
        for o in model.openings:
            if o.host == w.id:
                pos = o.cx if w.horizontal else o.cy
                if abs(pos - at) <= o.width / 2:
                    z0, z1 = o.sill + wl.elevation, o.sill + wl.elevation + o.height
                    segs = [(bottom, z0 if o.sill > 0 else bottom), (z1, top)]
                    segs = [(a, c_) for a, c_ in segs if c_ - a > 1]
        for z0, z1 in segs:
            b.rect(c - t2, z0, c + t2, z1, "A-SECT-CUT", "wall")
        if w.kind == "ext" and wl.id == model.levels[-1].id:
            b.rect(c - t2, H, c + t2, H + par, "A-SECT-CUT", "wall")
        cut_walls.append(dict(wall=w.id, u=round(c, 1), t=w.thickness))
    # openings cut by the plane (window/door heads and sills shown)
    # rooms along the cut
    rooms = []
    for s in model.spaces:
        if axis == "x" and s.x <= at < s.x2:
            a, c = sorted((U(0, s.y), U(0, s.y2)))
        elif axis == "y" and s.y <= at < s.y2:
            a, c = sorted((U(s.x, 0), U(s.x2, 0)))
        else:
            continue
        x0, y0, x1, y1 = clear_rect(model, s)
        if axis == "x":
            a2, c2 = sorted((U(0, y0), U(0, y1)))
        else:
            a2, c2 = sorted((U(x0, 0), U(x1, 0)))
        mid = (a2 + c2) / 2
        sl = model.level(s.level)
        zc = sl.elevation + sl.height / 2
        b.text(mid, zc + b.p(3), s.name.upper(), 2.1, "A-ANNO-TEXT", "c", "b", bold=True)
        b.text(mid, zc - b.p(1), f"{c2 - a2:.0f} clear", 1.7, "A-ANNO-TEXT", "c", "b")
        rooms.append(dict(key=s.key, a=round(a2, 1), c=round(c2, 1)))
        b.line(a2, sl.elevation + sl.height - sl.slab, c2, sl.elevation + sl.height - sl.slab, "A-SECT-BEYOND", "dash")
        # stair steps if the plane crosses the stair run
        st = model.stairs[0] if model.stairs else None
        if st and s.id == st.space_id and st.flight:
            fl = st.flight
            run_axis_matches = (st.run_axis == "y" and axis == "x") or (st.run_axis == "x" and axis == "y")
            if run_axis_matches:
                T = fl.treads_per_flight
                start_low = (st.start[1] < 0) if st.run_axis == "y" else (st.start[0] < 0)
                u_start = a2 if True else a2
                sign = 1
                # direction of u increase vs world: determine by mapping
                p_lo = U(0, y0) if axis == "x" else U(x0, 0)
                p_hi = U(0, y1) if axis == "x" else U(x1, 0)
                world_low_is_u_low = p_lo < p_hi
                begin_world_low = start_low
                u_begin = a2 if (begin_world_low == world_low_is_u_low) else c2
                dirn = 1 if u_begin == a2 else -1
                pts = [(u_begin, 0.0)]
                for i in range(T + 1):
                    z = i * fl.riser_mm
                    if i:
                        pts.append((u_begin + dirn * (i - 1) * fl.tread_mm, z))
                    pts.append((u_begin + dirn * i * fl.tread_mm if i < T else u_begin + dirn * T * fl.tread_mm, z))
                uu = u_begin + dirn * T * fl.tread_mm
                zz = (T + 1) * fl.riser_mm
                pts.append((uu, zz))
                pts.append((uu + dirn * fl.landing, zz))
                b.poly(pts, "A-STAIR", False, None)
    # level marks / dims
    xr = hi + b.p(18)
    mk = [(-plinth, f"GL  -{plinth/1000:.3f}"), (0, "FFL  ±0.000")]
    mk += [(lx.elevation, f"{lx.name.upper()}  +{lx.elevation/1000:.3f}") for lx in model.levels[1:]]
    mk += [(H - slab, f"SOFFIT  +{(H-slab)/1000:.3f}"), (H, f"ROOF SLAB  +{H/1000:.3f}"), (H + par, f"PARAPET  +{(H+par)/1000:.3f}")]
    for z, lb in mk:
        b.level_mark(xr - b.p(2), z, lb)
        b.line(hi + b.p(1), z, xr - b.p(6), z, "A-ANNO-DIMS", "dash", w=0.08)
    xd = lo - b.p(12)
    b.dim_v(-plinth, 0, lo, xd, f"{plinth:.0f}")
    for lx in model.levels:
        b.dim_v(lx.elevation, lx.elevation + lx.height - lx.slab, lo, xd, f"{lx.height - lx.slab:.0f}")
        b.dim_v(lx.elevation + lx.height - lx.slab, lx.elevation + lx.height, lo, xd, f"{lx.slab:.0f}")
    b.dim_v(H, H + par, lo, xd, f"{par:.0f}")
    b.dim_h(lo, hi, -plinth, -plinth - b.p(10), f"{hi - lo:.0f}")
    b.scale_bar(lo, -plinth - b.p(26), S)
    return ViewResult(vd.id, f"SECTION {lab}-{lab}", b.prims, bbox_of(b.prims, S), S,
                      dict(label=lab, axis=axis, at=at, cut_walls=cut_walls, rooms=rooms, height=H, clear_height=lv.height - slab))


# ---------------- tables (paper units, not to scale) -----------------------
def _wrap(text: str, width_mm: float, h: float) -> list[str]:
    out, line = [], ""
    cw = h * CW
    for word in text.split():
        trial = (line + " " + word).strip()
        if len(trial) * cw > width_mm and line:
            out.append(line); line = word
        else:
            line = trial
    if line:
        out.append(line)
    return out


def _table(b: B, x, y, cols: list[tuple[str, float]], rows: list[list[str]], h=2.1, rowh=6.0, title=None, bold_last=False):
    """Draw a table with top-left at (x,y) in paper mm (y decreasing downward). Returns bottom y."""
    if title:
        b.text(x, y, title, 3.0, bold=True, valign="t"); y -= 6.5
    W = sum(w for _, w in cols)
    b.rect(x, y - rowh, x + W, y, "A-TABLE", "light")
    cx = x
    for name, w in cols:
        b.text(cx + 1.2, y - rowh / 2, name, h, "A-TABLE", "l", "m", bold=True)
        cx += w
    cy = y - rowh
    for ri, row in enumerate(rows):
        cx = x
        for (name, w), val in zip(cols, row):
            maxc = max(1, int((w - 2.2) / (h * CW)))
            s = val if len(val) <= maxc else val[: max(1, maxc - 1)] + "…"
            b.text(cx + 1.2, cy - rowh / 2, s, h, "A-TABLE", "l", "m", bold=(bold_last and ri == len(rows) - 1))
            cx += w
        cy -= rowh
        b.line(x, cy, x + W, cy, "A-TABLE")
    b.line(x, y, x + W, y, "A-TABLE", w=0.35)
    cx = x
    for name, w in cols:
        b.line(cx, y, cx, cy, "A-TABLE")
        cx += w
    b.line(x + W, y, x + W, cy, "A-TABLE")
    b.line(x, y - rowh, x + W, y - rowh, "A-TABLE", w=0.35)
    return cy


def rooms_schedule(model: ProjectModel, vd: ViewDef, S: int, project: dict) -> ViewResult:
    b = B(1)
    cols = [("No.", 12), ("Room", 52), ("Level", 22), ("Clear L (mm)", 28), ("Clear W (mm)", 28), ("Net area (m²)", 28), ("Gross to CL (m²)", 30)]
    rows, total, meta = [], 0.0, []
    for i, s in enumerate(model.spaces, 1):
        m = room_metrics(model, s)
        a, c = max(m["clear_w"], m["clear_d"]), min(m["clear_w"], m["clear_d"])
        rows.append([str(i), s.name, model.level(s.level).name, f"{a:.0f}", f"{c:.0f}", f"{m['area_m2']:.2f}", f"{m['gross_m2']:.2f}"])
        total += m["area_m2"]
        meta.append(dict(key=s.key, name=s.name, area_m2=round(m["area_m2"], 3), clear_w=round(m["clear_w"], 1), clear_d=round(m["clear_d"], 1)))
    rows.append(["", "TOTAL (net)", "", "", "", f"{total:.2f}", ""])
    y = _table(b, 0, 0, cols, rows, bold_last=True)
    y -= 5
    for ln in _wrap("Area method: " + AREA_METHOD, 190, 1.9):
        b.text(0, y, ln, 1.9, valign="t"); y -= 3.4
    y -= 2
    b.text(0, y, "Units: millimetres (lengths) and square metres (areas). Reported values are concept-stage and unverified by survey.", 1.9, valign="t")
    return ViewResult(vd.id, "ROOM AREA SCHEDULE", b.prims, bbox_of(b.prims, 1), 0, dict(rows=meta, total_net=round(total, 3)))


def openings_schedule(model: ProjectModel, vd: ViewDef, S: int, project: dict) -> ViewResult:
    b = B(1)
    cols = [("Mark", 16), ("Type", 20), ("Location", 56), ("Width (mm)", 26), ("Height (mm)", 26), ("Sill (mm)", 22), ("Qty", 12), ("Remarks", 52)]
    rows, meta = [], []
    for o in sorted(model.openings, key=lambda o: (o.type, int(o.mark[1:]))):
        nm = lambda k: (model.space(k).name if model.space(k) else k)
        loc = " / ".join([nm(x) for x in (o.from_space, o.to_space) if x]) or "—"
        rows.append([o.mark, o.type.title(), loc, f"{o.width:.0f}", f"{o.height:.0f}", f"{o.sill:.0f}", "1", o.note or ("Spec by designer" )])
        meta.append(dict(mark=o.mark, type=o.type, width=o.width, height=o.height, sill=o.sill))
    y = _table(b, 0, 0, cols, rows)
    y -= 5
    b.text(0, y, "Sizes are nominal clear openings in millimetres. Frame, shutter and glazing specification are not set at concept stage.", 1.9, valign="t")
    return ViewResult(vd.id, "DOOR AND WINDOW SCHEDULE", b.prims, bbox_of(b.prims, 1), 0, dict(rows=meta))


def index_view(model: ProjectModel, vd: ViewDef, S: int, project: dict) -> ViewResult:
    b = B(1)
    sheets = project.get("sheet_index", [])
    cols = [("Sheet", 22), ("Title", 78), ("Scale", 22), ("Paper", 18), ("Rev", 14)]
    rows = [[s["number"], s["title"], s["scale"], s["paper"], s["rev"]] for s in sheets]
    y = _table(b, 0, 0, cols, rows)
    y -= 8
    b.text(0, y, "GENERAL NOTES", 3.0, bold=True, valign="t"); y -= 6
    notes = [
        "All dimensions are in millimetres unless noted. Do not scale from printed drawings; use the dimensions shown.",
        "CONCEPT DRAFT prepared with AI assistance. Not reviewed, signed or stamped by any architect, engineer or authority.",
        "Setbacks / open spaces marked 'assumed' are placeholders for concept work only and must be verified locally.",
        "Wall thickness: 230 mm external, 115 mm internal (assumed brick masonry). Structure is not designed.",
        "Print at the stated paper size with scaling set to Actual Size / 100% (not 'Fit to page').",
        "Levels: FFL = finished floor level (±0.000), plinth 450 above ground; floor height as noted on sections.",
    ]
    for n in notes:
        for k, ln in enumerate(_wrap(n, 175, 2.0)):
            b.text(0 if k else 3, y, ("• " if k == 0 else "") + ln, 2.0, valign="t") if False else b.text(0, y, ("• " if k == 0 else "  ") + ln, 2.0, valign="t")
            y -= 3.6
    y -= 3
    asm = [a for a in model.assumptions]
    if asm:
        b.text(0, y, "ASSUMPTIONS", 3.0, bold=True, valign="t"); y -= 6
        for a in asm:
            for k, ln in enumerate(_wrap(a.text, 175, 2.0)):
                b.text(0, y, ("• " if k == 0 else "  ") + ln, 2.0, valign="t"); y -= 3.6
        y -= 3
    miss = project.get("missing", [])
    if miss:
        b.text(0, y, "INFORMATION STILL NEEDING LOCAL REVIEW", 3.0, bold=True, valign="t"); y -= 6
        for m in miss:
            for k, ln in enumerate(_wrap(m, 175, 2.0)):
                b.text(0, y, ("• " if k == 0 else "  ") + ln, 2.0, valign="t"); y -= 3.6
        y -= 3
    b.text(0, y, "LEGEND", 3.0, bold=True, valign="t"); y -= 8
    b.rect(0, y - 3, 14, y, "A-WALL", "wall"); b.text(18, y - 1.5, "Cut wall (poche)", 2.0, valign="m")
    b.line(60, y - 1.5, 74, y - 1.5, "A-GRID", "center"); b.text(78, y - 1.5, "Reference axis", 2.0, valign="m")
    b.circle(120, y - 1.5, 2.4, "A-ANNO-SYMB"); b.text(120, y - 1.5, "D1", 1.7, "A-ANNO-SYMB", "c", "m"); b.text(126, y - 1.5, "Door / window mark", 2.0, valign="m")
    b.rect(0, y - 12, 14, y - 9, "A-SITE-SETB", None, "dash"); b.text(18, y - 10.5, "Setback line", 2.0, valign="m")
    return ViewResult(vd.id, "COVER, INDEX AND GENERAL NOTES", b.prims, bbox_of(b.prims, 1), 0, dict(sheets=sheets))


def structure_view(model: ProjectModel, vd: ViewDef, S: int, project: dict) -> ViewResult:
    """PRELIMINARY column / footing / beam layout. Concept sizes from engine.structural; never a structural design."""
    from .structural import prelim
    b = B(S)
    ob = model.outer_bounds()
    sz = prelim(model)["sizes"]
    for w in model.walls:                                         # architectural walls in light grey for reference
        t = w.thickness / 2
        if w.horizontal:
            b.rect(min(w.x1, w.x2) - t, w.y1 - t, max(w.x1, w.x2) + t, w.y1 + t, "A-SECT-BEYOND")
        else:
            b.rect(w.x1 - t, min(w.y1, w.y2) - t, w.x1 + t, max(w.y1, w.y2) + t, "A-SECT-BEYOND")
    for w in model.walls:                                         # plinth / roof beams run on every wall line
        b.line(w.x1, w.y1, w.x2, w.y2, "S-BEAM", "center")
    cnt: dict[tuple[int, int], int] = {}
    for w in model.walls:
        for x, y in ((w.x1, w.y1), (w.x2, w.y2)):
            k = (round(x / 10) * 10, round(y / 10) * 10)
            cnt[k] = cnt.get(k, 0) + 1
    cols = sorted([k for k, n in cnt.items() if n >= 2], key=lambda k: (-k[1], k[0]))
    for i, (x, y) in enumerate(cols, 1):
        fs = sz["footing"] / 2
        b.rect(x - fs, y - fs, x + fs, y + fs, "S-FOOT", None, "dash")
        b.rect(x - sz["col_b"] / 2, y - sz["col_d"] / 2, x + sz["col_b"] / 2, y + sz["col_d"] / 2, "S-COL", "mid")
        b.text(x + sz["col_b"] / 2 + b.p(1), y + sz["col_d"] / 2 + b.p(1), f"C{i}", 1.8, "A-ANNO-TEXT", "l", "b", bold=True)
    b.dim_h(ob[0], ob[2], ob[3], ob[3] + b.p(10), f"{ob[2]-ob[0]:.0f}")
    b.dim_v(ob[1], ob[3], ob[0], ob[0] - b.p(10), f"{ob[3]-ob[1]:.0f}")
    b.north_arrow(ob[2] + b.p(24), ob[3] + b.p(4))
    b.scale_bar(ob[0], ob[1] - b.p(20), S)
    x0 = ob[2] + b.p(34)
    y = ob[3]
    lines = [("PRELIMINARY - NOT FOR CONSTRUCTION", 3.0, True),
             ("Rule-of-thumb sizes for early planning. Not a structural design.", 2.0, False),
             ("A licensed structural engineer must design and check all members", 2.0, False),
             ("against current IS codes using a soil investigation report.", 2.0, False), ("", 2.0, False),
             (f"COLUMNS C1-C{len(cols)}: {sz['col_b']:.0f} x {sz['col_d']:.0f} mm RCC (M20 / Fe500), at wall corners and junctions", 2.0, False),
             (f"FOOTINGS: {sz['footing']:.0f} x {sz['footing']:.0f} x {sz['footing_depth']:.0f} mm under each column (assumed SBC 150 kN/m2)", 2.0, False),
             (f"ROOF BEAMS: {sz['beam_b']:.0f} x {sz['beam_d']:.0f} mm on wall lines;  PLINTH BEAM 230 x 300 mm", 2.0, False),
             (f"ROOF SLAB: {sz['slab']:.0f} mm thick (model {model.levels[0].slab:.0f} mm)", 2.0, False), ("", 2.0, False),
             ("Beam and column positions follow the architectural walls (dash-dot lines);", 1.8, False),
             ("column grid is indicative and not optimised. Footings may overlap and need design.", 1.8, False)]
    for txt, h, bold in lines:
        if txt:
            b.text(x0, y, txt, h, "A-ANNO-TEXT", "l", "t", bold=bold)
        y -= b.p(h + 2.4)
    return ViewResult(vd.id, "STRUCTURAL LAYOUT (PRELIMINARY)", b.prims, bbox_of(b.prims, S), S, dict(columns=len(cols), sizes=sz))


BUILDERS = dict(plan=plan_view, site=site_view, roof=roof_view, elevation=elevation_view, section=section_view,
                rooms=rooms_schedule, openings=openings_schedule, index=index_view, structure=structure_view)


def build_view(model: ProjectModel, vd: ViewDef, S: int, project: dict | None = None) -> ViewResult:
    if vd.type == "plan":
        model = model.at_level(vd.level)
    elif vd.type == "structure":
        model = model.at_level(model.levels[0].id)
    return BUILDERS[vd.type](model, vd, S, project or {})
