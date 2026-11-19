"""Concept layout of electrical points, plumbing fixtures, soil stacks, drains and a septic tank, computed from the model.

These are planning aids for talking to an electrician and a plumber. They are not a design: pipe sizes, tank sizes and
loads are typical rule-of-thumb values and must be checked by a licensed engineer and against local codes.
All coordinates are model millimetres (+y north).
"""
from __future__ import annotations

import math

from .layout import clear_rect
from .model import Opening, ProjectModel, Space

# connected load per point, kW (typical allowances)
LOAD_KW = dict(light=0.06, fan=0.075, socket=0.5, ac=1.5, tv=0.15, exhaust=0.05, geyser=2.0, fridge=0.3, chimney=0.2, db=0.0)
USERS_FORMULA = "2 users per bedroom plus 1"
# Typical inner sizes (length, breadth, liquid depth in m) of a septic tank by number of users. Check against your local code.
SEPTIC_TABLE = [(5, 1.5, 0.75, 1.0), (10, 2.0, 0.90, 1.0), (15, 2.0, 0.90, 1.3), (20, 2.3, 1.10, 1.3)]
LPCD = 135.0
WALL_T = 230.0
CLEAR = 225.0        # half an inspection chamber: nearest a chamber or drain centre may get to the plot boundary


def _pt(kind, x, y, room, **kw):
    return dict(kind=kind, x=round(x, 1), y=round(y, 1), room=room, **kw)


def _openings(model: ProjectModel, s: Space) -> list[Opening]:
    return [o for o in model.openings if s.key in (o.from_space, o.to_space)]


def _wall_spots(model: ProjectModel, s: Space, n: int, side_pref: str | None = None) -> list[tuple[float, float]]:
    """Points on the wall faces of a room, away from doors and windows, for sockets and similar."""
    x0, y0, x1, y1 = clear_rect(model, s)
    w, h = x1 - x0, y1 - y0
    cand = [((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1), (x0, (y0 + y1) / 2), (x1, (y0 + y1) / 2),
            (x0 + w * 0.25, y0), (x0 + w * 0.75, y1), (x0, y0 + h * 0.25), (x1, y0 + h * 0.75)]
    ops = _openings(model, s)
    ok = [c for c in cand if all(math.hypot(c[0] - o.cx, c[1] - o.cy) > o.width / 2 + 450 for o in ops)]
    return (ok or cand)[:n]


def _switch_pos(model: ProjectModel, s: Space, o: Opening) -> tuple[float, float]:
    """Switch board beside a door, on the room side of the wall, on the latch side."""
    x0, y0, x1, y1 = clear_rect(model, s)
    host = next((w for w in model.walls if w.id == o.host), None)
    off = o.width / 2 + 200
    if host is None or host.horizontal:
        x = o.cx + off if o.cx + off < x1 - 100 else o.cx - off
        y = y0 + 60 if abs(o.cy - y0) < abs(o.cy - y1) else y1 - 60
        return x, y
    y = o.cy + off if o.cy + off < y1 - 100 else o.cy - off
    x = x0 + 60 if abs(o.cx - x0) < abs(o.cx - x1) else x1 - 60
    return x, y


def electrical(model: ProjectModel) -> dict:
    """Light, fan, socket, AC and appliance points for every room on the model's level, plus the distribution board."""
    pts: list[dict] = []
    for s in model.spaces:
        x0, y0, x1, y1 = clear_rect(model, s)
        w, h = x1 - x0, y1 - y0
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        long_x = w >= h

        def two(frac=(1 / 3, 2 / 3)):
            return [((x0 + w * f, cy) if long_x else (cx, y0 + h * f)) for f in frac]

        k = s.kind
        if k == "bedroom":
            pts += [_pt("light", cx, cy - (h * 0.18 if not long_x else 0), s.key), _pt("fan", cx, cy + (h * 0.12 if not long_x else 0), s.key)]
            sp = _wall_spots(model, s, 4)
            pts += [_pt("socket", x, y, s.key) for x, y in sp[:3]] + ([_pt("ac", *sp[3], s.key)] if len(sp) > 3 else [_pt("ac", x1 - 100, y1 - 100, s.key)])
        elif k == "living":
            for x, y in two():
                pts.append(_pt("light", x, y, s.key))
            pts.append(_pt("fan", cx, cy, s.key))
            sp = _wall_spots(model, s, 4)
            pts += [_pt("socket", x, y, s.key) for x, y in sp[:3]] + [_pt("tv", *sp[min(3, len(sp) - 1)], s.key)]
            pts.append(_pt("ac", x1 - 120, y1 - 120, s.key))
        elif k in ("dining", "study", "entry", "passage", "store", "utility", "pooja"):
            pts.append(_pt("light", cx, cy, s.key))
            if k in ("dining", "study"):
                pts.append(_pt("fan", cx, cy + 300, s.key))
            for x, y in _wall_spots(model, s, 2 if k in ("dining", "study") else 1):
                pts.append(_pt("socket", x, y, s.key))
        elif k == "kitchen":
            pts += [_pt("light", cx, cy, s.key), _pt("exhaust", x1 - 100, y1 - 150, s.key), _pt("chimney", cx, y1 - 100, s.key)]
            sp = _wall_spots(model, s, 4)
            pts += [_pt("socket", x, y, s.key) for x, y in sp[:3]] + [_pt("fridge", x0 + 150, y0 + 150, s.key)]
        elif k == "toilet":
            pts += [_pt("light", cx, cy, s.key), _pt("exhaust", x1 - 120, y1 - 120, s.key), _pt("geyser", x0 + 150, y1 - 150, s.key)]
        elif k in ("parking", "sitout", "balcony", "terrace"):
            pts.append(_pt("light", cx, cy, s.key))
        for o in _openings(model, s):
            if o.type == "door" and k not in ("parking", "sitout", "terrace", "balcony", "stair"):
                x, y = _switch_pos(model, s, o)
                pts.append(_pt("switch", x, y, s.key))
                break
    entry = model.opening_by_mark("D1")
    db = None
    if entry and entry.level == (model.levels[0].id if model.spaces else "GF"):
        room = next((s for s in model.spaces if s.key in (entry.from_space, entry.to_space) and not s.open_boundary), None)
        if room:
            sx, sy = _switch_pos(model, room, entry)
            host = next((w for w in model.walls if w.id == entry.host), None)
            dx, dy = (-300.0, 0.0) if (host and host.horizontal) else (0.0, -300.0)
            db = dict(x=round(sx + (dx if host and host.horizontal else 0), 1), y=round(sy + (0 if host and host.horizontal else dy), 1), room=room.key)
            pts.append(_pt("db", db["x"], db["y"], room.key))
    counts: dict[str, int] = {}
    for p in pts:
        counts[p["kind"]] = counts.get(p["kind"], 0) + 1
    load = sum(LOAD_KW.get(k, 0) * n for k, n in counts.items())
    return dict(points=pts, counts=counts, connected_load_kw=round(load, 1), db=db,
                circuits=_circuits(counts))


def _circuits(c: dict) -> list[dict]:
    light_fan = c.get("light", 0) + c.get("fan", 0) + c.get("exhaust", 0) + c.get("chimney", 0)
    out = [dict(name="Lights and fans", points=light_fan, mcb="10 A", wire="1.5 mm²")]
    sockets = c.get("socket", 0) + c.get("tv", 0)
    if sockets:
        out.append(dict(name="Power sockets", points=sockets, mcb="16 A", wire="2.5 mm²"))
    if c.get("ac"):
        out.append(dict(name="Air conditioner (one per point)", points=c["ac"], mcb="16 A", wire="2.5 mm²"))
    if c.get("geyser"):
        out.append(dict(name="Water heater (one per point)", points=c["geyser"], mcb="16 A", wire="2.5 mm²"))
    if c.get("fridge"):
        out.append(dict(name="Refrigerator", points=c["fridge"], mcb="10 A", wire="2.5 mm²"))
    return out


# ---------------------------------------------------------------- plumbing
def septic_size(users: int) -> dict:
    for n, L, B, D in SEPTIC_TABLE:
        if users <= n:
            return dict(users_up_to=n, length_m=L, breadth_m=B, depth_m=D)
    n, L, B, D = SEPTIC_TABLE[-1]
    return dict(users_up_to=n, length_m=L, breadth_m=B, depth_m=D, over_table=True)


def _toilet_fixtures(model: ProjectModel, s: Space) -> dict:
    x0, y0, x1, y1 = clear_rect(model, s)
    w, h = x1 - x0, y1 - y0
    cx = (x0 + x1) / 2
    if w >= h:
        return dict(wc=(x1 - 375, y1 - 375), basin=(x0 + 350, y1 - 325), shower=(x0 + 320, y0 + 320), stack=(x1 - 120, y1 - 375), wall="e")
    return dict(wc=(cx, y1 - 770), basin=(x1 - 350, y0 + 350), shower=(x0 + 320, y0 + 320), stack=(cx, y1 - 120), wall="n")


def _sink_pos(model: ProjectModel, s: Space) -> tuple[float, float]:
    x0, y0, x1, y1 = clear_rect(model, s)
    w, h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    win = next((o for o in model.openings if o.type == "window" and s.key in (o.from_space, o.to_space)), None)
    if win and abs(win.cy - cy) > abs(win.cx - cx):
        yy = y1 - 300 if win.cy > cy else y0 + 300
        return x0 + w * 0.2 + 250, yy
    if win:
        xx = x1 - 300 if win.cx > cx else x0 + 300
        return xx, y0 + h * 0.2 + 250
    return x0 + w * 0.2 + 250, y0 + 300


def _strips(model: ProjectModel) -> list[dict]:
    """Open strips between the building and the plot boundary, with the room they leave for a tank."""
    pl = model.plot
    ob = model.outer_bounds()
    if not pl or not ob:
        return []
    W, H = pl["w"], pl["h"]
    return [dict(side="west", x0=0.0, x1=ob[0], y0=0.0, y1=H), dict(side="east", x0=ob[2], x1=W, y0=0.0, y1=H),
            dict(side="south", x0=0.0, x1=W, y0=0.0, y1=ob[1]), dict(side="north", x0=0.0, x1=W, y0=ob[3], y1=H)]


def _around(ob, gap: float, start: tuple[float, float], target: tuple[float, float], bounds: tuple[float, float] | None = None) -> list[tuple[float, float]]:
    """Route from a point on the ring round the building (outer bounds grown by `gap`) to the ring point nearest the target, then straight to it.
    The ring keeps every drain outside the walls."""
    rx0, ry0, rx1, ry1 = ob[0] - gap, ob[1] - gap, ob[2] + gap, ob[3] + gap
    if bounds:                                   # never run a drain outside the plot
        rx0, ry0 = max(rx0, CLEAR), max(ry0, CLEAR)
        rx1, ry1 = min(rx1, bounds[0] - CLEAR), min(ry1, bounds[1] - CLEAR)
    W, H = rx1 - rx0, ry1 - ry0
    per = 2 * (W + H)

    def to_t(p):                      # distance along the ring, counter-clockwise from the south-west corner
        x = min(max(p[0], rx0), rx1); y = min(max(p[1], ry0), ry1)
        d = {"s": abs(y - ry0), "e": abs(x - rx1), "n": abs(y - ry1), "w": abs(x - rx0)}
        e = min(d, key=d.get)
        return {"s": x - rx0, "e": W + (y - ry0), "n": W + H + (rx1 - x), "w": 2 * W + H + (ry1 - y)}[e]

    def at(t):
        t %= per
        if t <= W: return (rx0 + t, ry0)
        if t <= W + H: return (rx1, ry0 + t - W)
        if t <= 2 * W + H: return (rx1 - (t - W - H), ry1)
        return (rx0, ry1 - (t - 2 * W - H))

    t1, t2 = to_t(start), to_t(target)
    fwd = (t2 - t1) % per
    step_t = fwd if fwd <= per / 2 else fwd - per
    corners = [0.0, W, W + H, 2 * W + H]
    pts = []
    lo, hi = sorted((t1, t1 + step_t))
    for k in range(-1, 3):
        for c in corners:
            ct = c + k * per
            if lo < ct < hi:
                pts.append((ct, at(ct)))
    pts.sort(key=lambda a: a[0], reverse=step_t < 0)
    out = [q for _, q in pts]
    out.append(at(t1 + step_t))
    out.append(target)
    return out


def plumbing(model: ProjectModel) -> dict:
    """Fixtures, soil stacks, drain runs to inspection chambers and a septic tank, and water storage sizes."""
    fixtures, stacks, wet = [], [], []
    for s in model.spaces:
        if s.kind == "toilet":
            f = _toilet_fixtures(model, s)
            fixtures += [dict(kind="wc", x=f["wc"][0], y=f["wc"][1], room=s.key), dict(kind="basin", x=f["basin"][0], y=f["basin"][1], room=s.key),
                         dict(kind="shower", x=f["shower"][0], y=f["shower"][1], room=s.key)]
            stacks.append(dict(x=f["stack"][0], y=f["stack"][1], room=s.key, kind="soil", dia=110))
            wet.append(s)
        elif s.kind == "kitchen":
            x, y = _sink_pos(model, s)
            fixtures.append(dict(kind="sink", x=x, y=y, room=s.key))
            stacks.append(dict(x=x, y=y + (130 if y < (clear_rect(model, s)[1] + clear_rect(model, s)[3]) / 2 else -130), room=s.key, kind="waste", dia=75))
            wet.append(s)
    for i, st in enumerate(stacks, 1):
        st["id"] = f"S{i}"
    beds = sum(1 for s in model.spaces if s.kind == "bedroom")
    users = 2 * beds + 1
    tank = septic_size(users)
    ob = model.outer_bounds()
    place = None
    if ob and model.plot:
        Lo, Bo = tank["length_m"] * 1000 + 2 * WALL_T, tank["breadth_m"] * 1000 + 2 * WALL_T
        best = None
        road = {"n": "north", "e": "east", "s": "south", "w": "west"}.get(model.plot.get("road_side", ""), "")
        strips = _strips(model)
        # a tank belongs at the back or side, not in front of the entrance; use the road side only if nothing else has room
        pool = [st for st in strips if st["side"] != road] or strips
        for st in pool:
            sw, sh = st["x1"] - st["x0"], st["y1"] - st["y0"]
            # tank long axis along the strip's long direction
            if sw >= sh:
                tw, th = Lo, Bo
            else:
                tw, th = Bo, Lo
            room = min(sw - tw, sh - th)
            if best is None or room > best[0]:
                best = (room, st, tw, th)
        if best and best[0] < 600:
            for st in strips:
                if st["side"] != road:
                    continue
                sw, sh = st["x1"] - st["x0"], st["y1"] - st["y0"]
                tw, th = (Lo, Bo) if sw >= sh else (Bo, Lo)
                if min(sw - tw, sh - th) > best[0]:
                    best = (min(sw - tw, sh - th), st, tw, th)
        if best:
            room, st, tw, th = best
            # keep clear of the building and the boundary: centre in the strip, near the end that is farthest from the entry door
            cx, cy = (st["x0"] + st["x1"]) / 2, (st["y0"] + st["y1"]) / 2
            if st["side"] in ("south", "north"):
                ent = model.opening_by_mark("D1")
                cx = max(st["x0"] + tw / 2 + 300, min(st["x1"] - tw / 2 - 300, (ob[2] + ob[0]) / 2 + (ob[2] - ob[0]) * 0.3 * (-1 if ent and ent.cx > (ob[0] + ob[2]) / 2 else 1)))
            else:
                ent = model.opening_by_mark("D1")
                cy = max(st["y0"] + th / 2 + 300, min(st["y1"] - th / 2 - 300, (ob[3] + ob[1]) / 2 + (ob[3] - ob[1]) * 0.3 * (-1 if ent and ent.cy > (ob[1] + ob[3]) / 2 else 1)))
            fits = room >= 600
            place = dict(side=st["side"], cx=round(cx, 1), cy=round(cy, 1), w=round(tw, 1), h=round(th, 1), fits=fits, clearance_mm=round(room, 0))
    # drains: from each soil stack straight out through the nearest outer wall to an inspection chamber, then to the tank
    chambers, runs = [], []
    squeezed: set[str] = set()
    if ob:
        for st in stacks:
            d = {"west": st["x"] - ob[0], "east": ob[2] - st["x"], "south": st["y"] - ob[1], "north": ob[3] - st["y"]}
            side = min(d, key=d.get)
            gap = 750.0
            if side == "west":
                ic = (ob[0] - gap, st["y"])
            elif side == "east":
                ic = (ob[2] + gap, st["y"])
            elif side == "south":
                ic = (st["x"], ob[1] - gap)
            else:
                ic = (st["x"], ob[3] + gap)
            if model.plot:
                cl = (min(max(ic[0], CLEAR), model.plot["w"] - CLEAR), min(max(ic[1], CLEAR), model.plot["h"] - CLEAR))
                if math.hypot(cl[0] - ic[0], cl[1] - ic[1]) > 1:
                    squeezed.add(side)
                ic = cl
            chambers.append(dict(id=f"IC{len(chambers) + 1}", x=round(ic[0], 1), y=round(ic[1], 1), stack=st["id"]))
            path = [(st["x"], st["y"]), ic]
            if place:
                path += _around(ob, gap, ic, (place["cx"], place["cy"]), (model.plot["w"], model.plot["h"]) if model.plot else None)
            runs.append(dict(stack=st["id"], path=[(round(x, 1), round(y, 1)) for x, y in path], dia=st["dia"], slope="1:60" if st["dia"] >= 100 else "1:40"))
    warnings = []
    if squeezed or (ob and model.plot and (ob[0] < 600 or ob[1] < 600 or model.plot["w"] - ob[2] < 600 or model.plot["h"] - ob[3] < 600) and stacks):
        warnings.append("The building is close to the plot boundary on at least one side, so a drain cannot run clear of the walls there. "
                        "It must run under the floor or along the boundary. Confirm the route with your plumber.")
    demand = users * LPCD
    return dict(warnings=warnings, fixtures=fixtures, stacks=stacks, chambers=chambers, runs=runs, septic=dict(tank=tank, place=place, users=users, users_basis=USERS_FORMULA),
                water=dict(demand_l_per_day=round(demand), sump_l=round(demand), oht_l=round(demand / 3), lpcd=LPCD,
                           note="Sump about one day of demand and overhead tank about one third (assumed). Round up to the nearest standard tank."))


def mep(model: ProjectModel) -> dict:
    return dict(electrical=electrical(model), plumbing=plumbing(model))
