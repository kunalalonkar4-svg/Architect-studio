"""Apply structured edit operations to the design inputs and rebuild the model. The engine, not the AI,
owns all coordinates. Unsupported edits raise EditError with the specific limit."""
from __future__ import annotations

import copy

from .layout import ImpossibleLayout, build_model
from .model import ViewDef
from .model import Brief, ProjectModel, Setbacks

ALIASES = {
    "kitchen": "kitchen", "rasoi": "kitchen", "rasoighar": "kitchen",
    "bedroom 1": "bed1", "bedroom1": "bed1", "bed1": "bed1", "master": "bed1", "master bedroom": "bed1", "bed 1": "bed1",
    "bedroom 2": "bed2", "bedroom2": "bed2", "bed2": "bed2", "bed 2": "bed2",
    "living": "living", "living room": "living", "hall": "living", "drawing room": "living", "living / dining": "living",
    "dining": "dining", "dining / passage": "dining", "passage": "dining",
    "toilet": "toilet", "bath": "toilet", "bathroom": "toilet", "washroom": "toilet", "wc": "toilet",
    "stair": "stair", "staircase": "stair", "seedhi": "stair", "stairs": "stair",
    "parking": "parking", "car parking": "parking", "garage": "parking", "sit-out": "parking",
    "entry": "entry", "store": "store", "study": "bed2",
}


class EditError(Exception):
    def __init__(self, code: str, message: str, options: list[str] | None = None):
        super().__init__(message)
        self.code, self.message, self.options = code, message, options or []


class EditConflict(EditError):
    pass


def resolve_space(name: str) -> str:
    k = ALIASES.get(name.strip().lower())
    if not k:
        raise EditError("unknown_space", f"I don't recognise the room '{name}'.", ["kitchen", "bedroom 1", "bedroom 2", "living", "dining", "toilet", "staircase", "parking"])
    return k


def _local_dims(model: ProjectModel, key: str):
    """(along-frontage, depth) centreline dims of a space in the road-oriented local frame."""
    s = model.space(key)
    if model.plot["road_side"] in ("s", "n"):
        return s.w, s.h
    return s.h, s.w


def apply_edits(brief: Brief, model: ProjectModel, ops: list[dict], use_assumptions: bool = True,
                preserve: list[str] | None = None) -> tuple[Brief, ProjectModel, list[str]]:
    brief = brief.model_copy(deep=True)
    params = model.params.model_copy(deep=True)
    overrides = copy.deepcopy(model.opening_overrides)
    notes: list[str] = []
    preserve = [resolve_space(p) for p in (preserve or [])]
    BW = model.plot["bw"]
    from .plan import PlanSpec, build_model_from_plan
    plan_obj = PlanSpec.model_validate(model.plan) if model.plan else None
    for op in ops:
        kind = op.get("op")
        if kind == "replace_plan":
            plan_obj = PlanSpec.model_validate(op["plan"]); overrides = {}
            continue
        if plan_obj is not None and kind not in ("set_opening", "set_level_height", "set_brief"):
            raise EditError("plan_model", "This house was designed room by room, so that quick edit is not available. Describe the change and I will redesign the plan.",
                            ["Ask for the change in words (e.g. make bedroom 2 bigger, move the stair)"])
        if kind == "move_stair":
            pos = op["position"]
            if pos not in ("front", "rear"):
                raise EditError("bad_position", "Stair position must be 'front' (beside the entry) or 'rear' (middle/rear band).", ["front", "rear"])
            params.stair_position = pos; brief.stair_position = pos
        elif kind == "resize_space":
            key = resolve_space(op["space"])
            w, d = op.get("width_mm"), op.get("depth_mm")
            _resize(params, key, w, d, BW, preserve, notes)
        elif kind == "move_wall":
            a, b_ = resolve_space(op["between"][0]), resolve_space(op["between"][1])
            delta = float(op["delta_mm"])
            pair = frozenset((a, b_))
            if pair == frozenset(("bed1", "kitchen")):
                _resize(params, "bed1", params.bed1_w + delta, None, BW, preserve + ["kitchen"], notes)
            elif pair == frozenset(("kitchen", "bed2")):
                _resize(params, "kitchen", params.kitchen_w + delta, None, BW, preserve, notes)
            elif pair == frozenset(("living", "dining")):
                params.front_band += delta
            elif pair in (frozenset(("dining", "bed1")), frozenset(("dining", "bed2")), frozenset(("dining", "kitchen"))):
                params.rear_row -= delta
            else:
                raise EditError("unsupported_wall", f"Moving the wall between {a} and {b_} is not supported by the implemented engine.",
                                ["bed1|kitchen", "kitchen|bed2", "living|dining", "dining|bedrooms"])
        elif kind == "set_opening":
            o = model.opening_by_mark(op["mark"])
            if not o:
                raise EditError("unknown_opening", f"No door/window '{op['mark']}' exists.", [x.mark for x in model.openings])
            ov = overrides.setdefault(o.key, {})
            for f, k in (("width_mm", "width"), ("height_mm", "height"), ("sill_mm", "sill"), ("shift_mm", "shift")):
                if op.get(f) is not None:
                    ov[k] = float(op[f]) if k != "shift" else float(op[f]) + ov.get("shift", 0.0) * 0
            if op.get("hinge"):
                ov["hinge"] = op["hinge"]
        elif kind == "set_level_height":
            params.level_height = float(op["height_mm"])
        elif kind == "set_brief":
            f = op["fields"]
            for k, v in f.items():
                if k == "setbacks":
                    brief.setbacks = Setbacks(**{**brief.setbacks.model_dump(), **v})
                elif hasattr(brief, k):
                    setattr(brief, k, v)
            if "stair_position" in f:
                params.stair_position = f["stair_position"]
        else:
            raise EditError("unknown_op", f"Unsupported edit '{kind}'.")
    try:
        if plan_obj is not None:
            new = build_model_from_plan(brief, plan_obj, params, overrides, use_assumptions=use_assumptions, roof_approved=model.roof_approved)
        else:
            new = build_model(brief, params, overrides, use_assumptions=use_assumptions, roof_approved=model.roof_approved)
    except ImpossibleLayout:
        raise
    new.views, new.sheets = copy.deepcopy(model.views), copy.deepcopy(model.sheets)
    from .layout import refresh_walls
    for k in preserve:
        old_s, new_s = model.space(k), new.space(k)
        if old_s and new_s and (abs(old_s.w - new_s.w) > 1 or abs(old_s.h - new_s.h) > 1):
            raise EditConflict("preserve_conflict",
                               f"This change would resize {old_s.name} from {old_s.w:.0f} x {old_s.h:.0f} to {new_s.w:.0f} x {new_s.h:.0f} mm, which conflicts with 'keep {old_s.name} the same'.",
                               ["Allow the room to change", "Cancel this edit"])
    if new.stairs and new.sheets:
        _retarget_section(new)
    sync_level_views(new)
    return brief, new, notes


def plan_sheet_title(model: ProjectModel) -> str:
    return "Ground Floor Plan" if len(model.levels) == 1 else "Floor Plans"


def plan_view_defs(model: ProjectModel) -> list[ViewDef]:
    return [ViewDef(id="v-plan" if lv.id == "GF" else f"v-plan-{lv.id}", type="plan", level=lv.id) for lv in model.levels]


def sync_level_views(model: ProjectModel) -> None:
    """Keep per-floor plan views and the roof view in step with the number of levels."""
    ids = {l.id for l in model.levels}
    want = plan_view_defs(model)
    model.views = [v for v in model.views if not (v.type == "plan" and v.level not in ids)]
    have = {v.id for v in model.views}
    model.views += [v for v in want if v.id not in have]
    for sd in model.sheets:
        if sd.kind == "plan":
            sd.views = [v.id for v in want]
            sd.title = plan_sheet_title(model)
    for v in model.views:
        if v.type == "roof":
            v.level = model.levels[-1].id


def _retarget_section(model: ProjectModel):
    from .views import default_sections
    for v in model.views:
        if v.type == "section" and v.cut and v.cut.get("label") == "A":
            v.cut = default_sections(model)[0]


def _resize(params, key, w, d, BW, preserve, notes):
    if key == "kitchen":
        if w is not None:
            params.kitchen_w = float(w); notes.append("Bedroom 2 absorbs the change in kitchen width.")
        if d is not None:
            params.rear_row = float(d); notes.append("Rear-row rooms (bedroom 1, kitchen, bedroom 2) share one depth; all three change; the dining passage absorbs it.")
    elif key == "bed1":
        if w is not None:
            keep_k = params.kitchen_w
            params.bed1_w = float(w); params.kitchen_w = keep_k
            notes.append("Bedroom 2 absorbs the change in bedroom 1 width; kitchen size is kept.")
        if d is not None:
            params.rear_row = float(d)
    elif key == "bed2":
        if w is not None:
            if "kitchen" in preserve:
                raise EditConflict("preserve_conflict", "Bedroom 2 width can only change by resizing the kitchen, but the kitchen must stay the same.", ["Allow the kitchen to change", "Change bedroom 1 instead", "Cancel"])
            params.kitchen_w = BW - params.bed1_w - float(w); notes.append("The kitchen absorbs the change in bedroom 2 width.")
        if d is not None:
            params.rear_row = float(d)
    elif key == "living":
        if d is not None:
            params.front_band = float(d)
        if w is not None:
            raise EditError("unsupported_resize", "Living width is derived from plot width less parking and the entry column; change parking width or the entry column instead.", ["Change parking width", "Change the plot / open-space inputs"])
    elif key == "parking":
        if w is not None:
            params.parking_w = float(w)
        if d is not None:
            params.front_band = float(d)
    elif key == "stair":
        if w is not None:
            params.stair_w = float(w)
        if d is not None:
            raise EditError("unsupported_resize", "Stair depth follows the band it sits in; change the band depth instead.", [])
    else:
        raise EditError("unsupported_resize", f"Resizing '{key}' directly is not supported by the implemented engine.", ["kitchen", "bedroom 1", "bedroom 2", "living (depth)", "parking"])


def diff_models(old: ProjectModel | None, new: ProjectModel) -> list[dict]:
    out = []
    if old is None or not old.spaces:
        return [dict(kind="new", text="New layout generated.")]
    f = lambda v: f"{v:.0f}"
    for s in new.spaces:
        o = old.space(s.key)
        if not o:
            out.append(dict(kind="space_added", text=f"{s.name} added ({f(s.w)} x {f(s.h)} mm)."))
            continue
        moved = abs(o.x - s.x) > 1 or abs(o.y - s.y) > 1
        resized = abs(o.w - s.w) > 1 or abs(o.h - s.h) > 1
        if resized and not moved:
            out.append(dict(kind="space_resized", key=s.key, text=f"{s.name}: {f(o.w)} x {f(o.h)} → {f(s.w)} x {f(s.h)} mm (centreline sizes)."))
        elif resized and moved:
            out.append(dict(kind="space_changed", key=s.key, text=f"{s.name}: moved and resized {f(o.w)} x {f(o.h)} → {f(s.w)} x {f(s.h)} mm."))
        elif moved:
            out.append(dict(kind="space_moved", key=s.key, text=f"{s.name}: moved by ({f(s.x - o.x)}, {f(s.y - o.y)}) mm; size unchanged {f(s.w)} x {f(s.h)} mm."))
    for o in old.spaces:
        if not new.space(o.key):
            out.append(dict(kind="space_removed", text=f"{o.name} removed."))
    for n in new.openings:
        o = old.opening_by_mark(n.key)
        o = next((x for x in old.openings if x.key == n.key), None)
        if not o:
            out.append(dict(kind="opening_added", text=f"{n.mark} ({n.type}) added: {f(n.width)} x {f(n.height)} mm."))
            continue
        ch = []
        if abs(o.width - n.width) > .5: ch.append(f"width {f(o.width)} → {f(n.width)}")
        if abs(o.height - n.height) > .5: ch.append(f"height {f(o.height)} → {f(n.height)}")
        if abs(o.sill - n.sill) > .5: ch.append(f"sill {f(o.sill)} → {f(n.sill)}")
        if abs(o.cx - n.cx) > 1 or abs(o.cy - n.cy) > 1: ch.append("position changed")
        if o.mark != n.mark: ch.append(f"mark {o.mark} → {n.mark}")
        if ch:
            out.append(dict(kind="opening_changed", key=n.key, text=f"{n.mark}: " + ", ".join(ch) + " (mm)."))
    for o in old.openings:
        if not any(x.key == o.key for x in new.openings):
            out.append(dict(kind="opening_removed", text=f"{o.mark} ({o.type}) removed."))
    if old.stairs and new.stairs:
        a, b = old.stairs[0].flight, new.stairs[0].flight
        if a and b and (a.risers != b.risers or abs(a.riser_mm - b.riser_mm) > .1):
            out.append(dict(kind="stair", text=f"Stair: {a.risers} risers @ {a.riser_mm} → {b.risers} @ {b.riser_mm} mm."))
    if old.levels[0].height != new.levels[0].height:
        out.append(dict(kind="level", text=f"Floor height {f(old.levels[0].height)} → {f(new.levels[0].height)} mm."))
    return out
