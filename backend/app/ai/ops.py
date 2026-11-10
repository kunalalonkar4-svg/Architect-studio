"""Execution of allow-listed operations: validate -> authorise -> run. The AI proposes; the engine computes."""
from __future__ import annotations

import json

from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..engine.edits import EditConflict, EditError, apply_edits, diff_models
from ..engine.layout import ImpossibleLayout, build_model
from ..engine.model import Assumption, Brief, ProjectModel, Setbacks, SIDE_FROM_NAME
from ..engine.sheets import SheetOverflow, TABLE_KINDS, PAPERS
from ..engine.validate import validate_model
from ..engine.views import rooms_schedule
from ..models import Job, Project, Proposal, Revision, User
from ..services import (ServiceError, affected_sheets, autofit, create_revision, enqueue_export, ensure_sheet, evaluate_edit,
                        new_proposal, precheck_export, sheet_meta, sheet_meta_for)
from ..units import AmbiguousUnit, to_mm
from .tools import MODELS

GEOMETRIC = {"plot_frontage", "plot_depth", "road_side", "setback_front", "setback_rear", "setback_left", "setback_right",
             "bedrooms", "floors", "kitchen_type", "parking"}


@dataclass
class Ctx:
    db: Session
    project: Project
    user: User


@dataclass
class Outcome:
    result: dict
    events: list = field(default_factory=list)
    is_error: bool = False
    images: list = field(default_factory=list)      # PNG bytes shown to the model (e.g. a preview of its own drawing)


def err(code, message, next_actions=None, detail=None) -> Outcome:
    d = dict(code=code, message=message, next_actions=next_actions or [], detail=detail or {})
    return Outcome(dict(ok=False, error=d), [dict(type="error", **d)], True)


def mm(l):
    if l is None:
        return None
    if l.value == 0:
        return 0.0
    return to_mm(l.value, l.unit)


def current_revision(ctx: Ctx):
    return ctx.db.get(Revision, ctx.project.current_revision_id) if ctx.project.current_revision_id else None


def execute_tool(ctx: Ctx, name: str, raw: dict) -> Outcome:
    if name not in MODELS:                       # allow-list
        return err("unknown_operation", f"Operation '{name}' is not allowed.")
    if ctx.project.status == "archived" and name not in ("explain_validation", "ask_clarification", "get_quantities"):
        return err("project_archived", "This project is archived and read-only.", ["Unarchive the project to continue"])
    try:
        args = MODELS[name].model_validate(raw)
    except ValidationError as e:
        return err("invalid_arguments", "The operation arguments were invalid: " + "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:4]))
    try:
        return globals()[f"op_{name}"](ctx, args)
    except AmbiguousUnit as e:
        return err("ambiguous_unit", f"{e} Please state the unit (feet, metres or mm).", ["Reply with the dimension and its unit, e.g. '30 ft'"])
    except ServiceError as e:
        return Outcome(dict(ok=False, error=e.as_dict()), [dict(type="error", **e.as_dict())], True)
    except SheetOverflow as e:
        return err("sheet_overflow", str(e), [s["text"] for s in e.suggestions], dict(sheet=e.sheet_number, suggestions=e.suggestions))
    except (EditError, EditConflict) as e:
        return err(e.code, e.message, e.options)
    except ImpossibleLayout as e:
        return err("impossible_layout", "That layout cannot be built: " + "; ".join(e.reasons), e.suggestions, dict(reasons=e.reasons))


# ---------------------------------------------------------------- brief
def op_update_brief(ctx: Ctx, a) -> Outcome:
    brief = Brief.model_validate(ctx.project.brief or {})
    rev = current_revision(ctx)
    amb, geo_changes = [], {}
    def L(field_, v):
        try:
            return mm(v)
        except AmbiguousUnit:
            amb.append(dict(field=field_, value=v.value)); return None
    fr, dp = L("plot_frontage", a.plot_frontage), L("plot_depth", a.plot_depth)
    sbs = {k: L(f"setback_{k}", getattr(a, f"setback_{k}")) for k in ("front", "rear", "left", "right")}
    if rev:
        # a design already exists: geometry changes become a reviewed proposal, not a silent overwrite
        fields = {}
        if a.bedrooms is not None: fields["bedrooms"] = a.bedrooms
        if a.floors is not None: fields["levels_now"] = a.floors
        if a.kitchen_type: fields["kitchen_type"] = a.kitchen_type
        if a.parking is not None: fields["parking"] = a.parking
        sb = {k: v for k, v in sbs.items() if v is not None}
        if sb: fields["setbacks"] = sb
        if fr: fields["plot_frontage_mm"] = fr
        if dp: fields["plot_depth_mm"] = dp
        if a.road_side: fields["road_side"] = SIDE_FROM_NAME[a.road_side]
        out_events = []
        if fields and not amb:
            o = _make_edit_proposal(ctx, rev, [dict(op="set_brief", fields=fields)], [], "Change the project inputs")
            out_events += o.events
            if o.is_error:
                return o
        _apply_soft_fields(brief, a)
        ctx.project.brief = brief.model_dump()
        ev = dict(type="brief", brief=brief.model_dump(), missing=brief.missing())
        if amb:
            return Outcome(dict(ok=False, ambiguous_dimensions=amb, brief=brief.model_dump()), [ev] + out_events + [dict(type="clarification", questions=_amb_questions(amb))], True)
        return Outcome(dict(ok=True, brief=brief.model_dump(), note="Geometry changes were turned into a proposal awaiting user confirmation."), [ev] + out_events)
    if fr: brief.plot_frontage_mm = fr
    if dp: brief.plot_depth_mm = dp
    if a.dims_orientation_assumed:
        brief.dims_assumed_orientation = True
        brief.assumptions = [x for x in brief.assumptions if x.id != "dims_orientation"] + [
            Assumption(id="dims_orientation", text="The first plot dimension is taken along the road frontage and the second as depth. Confirm.", kind="assumed")]
    if a.road_side: brief.road_side = SIDE_FROM_NAME[a.road_side]
    for k, v in sbs.items():
        if v is not None:
            setattr(brief.setbacks, k, v)
    _apply_soft_fields(brief, a)
    if a.bedrooms is not None: brief.bedrooms = a.bedrooms
    if a.floors is not None: brief.levels_now = a.floors
    if a.kitchen_type: brief.kitchen_type = a.kitchen_type
    if a.parking is not None: brief.parking = a.parking
    if a.stair is not None: brief.stair = a.stair
    if a.stair_position: brief.stair_position = a.stair_position
    ctx.project.brief = brief.model_dump()
    ev = [dict(type="brief", brief=brief.model_dump(), missing=brief.missing())]
    if amb:
        ev.append(dict(type="clarification", questions=_amb_questions(amb)))
    res = dict(ok=True, brief=brief.model_dump(), missing=brief.missing(), ambiguous_dimensions=amb,
               note="Dimensions without a unit were NOT stored; ask the user for the unit." if amb else "")
    if brief.plot_frontage_mm and brief.plot_depth_mm and brief.road_side:
        try:
            from ..engine.plan import envelope
            bw, bd, sb, src, _ = envelope(brief, True)
            res["envelope_mm"] = dict(width_x=bw, depth_y=bd, setbacks_used=sb, assumed_setbacks=[k for k, v in src.items() if v == "assumed"],
                                      note="Design rooms inside x 0..width_x, y 0..depth_y (y=0 is the road side), wall centrelines, multiples of 25 mm.")
        except Exception:
            pass
    return Outcome(res, ev)


def _apply_soft_fields(brief: Brief, a):
    if a.future_levels is not None: brief.future_levels = a.future_levels
    if a.requested_views is not None: brief.requested_views = list(a.requested_views)
    if a.constraints: brief.constraints = list(dict.fromkeys(brief.constraints + a.constraints))
    if a.notes: brief.notes = a.notes


def _amb_questions(amb):
    return [dict(id=f"unit_{x['field']}", question=f"What unit is {x['value']:g} for {x['field'].replace('_', ' ')}: feet, metres or mm?", why="Units must be certain before dimensions are fixed.", options=["feet", "metres", "mm"]) for x in amb]


def op_ask_clarification(ctx: Ctx, a) -> Outcome:
    qs = [q.model_dump() for q in a.questions][:4]
    return Outcome(dict(ok=True, waiting_for_user=True), [dict(type="clarification", questions=qs)])


# ---------------------------------------------------------------- layout
def prepare_sheets(ctx: Ctx, model: ProjectModel, brief: Brief, specs: list[dict]):
    for sp in specs:
        sd = ensure_sheet(model, sp["kind"], paper=sp.get("paper"), scale=sp.get("scale"), facings=sp.get("facings"))
        meta = sheet_meta(ctx.db, ctx.project, ctx.user, model, brief, {}, 0, ctx.project.created_at)
        meta["sheet_index"] = [dict(number=s.number, title=s.title, scale="", paper=s.paper, rev="0") for s in model.sheets]
        autofit(model, sd, meta, explicit_paper=bool(sp.get("paper")), explicit_scale=bool(sp.get("scale")))


def _rev_event(rev: Revision) -> dict:
    return dict(type="revision", revision_id=rev.id, number=rev.number, summary=rev.summary, render_status=rev.render_status)


def op_generate_layout(ctx: Ctx, a) -> Outcome:
    if current_revision(ctx):
        return err("layout_exists", "A layout already exists. Describe the change you want and I will propose an edit.", ["Ask for a specific change, e.g. move the staircase"])
    brief = Brief.model_validate(ctx.project.brief or {})
    if a.stair_position:
        brief.stair_position = a.stair_position
    missing = [m for m in brief.missing() if m["id"] != "setbacks"]
    sb_missing = any(v is None for v in brief.setbacks.model_dump().values())
    if missing:
        return err("missing_inputs", "Essential inputs are missing: " + ", ".join(m["question"] for m in missing), [m["question"] for m in missing], dict(missing=missing))
    if sb_missing and not a.use_assumptions:
        return err("missing_setbacks", "Required open spaces / setbacks are not provided. Provide them or choose to proceed with clearly labelled concept assumptions.",
                   ["Provide front / rear / left / right open space", "Proceed with concept assumptions"], dict(assumption_defaults=dict(front=3000, rear=1500, left=0, right=0)))
    model = build_model(brief, use_assumptions=a.use_assumptions)
    ctx.project.use_assumptions = bool(a.use_assumptions and sb_missing) or ctx.project.use_assumptions
    prepare_sheets(ctx, model, brief, [dict(kind=k) for k in (brief.requested_views or ["plan"])])
    rev = create_revision(ctx.db, ctx.project, ctx.user, brief, model, "Initial concept layout")
    rooms = [dict(name=r["name"], clear_w=r["clear_w"], clear_d=r["clear_d"], area_m2=r["area_m2"]) for r in rooms_schedule(model, model.views[0], 1, {}).meta["rows"]] if False else _room_dims(model)
    return Outcome(dict(ok=True, revision=rev.number, rooms=rooms, stair=model.stairs[0].flight.model_dump() if model.stairs else None,
                        assumptions=[x.text for x in model.assumptions if x.kind == "assumed"], validation=[i["message"] for i in rev.validation if i["severity"] != "info"][:6],
                        render="queued; the app will confirm when the drawing exists"),
                   [_rev_event(rev)])


def _plan_hash(a) -> str:
    import hashlib
    d = dict(rooms=sorted([r.model_dump() for r in a.rooms], key=lambda r: r["key"]),
             conns=sorted([c.model_dump() for c in a.connections], key=lambda c: (c["a"], c["b"], c["type"])), entry=a.entry_room)
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]


def _preview_png(ctx: Ctx, model: ProjectModel, brief: Brief) -> bytes:
    from ..engine.render import render_pdf, render_png
    from ..engine.sheets import compose_sheet
    sd = ensure_sheet(model, "plan")
    meta = sheet_meta(ctx.db, ctx.project, ctx.user, model, brief, {}, 0, ctx.project.created_at)
    meta["sheet_index"] = [dict(number=s.number, title=s.title, scale="", paper=s.paper, rev="0") for s in model.sheets]
    autofit(model, sd, meta)
    return render_png(render_pdf([compose_sheet(model, sd, meta)]), 0, dpi=80)


REVIEW_CHECKLIST = [
    "Walk in from the road: does the approach, entry and public-to-private sequence feel right?",
    "Is every bedroom comfortably usable (about 9 m2 or more, not a long thin strip) with a window and a door that does not clash with furniture?",
    "Is circulation efficient (little wasted passage) and is the kitchen next to dining with an outside wall?",
    "Are toilets reachable without crossing living or bedrooms, with a vent, and stacked above each other on a duplex?",
    "Is the stair well placed, and do doors, walls and labels read clearly in the drawing?",
    "Does the plan respect the user's stated preferences (Vastu, parking, bedroom count)?",
]


def op_design_floor_plan(ctx: Ctx, a) -> Outcome:
    from ..engine.plan import PlanConn, PlanRoom, PlanSpec, build_model_from_plan
    rev = current_revision(ctx)
    brief = Brief.model_validate((rev.brief if rev else ctx.project.brief) or {})
    missing = [m for m in brief.missing() if m["id"] not in ("setbacks",)]
    if missing:
        return err("missing_inputs", "Essential inputs are missing: " + ", ".join(m["question"] for m in missing), [m["question"] for m in missing], dict(missing=missing))
    sb_missing = any(v is None for v in brief.setbacks.model_dump().values())
    use_asm = bool(a.use_assumptions) or ctx.project.use_assumptions
    if sb_missing and not use_asm:
        return err("missing_setbacks", "Required open spaces / setbacks are not provided. Provide them or choose to proceed with clearly labelled concept assumptions.",
                   ["Provide front / rear / left / right open space", "Proceed with concept assumptions"], dict(assumption_defaults=dict(front=3000, rear=1500, left=0, right=0)))
    plan = PlanSpec(rooms=[PlanRoom(**r.model_dump()) for r in a.rooms], connections=[PlanConn(**c.model_dump()) for c in a.connections],
                    entry_room=a.entry_room, rationale=a.summary)
    h = _plan_hash(a)
    seen = ctx.__dict__.setdefault("previewed", set())
    if a.final and h not in seen:
        return err("review_first", "Look at this exact plan before finalising: call design_floor_plan with final=false, review the returned drawing against the checklist, fix anything wrong, then call with final=true.",
                   ["Preview the plan first (final=false)"])
    model = build_model_from_plan(brief, plan, use_assumptions=use_asm)
    errors = [i for i in validate_model(model) if i["severity"] == "error"]
    if errors:
        return err("plan_has_errors", "The plan was built but has errors: " + "; ".join(e["message"] for e in errors[:6]),
                   [e["fix"] or e["message"] for e in errors[:6]], dict(issues=errors))
    if not a.final:
        from ..engine.layout import room_metrics
        rooms, flagged = [], []
        for s in model.spaces:
            m = room_metrics(model, s)
            rooms.append(dict(floor=s.level, key=s.key, name=s.name, clear_mm=f"{m['clear_w']:.0f} x {m['clear_d']:.0f}", area_m2=round(m["area_m2"], 2)))
            if min(m["clear_w"], m["clear_d"]) > 0 and max(m["clear_w"], m["clear_d"]) / min(m["clear_w"], m["clear_d"]) > 2.0 and s.kind in ("bedroom", "living", "kitchen", "study"):
                flagged.append(f"{s.name} is long and thin ({m['clear_w']:.0f} x {m['clear_d']:.0f} mm)")
        total = sum(r["area_m2"] for r in rooms) or 1
        circ = sum(r["area_m2"] for r, s in zip(rooms, model.spaces) if s.kind in ("passage", "entry", "stair")) / total
        seen.add(h)
        try:
            png = _preview_png(ctx, model, brief)
        except Exception as e:      # the preview must never block the design
            png = b""
            flagged.append(f"(drawing preview unavailable: {type(e).__name__})")
        warnings = [i["message"] for i in validate_model(model) if i["severity"] == "warning"]
        return Outcome(dict(ok=True, preview=True, rooms=rooms, circulation_share=f"{circ * 100:.0f}% of floor area (passage + entry + stair)", warnings=warnings, shape_flags=flagged,
                            review_checklist=REVIEW_CHECKLIST,
                            note="NOT saved yet. Study the attached drawing like a senior architect. If anything is wrong, fix the plan and call design_floor_plan again with final=false. "
                                 "When you are satisfied, call it once more with the identical plan and final=true to save it."),
                       images=[png] if png else [])
    if rev:
        return _make_edit_proposal(ctx, rev, [dict(op="replace_plan", plan=plan.model_dump())], [], a.summary)
    if sb_missing and a.use_assumptions:
        ctx.project.use_assumptions = True
    prepare_sheets(ctx, model, brief, [dict(kind=k) for k in (brief.requested_views or ["plan"])])
    new = create_revision(ctx.db, ctx.project, ctx.user, brief, model, "Initial concept layout (designed room by room)")
    return Outcome(dict(ok=True, revision=new.number, rooms=_room_dims(model), assumptions=[x.text for x in model.assumptions if x.kind == "assumed"],
                        validation=[i["message"] for i in new.validation if i["severity"] != "info"][:8],
                        render="queued; the app will confirm when the drawing exists"), [_rev_event(new)])


def _room_dims(model: ProjectModel):
    from ..engine.layout import room_metrics
    out = []
    for s in model.spaces:
        m = room_metrics(model, s)
        out.append(dict(key=s.key, name=s.name, clear_w=round(m["clear_w"]), clear_d=round(m["clear_d"]), area_m2=round(m["area_m2"], 2)))
    return out


def op_propose_options(ctx: Ctx, a) -> Outcome:
    rev = current_revision(ctx)
    brief = Brief.model_validate(ctx.project.brief or {})
    if rev:
        brief = Brief.model_validate(rev.brief); base = ProjectModel.model_validate(rev.model)
    else:
        missing = [m for m in brief.missing() if m["id"] != "setbacks"]
        if missing:
            return err("missing_inputs", "Essential inputs are missing: " + ", ".join(m["question"] for m in missing), [m["question"] for m in missing])
        sb_missing = any(v is None for v in brief.setbacks.model_dump().values())
        if sb_missing and not a.use_assumptions:
            return err("missing_setbacks", "Open spaces are not provided; choose concept assumptions to compare options.", ["Provide open spaces", "Proceed with concept assumptions"])
        base = build_model(brief, use_assumptions=a.use_assumptions)
        ctx.project.use_assumptions = a.use_assumptions
    opts = []
    for o in a.options[:3]:
        ops = [dict(op="move_stair", position=o.stair_position)]
        nb, nm, notes = apply_edits(brief, base, ops, use_assumptions=ctx.project.use_assumptions or a.use_assumptions)
        opts.append(dict(label=o.label, tradeoff=o.tradeoff or "", ops=ops, rooms=_room_dims(nm), stair=nm.stairs[0].flight.model_dump(),
                         changes=diff_models(base, nm) if rev else [], issues=[i for i in validate_model(nm) if i["severity"] != "info"]))
    if rev:
        base_id = rev.id
    else:
        base_id = ""
    pr = new_proposal(ctx.db, ctx.project, rev or _NoRev(), "options", [], [], "Choose a layout option to continue", [], [], options=opts)
    ctx.project.brief = brief.model_dump()
    return Outcome(dict(ok=True, proposal_id=pr.id, options=[dict(label=o["label"], rooms=o["rooms"]) for o in opts], note="The user must choose an option in the app."),
                   [dict(type="options", proposal_id=pr.id)])


class _NoRev:
    id = ""


# ---------------------------------------------------------------- edits
def _edit_to_ops(items) -> list[dict]:
    ops = []
    for e in items:
        if e.op == "move_stair":
            ops.append(dict(op="move_stair", position=e.position or "rear"))
        elif e.op == "resize_space":
            ops.append(dict(op="resize_space", space=e.space or "", width_mm=mm(e.width), depth_mm=mm(e.depth)))
        elif e.op == "move_wall":
            ops.append(dict(op="move_wall", between=e.between or [], delta_mm=mm(e.delta)))
        elif e.op == "set_opening":
            ops.append(dict(op="set_opening", mark=e.mark or "", width_mm=mm(e.width), height_mm=mm(e.height), sill_mm=mm(e.sill), shift_mm=mm(e.shift), hinge=e.hinge))
        elif e.op == "set_level_height":
            ops.append(dict(op="set_level_height", height_mm=mm(e.height)))
        elif e.op == "set_brief":
            f = {}
            if e.bedrooms is not None: f["bedrooms"] = e.bedrooms
            if e.floors is not None: f["levels_now"] = e.floors
            if e.kitchen_type: f["kitchen_type"] = e.kitchen_type
            if e.parking is not None: f["parking"] = e.parking
            ops.append(dict(op="set_brief", fields=f))
    return ops


def _make_edit_proposal(ctx: Ctx, rev: Revision, ops: list[dict], preserve: list[str], summary: str) -> Outcome:
    try:
        nb, nm, changes, affected, issues, notes = evaluate_edit(ctx.db, ctx.project, ctx.user, rev, ops, preserve)
    except (EditError, EditConflict) as e:
        return err(e.code, e.message, e.options)
    except ImpossibleLayout as e:
        return err("impossible_layout", "That change cannot be built: " + "; ".join(e.reasons), e.suggestions, dict(reasons=e.reasons))
    if not changes:
        return Outcome(dict(ok=True, note="No change: the model already matches that request."), [dict(type="info", message="Nothing to change: the drawing already matches.")])
    pr = new_proposal(ctx.db, ctx.project, rev, "edit", ops, preserve, summary, changes + [dict(kind="note", text=n) for n in notes], affected, issues=issues)
    blocking = [i for i in issues if i["severity"] == "error"]
    return Outcome(dict(ok=True, proposal_id=pr.id, changes=[c["text"] for c in changes], affected_sheets=[s["number"] for s in affected],
                        blocking_issues=[i["message"] for i in blocking], note="Awaiting the user's confirmation; nothing is saved yet."),
                   [dict(type="proposal", proposal_id=pr.id)])


def op_propose_edit(ctx: Ctx, a) -> Outcome:
    rev = current_revision(ctx)
    if not rev:
        return err("no_model_yet", "There is no drawing to edit yet.", ["Generate the first layout from the brief"])
    ops = _edit_to_ops(a.edits)
    return _make_edit_proposal(ctx, rev, ops, a.preserve or [], a.summary)


def op_generate_views(ctx: Ctx, a) -> Outcome:
    rev = current_revision(ctx)
    if not rev:
        return err("no_model_yet", "Generate the first layout before adding views.", ["Generate the first layout"])
    brief = Brief.model_validate(rev.brief); model = ProjectModel.model_validate(rev.model)
    specs = [dict(kind=v.kind, paper=v.paper, scale=v.scale, facings=v.facings) for v in a.views]
    prepare_sheets(ctx, model, brief, specs)
    names = ", ".join(sorted({v.kind for v in a.views}))
    new = create_revision(ctx.db, ctx.project, ctx.user, brief, model, f"Views added/updated: {names}")
    return Outcome(dict(ok=True, revision=new.number, sheets=[f"{s.number} {s.title} ({s.paper}, " + (f"1:{s.scale}" if s.scale else "NTS") + ")" for s in model.sheets]),
                   [_rev_event(new)])


def op_request_export(ctx: Ctx, a) -> Outcome:
    rev = current_revision(ctx)
    if not rev:
        return err("no_model_yet", "There is nothing to export yet.", ["Generate the first layout"])
    model = ProjectModel.model_validate(rev.model)
    if a.sheets == ["all"] or not a.sheets:
        ids = [s.id for s in model.sheets]
    else:
        want = [x.lower() for x in a.sheets]
        ids = [s.id for s in model.sheets if s.number.lower() in want or s.id.lower() in want or s.kind in want]
        if not ids:
            return err("unknown_sheet", f"No matching sheets. Available: {', '.join(s.number for s in model.sheets)}.", [s.number for s in model.sheets])
    params = dict(format=a.format, sheet_ids=ids, paper=a.paper, scale=a.scale, orientation=a.orientation)
    brief = Brief.model_validate(rev.brief)
    base = sheet_meta(ctx.db, ctx.project, ctx.user, model, brief, rev.sheet_revs, rev.number, rev.created_at)
    precheck_export(rev, lambda sd: sheet_meta_for(sd, base, rev.sheet_revs), params)
    job = enqueue_export(ctx.db, ctx.project, rev, params)
    return Outcome(dict(ok=True, job_id=job.id, state=job.state, note="Queued. The app confirms when the file exists and passed validation; do not say it is ready."),
                   [dict(type="export", job_id=job.id, format=a.format)])


def op_get_quantities(ctx: Ctx, a) -> Outcome:
    from ..engine.estimate import estimate
    from ..engine.structural import prelim
    rev = current_revision(ctx)
    if not rev:
        return err("no_model_yet", "There is no drawing yet, so quantities cannot be computed.")
    model = ProjectModel.model_validate(rev.model)
    return Outcome(dict(ok=True, revision=rev.number, estimate=estimate(model), structural_preliminary=prelim(model)), [dict(type="info", message="Quantities and preliminary structural sizes are in the Estimate tab.")])


def op_explain_validation(ctx: Ctx, a) -> Outcome:
    rev = current_revision(ctx)
    if not rev:
        return err("no_model_yet", "There is no drawing to validate yet.")
    issues = rev.validation or []
    return Outcome(dict(ok=True, issues=[dict(severity=i["severity"], message=i["message"], fix=i.get("fix", "")) for i in issues]),
                   [dict(type="validation", issues=issues)])
