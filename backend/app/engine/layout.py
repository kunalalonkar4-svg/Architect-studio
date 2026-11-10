"""Deterministic parametric layout generator. Claude chooses parameters (bedrooms, stair position,
assumptions); this module owns every coordinate. Local frame: road at v=0, u along the frontage."""
from __future__ import annotations

import math

from .model import (Assumption, Brief, LayoutParams, Level, Opening, ProjectModel, Space, Stair,
                    StairFlight, Wall, SIDE_NAMES)


class ImpossibleLayout(Exception):
    def __init__(self, reasons: list[str], suggestions: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons
        self.suggestions = suggestions


# Concept assumptions, always labelled as assumptions in the model and on the sheets.
ASSUMED_SETBACKS = {"front": 3000.0, "rear": 1500.0, "left": 0.0, "right": 0.0}
MIN_BED_W = 3000.0


def local_to_world(side: str, W: float, D: float):
    """Return (point_fn, vec_fn, plot_w, plot_h) for plot-local (u,v) -> world."""
    if side == "s":
        return (lambda u, v: (u, v)), (lambda a, b: (a, b)), W, D
    if side == "n":
        return (lambda u, v: (W - u, D - v)), (lambda a, b: (-a, -b)), W, D
    if side == "e":
        return (lambda u, v: (D - v, u)), (lambda a, b: (-b, a)), D, W
    if side == "w":
        return (lambda u, v: (v, W - u)), (lambda a, b: (b, -a)), D, W
    raise ValueError(side)


def stair_flight(w: float, h: float, level_h: float) -> StairFlight:
    long_, short = max(w, h), min(w, h)
    clear_long, clear_short = long_ - 230, short - 230
    fw = min(1000.0, (clear_short - 100) / 2)
    going = 250.0
    t = int(math.floor((clear_long - fw) / going))
    if fw < 850 or t < 4:
        raise ImpossibleLayout([f"Stair space {w:.0f} x {h:.0f} mm is too small for a dog-leg stair"],
                               ["Make the stair space at least 2300 x 3000 mm", "Choose a straight-flight stair (not yet supported)"])
    n = 2 * (t + 1)
    riser = level_h / n
    if riser > 190:
        raise ImpossibleLayout([f"Stair riser would be {riser:.0f} mm (max 190 mm for comfort) at floor height {level_h:.0f} mm"],
                               ["Lengthen the stair space", "Reduce floor-to-floor height"])
    return StairFlight(risers=n, riser_mm=round(riser, 1), tread_mm=going, treads_per_flight=t,
                       flight_width=round(fw, 1), landing=round(fw, 1), clear_w=clear_short, clear_len=clear_long)


def effective_setbacks(brief: Brief, use_assumptions: bool):
    sb = {"front": brief.setbacks.front, "rear": brief.setbacks.rear,
          "left": brief.setbacks.left, "right": brief.setbacks.right}
    source, assumptions = {}, []
    for k, v in sb.items():
        if v is None:
            if not use_assumptions:
                raise ImpossibleLayout([f"{k} setback not provided"], ["Provide setbacks or choose to proceed with concept assumptions"])
            sb[k] = ASSUMED_SETBACKS[k]
            source[k] = "assumed"
            assumptions.append(Assumption(id=f"setback_{k}", text=f"{k.capitalize()} open space {ASSUMED_SETBACKS[k]:.0f} mm assumed for concept only. Verify against local rules.", kind="assumed"))
        else:
            source[k] = "user"
    return sb, source, assumptions


MAX_BEDROOMS = 5


def plan_floors(brief: Brief) -> tuple[int, int, int, list[Assumption]]:
    """(floors, ground-floor bedrooms, first-floor bedrooms, notes). One floor holds up to 2 bedrooms;
    3+ bedrooms or an explicit duplex gives a ground + first floor house."""
    B = brief.bedrooms if brief.bedrooms is not None else 2
    notes: list[Assumption] = []
    if B < 1 or B > MAX_BEDROOMS:
        raise ImpossibleLayout([f"{B} bedrooms is outside the supported range (1 to {MAX_BEDROOMS})"],
                               [f"Choose between 1 and {MAX_BEDROOMS} bedrooms"])
    floors = max(1, int(brief.levels_now or 1))
    if floors > 2:
        raise ImpossibleLayout([f"{floors} floors requested; the layout engine generates up to ground + first floor (duplex)"],
                               ["Choose a duplex (ground + first floor)", "Ask for the third floor as a future level"])
    if B >= 3 and floors == 1:
        floors = 2
        notes.append(Assumption(id="duplex_auto", text=f"{B} bedrooms do not fit one floor of this plot concept, so the house is planned as a duplex (ground + first floor).", kind="assumed"))
    if floors == 1:
        return 1, B, 0, notes
    g = 1 if B <= 4 else 2
    g = min(g, B)
    return 2, g, B - g, notes


def build_model(brief: Brief, params: LayoutParams | None = None, overrides: dict | None = None,
                use_assumptions: bool = False, roof_approved: bool = False,
                keep: ProjectModel | None = None) -> ProjectModel:
    if not (brief.plot_frontage_mm and brief.plot_depth_mm and brief.road_side):
        raise ImpossibleLayout(["Plot size and road side are required"], ["Provide plot size and the road-facing side"])
    floors, gf_beds, ff_beds, floor_notes = plan_floors(brief)
    bedrooms = gf_beds
    sb, source, asm = effective_setbacks(brief, use_assumptions)
    asm = asm + floor_notes
    fresh = params is None
    p = (params or LayoutParams()).model_copy(deep=True)
    if fresh:
        p.stair_position = brief.stair_position
    if floors == 2 and p.stair_position != "front":
        p.stair_position = "front"
        asm.append(Assumption(id="stair_front", text="Duplex uses the front stair position so the upper floor can be planned around it.", kind="assumed"))
    W, D = brief.plot_frontage_mm, brief.plot_depth_mm
    ext_t, int_t = p.ext_t, p.int_t
    BW = W - sb["left"] - sb["right"] - ext_t
    BD = D - sb["front"] - sb["rear"] - ext_t
    if fresh:   # scale rooms with the plot instead of leaving one fixed template size
        extra_w = max(0.0, BW - 9500.0)
        p.bed1_w = 3300.0 + 0.4 * extra_w
        p.kitchen_w = 2800.0 + 0.2 * extra_w if BW >= 9500 else None
        extra_d = max(0.0, BD - 10500.0)
        p.front_band = min(6000.0, 4600.0 + 0.3 * extra_d)
        p.rear_row = min(4200.0, 2900.0 + 0.3 * extra_d)
    reasons, sugg = [], []
    parking_w = p.parking_w if brief.parking is not False else p.parking_w
    colw = p.col_w_front if p.stair_position == "front" else p.col_w_rear
    if BW < parking_w + colw + 3200:
        reasons.append(f"Building width {BW:.0f} mm (plot {W:.0f} less setbacks) cannot hold parking {parking_w:.0f} + entry column {colw:.0f} + living 3200")
        sugg += ["Reduce side open space", "Drop parking from the ground floor", "Use a wider plot"]
    F, RR = p.front_band, p.rear_row
    MR = BD - F - RR
    need_mr = 3000.0 if p.stair_position == "rear" else 2400.0
    if MR < need_mr:
        reasons.append(f"Building depth {BD:.0f} mm (plot {D:.0f} less front/rear open space) is short by {need_mr - MR:.0f} mm for the middle band")
        sugg += ["Reduce front or rear open space", "Reduce the front/rear band depth"]
    bed1_w = p.bed1_w
    kw = p.kitchen_w if p.kitchen_w is not None else BW - bed1_w - 3400
    bed2_w = BW - bed1_w - kw
    if kw < 1900:
        reasons.append(f"Kitchen width would be {kw:.0f} mm (min 1900 mm)"); sugg.append("Reduce bedroom 1 width or use a wider plot")
    if bed2_w < 3300:
        reasons.append(f"Bedroom 2 width {bed2_w:.0f} mm is below 3300 mm needed to reach its door from the dining passage")
        sugg.append("Reduce kitchen or bedroom 1 width")
    if floors == 2 and BW - 1500.0 < 6000.0:
        reasons.append(f"Building width {BW:.0f} mm is too narrow for two bedrooms and a toilet side by side on the first floor")
        sugg.append("Use a wider plot or reduce side open space")
    if reasons:
        raise ImpossibleLayout(reasons, sugg)

    L = []  # (key,name,kind,x,y,w,h,open_to,open_boundary,level)
    def add(key, name, kind, x, y, w, h, open_to=(), ob=False, lvl="GF"):
        L.append(dict(key=key, name=name, kind=kind, x=x, y=y, w=w, h=h, open_to=list(open_to), open_boundary=ob, level=lvl))

    par = BW - parking_w
    mid_x = BW - p.stair_w
    if p.stair_position == "front":
        LW = BW - parking_w - colw
        add("living", "Living / Dining", "living", 0, 0, LW, F, ["dining", "entry", "stair"])
        add("entry", "Entry", "entry", LW, 0, colw, 1600, ["living"])
        add("stair", "Staircase", "stair", LW, 1600, colw, F - 1600, ["living", "dining"])
        add("dining", "Dining / Passage", "dining", 0, F, mid_x, MR, ["living", "kitchen", "stair"] if brief.kitchen_type != "closed" else ["living", "stair"])
        add("toilet", "Toilet", "toilet", mid_x, F, p.stair_w, 1800)
        add("store", "Store", "store", mid_x, F + 1800, p.stair_w, MR - 1800)
    else:
        LW = BW - parking_w - colw
        add("living", "Living / Dining", "living", 0, 0, LW, F, ["dining", "entry"])
        add("entry", "Entry", "entry", LW, 0, colw, 2400, ["living"])
        add("toilet", "Toilet", "toilet", LW, 2400, colw, F - 2400)
        add("dining", "Dining / Passage", "dining", 0, F, mid_x, MR, ["living", "kitchen", "stair"] if brief.kitchen_type != "closed" else ["living", "stair"])
        add("stair", "Staircase", "stair", mid_x, F, p.stair_w, MR, ["dining"])
    pk_name, pk_kind = ("Car Parking", "parking") if brief.parking is not False else ("Sit-out", "sitout")
    add("parking", pk_name, pk_kind, par, 0, parking_w, F, ob=True)
    ry = F + MR
    add("bed1", "Bedroom 1", "bedroom", 0, ry, bed1_w, RR)
    add("kitchen", "Kitchen", "kitchen", bed1_w, ry, kw, RR, ["dining"] if brief.kitchen_type != "closed" else [])
    if bedrooms == 2:
        add("bed2", "Bedroom 2", "bedroom", bed1_w + kw, ry, bed2_w, RR)
    else:
        add("bed2", "Study", "study", bed1_w + kw, ry, bed2_w, RR)

    # ---- first floor (duplex)
    ff = {}
    if floors == 2:
        rear_beds = max(ff_beds - 1, 0)
        names = [f"Bedroom {i}" for i in range(gf_beds + 2, gf_beds + 2 + rear_beds)]
        slots = [(n, "bedroom") for n in names]
        fillers = [("Study", "study"), ("Family Room", "living")]
        while len(slots) < 2:
            slots.append(fillers.pop(0))
        wa = (BW - 1500.0) / 2
        add("f_bed1", "Master Bedroom" if ff_beds >= 1 else "Family Room", "bedroom" if ff_beds >= 1 else "living", 0, 0, LW, F, lvl="FF")
        add("f_toilet1", "Toilet (attached)", "toilet", LW, 0, colw, 1600, lvl="FF")
        add("f_stair", "Staircase", "stair", LW, 1600, colw, F - 1600, ["f_lounge"], lvl="FF")
        add("f_balcony", "Balcony", "balcony", par, 0, parking_w, F, ob=True, lvl="FF")
        add("f_lounge", "Family Lounge", "dining", 0, F, mid_x, MR, ["f_stair"], lvl="FF")
        add("f_toilet", "Toilet", "toilet", mid_x, F, p.stair_w, 1800, lvl="FF")
        add("f_store", "Store", "store", mid_x, F + 1800, p.stair_w, MR - 1800, lvl="FF")
        add("f_roomA", slots[0][0], slots[0][1], 0, ry, wa, RR, lvl="FF")
        add("f_toilet2", "Toilet", "toilet", wa, ry, 1500.0, RR, lvl="FF")
        add("f_roomC", slots[1][0], slots[1][1], wa + 1500.0, ry, wa, RR, lvl="FF")
        for k in ("f_roomA", "f_roomC"):
            d = next(x for x in L if x["key"] == k)
            lo, hi = max(d["x"], 0.0) + 450.0, min(d["x"] + d["w"], mid_x) - 450.0
            if hi - lo < 0:
                raise ImpossibleLayout([f"{d['name']} on the first floor cannot reach the lounge passage on a building this narrow"],
                                       ["Use a wider plot", "Reduce side open space"])
            ff[k] = (lo + hi) / 2
    lvl_ids = ["GF", "FF"][:floors]
    lv_h = p.level_height

    pt, vec, PWw, PHh = local_to_world(brief.road_side, W, D)
    bx0, by0 = sb["left"] + ext_t / 2, sb["front"] + ext_t / 2
    spaces = []
    for i, d in enumerate(L):
        x1, y1 = pt(bx0 + d["x"], by0 + d["y"])
        x2, y2 = pt(bx0 + d["x"] + d["w"], by0 + d["y"] + d["h"])
        spaces.append(Space(id=f"S{i+1:02d}", level=d["level"], key=d["key"], name=d["name"], kind=d["kind"],
                            x=min(x1, x2), y=min(y1, y2), w=abs(x2 - x1), h=abs(y2 - y1),
                            open_to=d["open_to"], open_boundary=d["open_boundary"]))
    p.kitchen_w = kw   # freeze: later edits keep the kitchen size unless it is edited explicitly
    levels = [Level(id="GF", name="Ground Floor", elevation=0.0, height=lv_h)]
    if floors == 2:
        levels.append(Level(id="FF", name="First Floor", elevation=lv_h, height=lv_h))
    lv = levels[0]
    model = ProjectModel(plot=dict(w=PWw, h=PHh, frontage=W, depth=D, road_side=brief.road_side,
                                   setbacks=sb, setback_source=source, local_origin=[bx0, by0], bw=BW, bd=BD),
                         levels=levels, spaces=spaces, params=p, opening_overrides=dict(overrides or {}),
                         assumptions=list(brief.assumptions) + asm, roof_approved=roof_approved)
    # openings (local description -> world)
    def S(key): return next(d for d in L if d["key"] == key)
    ops: list[dict] = []
    def door(key, u, v, w, swing, hinge="start", note="", level="GF"):
        ops.append(dict(key=key, type="door", u=u, v=v, width=w, height=2100.0, sill=0.0, swing=swing, hinge=hinge, note=note, level=level))
    def win(key, u, v, w, h, sill, note="", level="GF"):
        ops.append(dict(key=key, type="window", u=u, v=v, width=w, height=h, sill=sill, swing=(0, 1), hinge="start", note=note, level=level))
    en = S("entry")
    door("entry", en["x"] + en["w"] / 2, 0, 1000 if en["w"] >= 1500 else 900, (0, 1), "start", "Main entrance")
    b1 = S("bed1"); b2 = S("bed2"); k = S("kitchen"); lv_ = S("living"); dn = S("dining")
    door("bed1_door", b1["w"] / 2, ry, 900, (0, 1))
    ov0 = b2["x"]; ov1 = dn["x"] + dn["w"]
    door("bed2_door", (ov0 + ov1) / 2, ry, 900, (0, 1), "end")
    tl = S("toilet")
    door("toilet_door", tl["x"], tl["y"] + (900 if p.stair_position == "front" else (tl["h"] / 2)), 750, (1, 0))
    if p.stair_position == "front":
        st = S("store")
        door("store_door", st["x"], st["y"] + st["h"] / 2, 800, (1, 0))
    if brief.kitchen_type == "closed":
        door("kitchen_door", k["x"] + k["w"] / 2, ry, 900, (0, 1))
    win("living_window", lv_["x"] + lv_["w"] / 2, 0, min(1500.0, lv_["w"] - 800), 1200.0, 900.0)
    win("bed1_window", b1["w"] / 2, BD, 1500.0, 1200.0, 900.0)
    win("kitchen_window", k["x"] + k["w"] / 2, BD, min(1000.0, k["w"] - 600), 1000.0, 1000.0)
    win("bed2_window", b2["x"] + b2["w"] / 2, BD, 1500.0, 1200.0, 900.0)
    if sb["left"] >= 900:
        win("bed1_side_window", 0, ry + RR / 2, 1200.0, 1200.0, 900.0, "Side window (left open space)")
    if sb["right"] >= 900:
        win("bed2_side_window", BW, ry + RR / 2, 1200.0, 1200.0, 900.0, "Side window (right open space)")
        if p.stair_position == "front":
            win("toilet_vent", BW, tl["y"] + 900, 600.0, 450.0, 1500.0, "Ventilator")
    order_d = ["entry", "bed1_door", "bed2_door", "toilet_door", "store_door", "kitchen_door"]
    order_w = ["living_window", "bed1_window", "kitchen_window", "bed2_window", "bed1_side_window", "bed2_side_window", "toilet_vent"]
    if floors == 2:
        FL = "FF"
        A, C, T2 = S("f_roomA"), S("f_roomC"), S("f_toilet2")
        door("f_master_door", LW / 2, F, 900, (0, -1), "start", level=FL)
        door("f_toilet1_door", LW, 800, 750, (1, 0), level=FL)
        door("f_balcony_door", par, 1600 + (F - 1600) / 2, 900, (1, 0), "start", "Balcony", level=FL)
        door("f_toilet_door", mid_x, F + 900, 750, (1, 0), level=FL)
        door("f_store_door", mid_x, F + 1800 + (MR - 1800) / 2, 800, (1, 0), level=FL)
        door("f_roomA_door", ff["f_roomA"], ry, 900, (0, 1), "start", level=FL)
        door("f_toilet2_door", min(T2["x"] + 750.0, mid_x - 450.0), ry, 750, (0, 1), "start", level=FL)
        door("f_roomC_door", ff["f_roomC"], ry, 900, (0, 1), "end", level=FL)
        win("f_master_window", LW / 2, 0, min(1500.0, LW - 800), 1200.0, 900.0, level=FL)
        win("f_toilet1_window", LW + colw / 2, 0, 600.0, 450.0, 1500.0, "Ventilator", level=FL)
        win("f_roomA_window", A["x"] + A["w"] / 2, BD, 1500.0, 1200.0, 900.0, level=FL)
        win("f_toilet2_window", T2["x"] + T2["w"] / 2, BD, 600.0, 450.0, 1500.0, "Ventilator", level=FL)
        win("f_roomC_window", C["x"] + C["w"] / 2, BD, 1500.0, 1200.0, 900.0, level=FL)
        if sb["left"] >= 900:
            win("f_master_side_window", 0, F / 2, 1200.0, 1200.0, 900.0, "Side window (left open space)", level=FL)
            win("f_roomA_side_window", 0, ry + RR / 2, 1200.0, 1200.0, 900.0, "Side window (left open space)", level=FL)
        if sb["right"] >= 900:
            win("f_roomC_side_window", BW, ry + RR / 2, 1200.0, 1200.0, 900.0, "Side window (right open space)", level=FL)
            win("f_toilet_vent", BW, F + 900, 600.0, 450.0, 1500.0, "Ventilator", level=FL)
        order_d += ["f_master_door", "f_toilet1_door", "f_balcony_door", "f_toilet_door", "f_store_door", "f_roomA_door", "f_toilet2_door", "f_roomC_door"]
        order_w += ["f_master_window", "f_toilet1_window", "f_roomA_window", "f_toilet2_window", "f_roomC_window",
                    "f_master_side_window", "f_roomA_side_window", "f_roomC_side_window", "f_toilet_vent"]
    di = wi = 0
    for o in sorted(ops, key=lambda o: (0 if o["type"] == "door" else 1, (order_d if o["type"] == "door" else order_w).index(o["key"]))):
        if o["type"] == "door":
            di += 1; mark = f"D{di}"
        else:
            wi += 1; mark = f"W{wi}"
        wx, wy = pt(bx0 + o["u"], by0 + o["v"])
        sx, sy = vec(*o["swing"])
        ov = (overrides or {}).get(o["key"], {})
        op = Opening(id=f"O-{o['key']}", key=o["key"], mark=mark, level=o["level"], type=o["type"], cx=wx, cy=wy,
                     width=ov.get("width", o["width"]), height=ov.get("height", o["height"]),
                     sill=ov.get("sill", o["sill"]), swing=[sx, sy], hinge=ov.get("hinge", o["hinge"]), note=o["note"])
        sh = ov.get("shift", 0.0)
        if sh:
            if abs(sx) > 0.5:   # wall runs along y
                op.cy += sh
            else:
                op.cx += sh
        model.openings.append(op)
    # stairs (one per floor; the lower flight is shared)
    sp = model.space("stair")
    fl = stair_flight(sp.w, sp.h, lv.height)
    sv = vec(0, 1) if p.stair_position == "front" else vec(0, -1)
    run = "y" if sp.h >= sp.w else "x"
    model.stairs.append(Stair(space_id=sp.id, x=sp.x, y=sp.y, w=sp.w, h=sp.h, run_axis=run, flight=fl, start=[float(sv[0]), float(sv[1])]))
    if floors == 2:
        sp2 = model.space("f_stair")
        model.stairs.append(Stair(id="ST2", level="FF", space_id=sp2.id, x=sp2.x, y=sp2.y, w=sp2.w, h=sp2.h, run_axis=run,
                                  flight=fl, start=[float(sv[0]), float(sv[1])]))
    refresh_walls(model)
    return model


def _space_at(spaces, x, y):
    for s in spaces:
        if s.x - 1e-6 <= x < s.x2 - 1e-6 and s.y - 1e-6 <= y < s.y2 - 1e-6:
            return s
    return None


def derive_walls(model: ProjectModel) -> list[Wall]:
    ext_t, int_t = model.params.ext_t, model.params.int_t
    segs = []   # (orient, c, a, b, kind)
    for lvl in [l.id for l in model.levels if any(s.level == l.id for s in model.spaces)]:
        sps = [s for s in model.spaces if s.level == lvl]
        for orient in ("h", "v"):
            lines: dict[float, list] = {}
            for s in sps:
                if orient == "h":
                    for c in (s.y, s.y2):
                        lines.setdefault(round(c, 3), []).append((s.x, s.x2))
                else:
                    for c in (s.x, s.x2):
                        lines.setdefault(round(c, 3), []).append((s.y, s.y2))
            for c, ivs in lines.items():
                bps = sorted({round(v, 3) for iv in ivs for v in iv})
                for a, b in zip(bps, bps[1:]):
                    if not any(iv[0] <= a + 1e-6 and iv[1] >= b - 1e-6 for iv in ivs):
                        continue
                    m = (a + b) / 2
                    if orient == "h":
                        s1, s2 = _space_at(sps, m, c - 1), _space_at(sps, m, c + 1)
                    else:
                        s1, s2 = _space_at(sps, c - 1, m), _space_at(sps, c + 1, m)
                    if s1 is None and s2 is None:
                        continue
                    if s1 is None or s2 is None:
                        sx = s1 or s2
                        if sx.open_boundary:
                            continue
                        kind = "ext"
                    else:
                        if s1.key in s2.open_to or s2.key in s1.open_to:
                            continue
                        kind = "ext" if (s1.open_boundary or s2.open_boundary) else "int"
                    segs.append((orient, c, a, b, kind, lvl))
    walls: list[Wall] = []
    segs.sort(key=lambda t: (t[0], t[1], t[4], t[2]))
    merged = []
    for sgm in segs:
        if merged and merged[-1][0] == sgm[0] and merged[-1][1] == sgm[1] and merged[-1][4] == sgm[4] \
                and merged[-1][5] == sgm[5] and abs(merged[-1][3] - sgm[2]) < 1e-6:
            merged[-1] = (sgm[0], sgm[1], merged[-1][2], sgm[3], sgm[4], sgm[5])
        else:
            merged.append(sgm)
    for i, (orient, c, a, b, kind, lvl) in enumerate(merged, 1):
        t = ext_t if kind == "ext" else int_t
        if orient == "h":
            walls.append(Wall(id=f"W{i:02d}", level=lvl, x1=a, y1=c, x2=b, y2=c, thickness=t, kind=kind))
        else:
            walls.append(Wall(id=f"W{i:02d}", level=lvl, x1=c, y1=a, x2=c, y2=b, thickness=t, kind=kind))
    return walls


def host_wall(model: ProjectModel, o: Opening):
    for w in model.walls:
        if w.level != o.level:
            continue
        if w.horizontal:
            if abs(o.cy - w.y1) < 1.0 and min(w.x1, w.x2) - 1 <= o.cx <= max(w.x1, w.x2) + 1:
                return w
        else:
            if abs(o.cx - w.x1) < 1.0 and min(w.y1, w.y2) - 1 <= o.cy <= max(w.y1, w.y2) + 1:
                return w
    return None


def refresh_walls(model: ProjectModel) -> None:
    model.walls = derive_walls(model)
    for o in model.openings:
        w = host_wall(model, o)
        o.host = w.id if w else None
        # which spaces does the host wall separate?
        if w:
            sl = [x for x in model.spaces if x.level == o.level]
            if w.horizontal:
                a, b = _space_at(sl, o.cx, o.cy - 1), _space_at(sl, o.cx, o.cy + 1)
            else:
                a, b = _space_at(sl, o.cx - 1, o.cy), _space_at(sl, o.cx + 1, o.cy)
            o.from_space, o.to_space = (a.key if a else None), (b.key if b else None)


def wall_offset(w: Wall, o: Opening) -> float:
    """Distance from the wall start to the opening's start edge."""
    c = (o.cx - min(w.x1, w.x2)) if w.horizontal else (o.cy - min(w.y1, w.y2))
    return c - o.width / 2


def clear_rect(model: ProjectModel, s: Space):
    """Room rectangle measured to wall faces (net/clear) and the method note."""
    def edge_t(orient, c, a, b, side):
        mid = (a + b) / 2
        best = 0.0
        for w in model.walls:
            if w.level != s.level:
                continue
            if orient == "h" and w.horizontal and abs(w.y1 - c) < 1 and min(w.x1, w.x2) - 1 <= mid <= max(w.x1, w.x2) + 1:
                best = max(best, w.thickness)
            if orient == "v" and (not w.horizontal) and abs(w.x1 - c) < 1 and min(w.y1, w.y2) - 1 <= mid <= max(w.y1, w.y2) + 1:
                best = max(best, w.thickness)
        return best
    # use the dominant wall along each edge; walls may be split by openings only in drawing, not here
    tl = edge_t("v", s.x, s.y, s.y2, "l") / 2
    tr = edge_t("v", s.x2, s.y, s.y2, "r") / 2
    tb = edge_t("h", s.y, s.x, s.x2, "b") / 2
    tt = edge_t("h", s.y2, s.x, s.x2, "t") / 2
    return (s.x + tl, s.y + tb, s.x2 - tr, s.y2 - tt)


AREA_METHOD = ("Net internal area = clear length x clear width, measured between finished wall faces "
               "(wall centrelines less half the wall thickness each side). Door/window recesses and open "
               "edges are not deducted. Units: mm and m².")


def room_metrics(model: ProjectModel, s: Space) -> dict:
    x1, y1, x2, y2 = clear_rect(model, s)
    cw, cd = x2 - x1, y2 - y1
    return dict(clear_w=cw, clear_d=cd, area_m2=cw * cd / 1e6, gross_m2=s.w * s.h / 1e6)
