"""Model validation: boundary containment, geometry, hosts, levels, stair, cross-view agreement."""
from __future__ import annotations

from .layout import room_metrics, wall_offset
from .model import ProjectModel


def issue(code, severity, message, objects=None, fix=None):
    return dict(code=code, severity=severity, message=message, objects=objects or [], fix=fix or "")


def validate_model(model: ProjectModel) -> list[dict]:
    out: list[dict] = []
    if not model.spaces:
        return [issue("no_model", "error", "No layout has been generated yet.", fix="Generate the layout from the brief.")]
    pl = model.plot or {}
    ob = model.outer_bounds()
    # --- boundary containment against supplied constraints
    if pl:
        sb, src = pl["setbacks"], pl["setback_source"]
        by = {"s": {"front": "y0", "rear": "y1", "left": "x0", "right": "x1"},
              "n": {"front": "y1", "rear": "y0", "left": "x1", "right": "x0"},
              "e": {"front": "x1", "rear": "x0", "left": "y0", "right": "y1"},
              "w": {"front": "x0", "rear": "x1", "left": "y1", "right": "y0"}}[pl["road_side"]]
        lim = {}
        for k, side in by.items():
            lim[side] = sb[k]
        tol = 1.5
        chk = [("x0", ob[0] - lim["x0"]), ("y0", ob[1] - lim["y0"]), ("x1", pl["w"] - lim["x1"] - ob[2]), ("y1", pl["h"] - lim["y1"] - ob[3])]
        for side, margin in chk:
            if margin < -tol:
                name = next(k for k, v in by.items() if v == side)
                out.append(issue("boundary_violation", "error",
                                 f"Building projects {-margin:.0f} mm into the {name} open space ({src[name]} value {lim[side]:.0f} mm).",
                                 [name], "Reduce the footprint or the open-space value."))
        for k, s in src.items():
            if s == "assumed":
                out.append(issue("assumed_setback", "warning", f"{k.capitalize()} open space {sb[k]:.0f} mm is a concept assumption.", [k],
                                 "Replace with the value required by your local rules."))
    # --- spaces
    sps = model.spaces
    for i, a in enumerate(sps):
        for b in sps[i + 1:]:
            if a.level != b.level:
                continue
            ox = min(a.x2, b.x2) - max(a.x, b.x); oy = min(a.y2, b.y2) - max(a.y, b.y)
            if ox > 1 and oy > 1:
                out.append(issue("rooms_overlap", "error", f"{a.name} and {b.name} overlap by {ox:.0f} x {oy:.0f} mm.", [a.key, b.key], "Resize or move one room."))
    f = model.footprint()
    for s in sps:
        m = room_metrics(model, s)
        if s.kind == "bedroom" and (min(m["clear_w"], m["clear_d"]) < 2400 or m["area_m2"] < 9.0):
            out.append(issue("room_small", "warning", f"{s.name} is {m['clear_w']:.0f} x {m['clear_d']:.0f} mm ({m['area_m2']:.1f} m²), below the commonly used 9.0 m² / 2.4 m minimum. Check local code.", [s.key],
                             "Increase the room size or confirm the requirement."))
        if s.kind == "kitchen" and (min(m["clear_w"], m["clear_d"]) < 1800 or m["area_m2"] < 4.5):
            out.append(issue("room_small", "warning", f"Kitchen is {m['clear_w']:.0f} x {m['clear_d']:.0f} mm ({m['area_m2']:.1f} m²), small for a working kitchen.", [s.key]))
        if s.kind == "toilet" and m["area_m2"] < 1.8:
            out.append(issue("room_small", "warning", f"{s.name} is only {m['area_m2']:.1f} m².", [s.key]))
        if s.kind in ("bedroom", "kitchen", "living", "study"):
            ext_open = [o for o in model.openings if o.type == "window" and s.key in (o.from_space, o.to_space)]
            if not ext_open:
                out.append(issue("no_daylight_opening", "warning", f"{s.name} has no external window.", [s.key], "Add a window on an external wall or confirm borrowed light/ventilation."))
        if s.kind == "toilet":
            if not [o for o in model.openings if o.type == "window" and s.key in (o.from_space, o.to_space)]:
                out.append(issue("no_vent_toilet", "info", f"{s.name} has no external opening; provide mechanical ventilation or a shaft.", [s.key]))
        # reachable door?
        if s.kind in ("bedroom", "toilet", "store", "study"):
            if not [o for o in model.openings if o.type == "door" and s.key in (o.from_space, o.to_space)]:
                out.append(issue("no_door", "error", f"{s.name} has no door.", [s.key], "Add a door."))
    # --- walls
    for w in model.walls:
        if w.thickness < 100:
            out.append(issue("thin_wall", "error", f"Wall {w.id} is {w.thickness:.0f} mm thick.", [w.id]))
    # --- openings
    lv = model.level()
    for o in model.openings:
        w = next((x for x in model.walls if x.id == o.host), None)
        if not w:
            out.append(issue("opening_no_host", "error", f"{o.mark} ({o.type}) is not on a wall.", [o.mark], "Move it onto a wall segment."))
            continue
        off = wall_offset(w, o)
        if off < 100 - 1e-6 or off + o.width > w.length - 100 + 1e-6:
            out.append(issue("opening_outside_wall", "error", f"{o.mark} ({o.width:.0f} mm) does not fit its host wall {w.id} ({w.length:.0f} mm) with 100 mm end clearance.", [o.mark],
                             "Reduce the width or choose a longer wall."))
        if o.width < 500 or o.height < 300:
            out.append(issue("opening_size", "error", f"{o.mark} has an unusable size {o.width:.0f} x {o.height:.0f} mm.", [o.mark]))
        if o.type == "door" and (o.width < 700):
            out.append(issue("door_narrow", "warning", f"Door {o.mark} is {o.width:.0f} mm wide, under the usual 750 mm minimum.", [o.mark]))
        if o.sill + o.height > lv.height - lv.slab - 150 + 1e-6:
            out.append(issue("opening_height", "error", f"{o.mark} head at {o.sill + o.height:.0f} mm leaves under 150 mm below the slab soffit ({lv.height - lv.slab:.0f} mm).", [o.mark], "Reduce the height or sill."))
        for p in model.openings:
            if p is o or p.host != o.host or p.mark > o.mark:
                continue
            a0, a1 = wall_offset(w, o), wall_offset(w, o) + o.width
            b0, b1 = wall_offset(w, p), wall_offset(w, p) + p.width
            if min(a1, b1) - max(a0, b0) > -50:
                out.append(issue("openings_clash", "error", f"{o.mark} and {p.mark} overlap or leave under 50 mm on wall {w.id}.", [o.mark, p.mark]))
    # --- levels / stairs
    if not (2400 <= lv.height <= 4500):
        out.append(issue("level_height", "error", f"Floor height {lv.height:.0f} mm is outside 2400-4500 mm.", ["GF"]))
    for st in model.stairs:
        if st.flight and st.flight.riser_mm > 190:
            out.append(issue("stair_riser", "error", f"Stair riser {st.flight.riser_mm:.0f} mm exceeds 190 mm.", [st.id]))
        if st.flight and st.flight.tread_mm < 250:
            out.append(issue("stair_tread", "error", f"Stair tread {st.flight.tread_mm:.0f} mm is under 250 mm.", [st.id]))
    return out


def check_agreement(model: ProjectModel, metas: dict[str, dict]) -> list[dict]:
    """metas: view_id -> meta of the rendered views. Confirms plans, elevations and schedules agree with the model."""
    out = []
    truth = {o.mark: (o.type, round(o.width, 1), round(o.height, 1), round(o.sill, 1)) for o in model.openings if o.host}
    def tup(m): return (m["type"], round(m["width"], 1), round(m["height"], 1), round(m["sill"], 1))
    for vid, m in metas.items():
        vd = next((v for v in model.views if v.id == vid), None)
        if not vd:
            continue
        if vd.type == "plan":
            got = {x["mark"]: tup(x) for x in m["openings"]}
            if got != truth:
                out.append(issue("view_mismatch", "error", f"Plan {vid} disagrees with the model for openings: {sorted(set(got.items()) ^ set(truth.items()))[:3]}"))
        elif vd.type == "openings":
            got = {x["mark"]: tup(x) for x in m["rows"]}
            if got != truth:
                out.append(issue("schedule_mismatch", "error", "Door/window schedule disagrees with the model."))
        elif vd.type == "elevation":
            exp = {o.mark: truth[o.mark] for o in model.openings if o.host and _on_facade(model, o, vd.facing)}
            got = {x["mark"]: tup(x) for x in m["openings"]}
            if got != exp:
                out.append(issue("elevation_mismatch", "error", f"{vid} elevation disagrees with the model for openings."))
        elif vd.type == "rooms":
            exp = {s.key: round(room_metrics(model, s)["area_m2"], 3) for s in model.spaces}
            got = {r["key"]: r["area_m2"] for r in m["rows"]}
            if exp != got:
                out.append(issue("rooms_mismatch", "error", "Room schedule disagrees with the model."))
    return out


def _on_facade(model, o, facing):
    from .views import _facade
    return any(o.host == w.id for w in _facade(model, facing))
