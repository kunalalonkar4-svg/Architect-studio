"""Design review for a concept model: planning limits, Vastu direction score, light and ventilation, and structural grid logic.

Everything here reads the canonical model (millimetres, +y = true north) and never changes it. Results are advisory:
* Planning limits are checked only against values the user supplies from their own authority. Nothing is guessed per city.
* Vastu is a traditional guideline, not a building code.
* Light and ventilation ratios use commonly applied values; local bye-laws differ.
* The column grid is a planning aid, not a structural design.
"""
from __future__ import annotations

import math

from .layout import room_metrics
from .model import Opening, ProjectModel, Space

SQM_PER_SQFT = 0.09290304
HABITABLE = {"bedroom", "living", "dining", "kitchen", "study"}
COMPASS = ["E", "NE", "N", "NW", "W", "SW", "S", "SE"]

# Longest slab span (mm) that is usually economical without deep beams. Planning aid only.
SPAN_NOTE_MM = 4500.0
SPAN_WARN_MM = 6000.0
MIN_CLEAR_HEIGHT_MM = 2750.0


def _row(code: str, status: str, title: str, detail: str, objects: list[str] | None = None, fix: str = "") -> dict:
    return dict(code=code, status=status, title=title, detail=detail, objects=objects or [], fix=fix)


def compass(dx: float, dy: float) -> str:
    """Eight-point compass direction of a vector in plot coordinates (+x east, +y north)."""
    ang = math.degrees(math.atan2(dy, dx)) % 360
    return COMPASS[int(((ang + 22.5) % 360) // 45)]


# ---------------------------------------------------------------- planning limits
def planning_limits(model: ProjectModel, far_max: float | None = None, coverage_max_pct: float | None = None,
                    height_max_m: float | None = None) -> dict:
    """Measured FAR, ground coverage and height, compared with limits the user supplies from the local authority."""
    pl = model.plot or {}
    plot_area = (pl.get("w", 0) * pl.get("h", 0)) / 1e6
    ob = model.outer_bounds()
    items: list[dict] = []
    if not plot_area or not ob:
        return dict(measured={}, items=[_row("no_plot", "info", "Plot not set", "Plot size is needed for FAR and coverage.")])
    ground = (ob[2] - ob[0]) * (ob[3] - ob[1]) / 1e6
    # Open parking / porches count in coverage when roofed; the footprint box is the safe measure at concept stage.
    built_up = ground * len(model.levels)
    far = built_up / plot_area
    coverage = ground / plot_area * 100
    top = model.top_level
    height = (top.elevation + top.height + top.parapet) / 1000
    measured = dict(plot_area_m2=round(plot_area, 2), plot_area_sqft=round(plot_area / SQM_PER_SQFT, 0), ground_footprint_m2=round(ground, 2),
                    built_up_m2=round(built_up, 2), far=round(far, 2), coverage_pct=round(coverage, 1), height_m=round(height, 2))

    def cmp(code, label, value, limit, unit, fmt):
        if limit is None:
            items.append(_row(code, "info", f"{label}: {fmt(value)}{unit}", "Enter the limit from your local authority to check this.",
                              fix="Add the permitted value from your development control rules."))
        elif value <= limit + 1e-9:
            items.append(_row(code, "ok", f"{label}: {fmt(value)}{unit} within {fmt(limit)}{unit}", f"{fmt(limit - value)}{unit} to spare."))
        else:
            items.append(_row(code, "fail", f"{label}: {fmt(value)}{unit} exceeds {fmt(limit)}{unit}", f"Over by {fmt(value - limit)}{unit}.",
                              fix="Reduce the footprint or floors, or confirm the limit with your local authority."))

    cmp("far", "FAR", far, far_max, "", lambda v: f"{v:.2f}")
    cmp("coverage", "Ground coverage", coverage, coverage_max_pct, "%", lambda v: f"{v:.1f}")
    cmp("height", "Height with parapet", height, height_max_m, " m", lambda v: f"{v:.2f}")
    sb = pl.get("setbacks") or {}
    src = pl.get("setback_source") or {}
    if any(s == "assumed" for s in src.values()):
        items.append(_row("setbacks_assumed", "warn", "Open space values are assumptions",
                          "Front, rear or side open space was not supplied, so concept values were used.",
                          fix="Replace with the values your authority requires, then regenerate."))
    elif sb:
        items.append(_row("setbacks_supplied", "ok", "Open space values supplied by you",
                          ", ".join(f"{k} {v / 1000:.2f} m" for k, v in sb.items())))
    return dict(measured=measured, items=items)


# ---------------------------------------------------------------- Vastu
# Preferred and acceptable zones for each room, in the usual textbook order. Zones are the eight compass sectors around the plot centre.
VASTU = {
    "kitchen": dict(good={"SE"}, ok={"NW"}, avoid={"NE", "SW", "N"}),
    "pooja": dict(good={"NE"}, ok={"N", "E"}, avoid={"S", "SW", "SE"}),
    "toilet": dict(good={"NW", "W"}, ok={"S", "SE"}, avoid={"NE", "SW"}),
    "living": dict(good={"N", "NE", "E"}, ok={"NW"}, avoid={"SW"}),
    "stair": dict(good={"S", "W", "SW"}, ok={"SE", "NW"}, avoid={"NE"}),
    "store": dict(good={"NW", "SW", "W"}, ok={"S"}, avoid={"NE"}),
    "dining": dict(good={"W", "E"}, ok={"N", "NW"}, avoid={"SW"}),
    "study": dict(good={"W", "NE", "N", "E"}, ok={"NW"}, avoid={"S"}),
}
ENTRANCE = dict(good={"N", "NE", "E"}, ok={"NW", "SE"}, avoid={"S", "SW", "W"})
POINTS = {"good": 1.0, "ok": 0.6, "avoid": 0.0}


def _zone(cx: float, cy: float, ox: float, oy: float) -> str:
    return compass(cx - ox, cy - oy)


def _grade(zone: str, rule: dict) -> str:
    return "good" if zone in rule["good"] else "ok" if zone in rule["ok"] else "avoid" if zone in rule["avoid"] else "ok"


def _entrance(model: ProjectModel) -> Opening | None:
    d = model.opening_by_mark("D1")
    if d and d.type == "door":
        return d
    return next((o for o in model.openings if o.type == "door" and o.level == "GF"), None)


def vastu(model: ProjectModel) -> dict:
    """Score the placement of rooms and the entrance by compass zone of the building centre."""
    fp = model.footprint()
    if not fp:
        return dict(score=None, items=[], note="No layout yet.")
    ox, oy = (fp[0] + fp[2]) / 2, (fp[1] + fp[3]) / 2
    items, pts, wt = [], 0.0, 0.0

    def add(code, title, zone, grade, weight, why):
        nonlocal pts, wt
        pts += POINTS[grade] * weight; wt += weight
        status = {"good": "ok", "ok": "info", "avoid": "warn"}[grade]
        items.append(_row(code, status, f"{title} in {zone}", why))

    for s in sorted(model.spaces, key=lambda s: (s.level, s.key)):
        if s.kind in VASTU:
            zone = _zone((s.x + s.x2) / 2, (s.y + s.y2) / 2, ox, oy)
            r = VASTU[s.kind]
            g = _grade(zone, r)
            why = (f"Preferred: {', '.join(sorted(r['good']))}." if g != "good" else "Matches the preferred zone.")
            add(f"vastu_{s.key}", s.name, zone, g, 2.0 if s.kind in ("kitchen", "pooja") else 1.0, why)
    beds = [s for s in model.spaces if s.kind == "bedroom"]
    if beds:
        master = max(beds, key=lambda s: s.w * s.h)
        zone = _zone((master.x + master.x2) / 2, (master.y + master.y2) / 2, ox, oy)
        r = dict(good={"SW"}, ok={"S", "W", "NW"}, avoid={"NE", "SE"})
        g = _grade(zone, r)
        add("vastu_master", f"Largest bedroom ({master.name})", zone, g, 2.0, "Preferred: SW." if g != "good" else "Matches the preferred zone.")
    d = _entrance(model)
    if d:
        zone = _zone(d.cx, d.cy, ox, oy)
        g = _grade(zone, ENTRANCE)
        add("vastu_entrance", "Main entrance", zone, g, 2.0, "Preferred: N, NE or E." if g != "good" else "Matches the preferred zone.")
    # Brahmasthan: the central zone is traditionally kept open and light.
    cx, cy = ox, oy
    centre = [s for s in model.spaces if s.x < cx < s.x2 and s.y < cy < s.y2 and s.level == "GF"]
    if centre:
        c = centre[0]
        g = "avoid" if c.kind in ("toilet", "kitchen", "store", "stair") else "good"
        add("vastu_centre", "Centre of the house is a " + c.name, "centre", g, 1.0,
            "Traditionally kept open: avoid toilet, kitchen, store or stair here." if g == "avoid" else "Centre sits in a living or circulation space.")
    score = round(100 * pts / wt) if wt else None
    return dict(score=score, items=items,
                note="Vastu is a traditional guideline, not a building code. Zones are the eight compass sectors around the building centre, "
                     "with true north taken as +y in the drawing.")


# ---------------------------------------------------------------- light and ventilation
def light_and_ventilation(model: ProjectModel, min_ratio: float = 0.10) -> dict:
    """Window area against floor area for habitable rooms, ceiling height, and toilet ventilation."""
    items = []
    for s in model.spaces:
        if s.open_boundary:
            continue
        m = room_metrics(model, s)
        area = m["area_m2"]
        wins = [o for o in model.openings if o.type == "window" and s.key in (o.from_space, o.to_space)]
        wa = sum(o.width * o.height for o in wins) / 1e6
        if s.kind in HABITABLE:
            ratio = wa / area if area else 0.0
            if ratio < min_ratio - 1e-9:
                items.append(_row("ventilation_low", "warn", f"{s.name}: windows are {ratio * 100:.1f}% of floor area",
                                  f"{wa:.2f} m² of window for {area:.1f} m² of floor. Commonly at least {min_ratio * 100:.0f}% is asked for.",
                                  [s.key], "Enlarge a window or add one on an external wall."))
            elif ratio < 1 / 6 - 1e-9:
                items.append(_row("ventilation_ok", "ok", f"{s.name}: windows are {ratio * 100:.1f}% of floor area",
                                  f"Meets {min_ratio * 100:.0f}%. Some local bye-laws ask for one sixth (16.7%), so check yours.", [s.key]))
            else:
                items.append(_row("ventilation_ok", "ok", f"{s.name}: windows are {ratio * 100:.1f}% of floor area", "Meets the usual ratios.", [s.key]))
        elif s.kind == "toilet":
            if not wins:
                items.append(_row("toilet_shaft", "warn", f"{s.name} has no external window",
                                  "Needs a ventilation shaft or mechanical extract. Plan a shaft position now so beams and columns do not clash.",
                                  [s.key], "Move the toilet to an external wall or reserve a shaft."))
            else:
                items.append(_row("toilet_vent", "ok", f"{s.name} has an external window", "", [s.key]))
    lv = model.level()
    clear = lv.height - lv.slab
    if clear < MIN_CLEAR_HEIGHT_MM:
        items.append(_row("ceiling_low", "warn", f"Clear height about {clear:.0f} mm",
                          f"Habitable rooms are usually asked to be at least {MIN_CLEAR_HEIGHT_MM:.0f} mm clear.", fix="Increase the floor height."))
    else:
        items.append(_row("ceiling_ok", "ok", f"Clear height about {clear:.0f} mm", "Meets the usual minimum."))
    # cross ventilation: a habitable room with windows on two different faces moves air better
    for s in model.spaces:
        if s.kind in ("bedroom", "living") and not s.open_boundary:
            faces = set()
            for o in model.openings:
                if o.type == "window" and s.key in (o.from_space, o.to_space):
                    faces.add(_wall_face(model, s, o))
            if len(faces) == 1:
                items.append(_row("cross_vent", "info", f"{s.name}: all windows on one side ({', '.join(faces)})",
                                  "A second window on another wall allows cross ventilation.", [s.key]))
    return dict(items=items)


def _wall_face(model: ProjectModel, s: Space, o: Opening) -> str:
    """Which wall of the room the opening is on."""
    dx, dy = o.cx - (s.x + s.x2) / 2, o.cy - (s.y + s.y2) / 2
    if abs(dx) >= abs(dy):
        return "east" if dx > 0 else "west"
    return "north" if dy > 0 else "south"


# ---------------------------------------------------------------- structural grid
def column_grid(model: ProjectModel) -> dict:
    """Columns at wall corners and junctions, then span checks along each grid line."""
    pts: dict[tuple[int, int], set[str]] = {}
    for w in model.walls:
        for x, y in ((w.x1, w.y1), (w.x2, w.y2)):
            pts.setdefault((round(x / 10) * 10, round(y / 10) * 10), set()).add(w.id)
    cols = [dict(x=x, y=y) for (x, y) in sorted(pts)]
    items = []
    by_y: dict[int, list[int]] = {}
    by_x: dict[int, list[int]] = {}
    for c in cols:
        by_y.setdefault(c["y"], []).append(c["x"])
        by_x.setdefault(c["x"], []).append(c["y"])

    def wall_between(horizontal: bool, fixed: int, a: int, b: int) -> bool:
        for w in model.walls:
            if horizontal and w.horizontal and abs(w.y1 - fixed) < 15 and min(w.x1, w.x2) <= a + 15 and max(w.x1, w.x2) >= b - 15:
                return True
            if (not horizontal) and not w.horizontal and abs(w.x1 - fixed) < 15 and min(w.y1, w.y2) <= a + 15 and max(w.y1, w.y2) >= b - 15:
                return True
        return False

    worst = 0.0
    for horizontal, table in ((True, by_y), (False, by_x)):
        for fixed, vals in table.items():
            vals = sorted(set(vals))
            for a, b in zip(vals, vals[1:]):
                span = b - a
                worst = max(worst, span)
                walled = wall_between(horizontal, fixed, a, b)
                where = f"{'y' if horizontal else 'x'} = {fixed / 1000:.2f} m, {a / 1000:.2f} to {b / 1000:.2f} m"
                if span > SPAN_WARN_MM:
                    items.append(_row("span_long", "warn", f"Span of {span / 1000:.2f} m between columns", f"At {where}. Needs a deep beam or an extra column.",
                                      fix="Add a column or move a wall so spans stay under 6 m."))
                elif span > SPAN_NOTE_MM and not walled:
                    items.append(_row("span_unwalled", "info", f"Span of {span / 1000:.2f} m with no wall below",
                                      f"At {where}. The beam here would sit inside a room.", fix="Add a column or shift a partition under the beam."))
    # slab panels: any room whose short side is long needs a deeper slab or a beam through it
    for s in model.spaces:
        if s.open_boundary:
            continue
        m = room_metrics(model, s)
        short = min(m["clear_w"], m["clear_d"])
        if short > SPAN_NOTE_MM:
            items.append(_row("panel_wide", "info", f"{s.name} is {short / 1000:.2f} m across", "A slab panel this wide needs extra depth or a beam through the room.", [s.key]))
    if not items:
        items.append(_row("grid_ok", "ok", "Column spans are within about 4.5 m", "No beam is expected to cut through a room."))
    return dict(columns=cols, longest_span_m=round(worst / 1000, 2), items=items,
                note="Columns are placed at wall corners and junctions as a planning aid. A structural engineer sets the real grid.")


# ---------------------------------------------------------------- everything
def review(model: ProjectModel, far_max: float | None = None, coverage_max_pct: float | None = None,
           height_max_m: float | None = None, min_window_ratio: float = 0.10) -> dict:
    rules = planning_limits(model, far_max, coverage_max_pct, height_max_m)
    v = vastu(model)
    lv = light_and_ventilation(model, min_window_ratio)
    g = column_grid(model)
    allitems = rules["items"] + lv["items"] + g["items"]
    counts = dict(fail=sum(i["status"] == "fail" for i in allitems), warn=sum(i["status"] == "warn" for i in allitems),
                  ok=sum(i["status"] == "ok" for i in allitems), info=sum(i["status"] == "info" for i in allitems))
    return dict(planning=rules, vastu=v, light_ventilation=lv, grid=g, counts=counts,
                disclaimer="Advisory checks on a concept drawing. Limits come only from values you enter. Vastu is a traditional guideline. "
                           "None of this replaces approval by your local authority or the design of a licensed architect and structural engineer.")
