"""Alternative layouts for the same brief, built by the same deterministic engine and compared on the same measures."""
from __future__ import annotations

from .edits import EditConflict, EditError, apply_edits
from .estimate import estimate
from .layout import ImpossibleLayout
from .model import Brief, ProjectModel, digest
from .review import review
from .validate import validate_model


def candidate_ops(brief: Brief, base: ProjectModel) -> list[tuple[str, str, list[dict]]]:
    """(label, trade-off, ops) for each idea worth trying on a template layout."""
    out = []
    if len(base.levels) == 1 and base.params.stair_position in ("front", "rear"):
        other = "rear" if base.params.stair_position == "front" else "front"
        out.append((f"Stair moved to the {other}",
                    "The stair sits beside the entry and frees the middle band." if other == "front" else
                    "The stair moves behind the living area, which opens up the front rooms.",
                    [dict(op="move_stair", position=other)]))
    if brief.kitchen_type in ("open", "closed"):
        other = "closed" if brief.kitchen_type == "open" else "open"
        out.append((f"{other.capitalize()} kitchen",
                    "Keeps cooking smells and noise in the kitchen." if other == "closed" else "Joins the kitchen to the dining space and makes the house feel larger.",
                    [dict(op="set_brief", fields=dict(kitchen_type=other))]))
    if len(base.levels) == 1 and base.params.stair_position in ("front", "rear") and brief.kitchen_type in ("open", "closed"):
        sp = "rear" if base.params.stair_position == "front" else "front"
        kt = "closed" if brief.kitchen_type == "open" else "open"
        out.append((f"{kt.capitalize()} kitchen with the stair at the {sp}", "Both changes together.",
                    [dict(op="move_stair", position=sp), dict(op="set_brief", fields=dict(kitchen_type=kt))]))
    return out


def _sig(m: ProjectModel) -> str:
    return digest([[s.model_dump() for s in m.spaces], [w.model_dump() for w in m.walls], [o.model_dump() for o in m.openings]])


def measures(brief: Brief, model: ProjectModel) -> dict:
    rv = review(model)
    est = estimate(model)
    carpet = sum(1 for _ in model.spaces)
    return dict(vastu=rv["vastu"]["score"], carpet_m2=est["carpet_m2"], built_up_m2=est["built_up_m2"], cost_per_sqft_inr=est["cost_per_sqft_inr"],
                to_check=rv["counts"]["warn"] + rv["counts"]["fail"], rooms=carpet)


def make_variants(brief: Brief, base: ProjectModel, use_assumptions: bool, limit: int = 3) -> list[dict]:
    """Return up to `limit` working alternatives that differ from the current layout and from each other."""
    if base.plan:
        raise EditError("plan_model", "This house was designed room by room, so automatic alternatives are not available.",
                        ["Ask in chat for another arrangement, for example 'show me another layout with the kitchen at the rear'"])
    seen = {_sig(base)}
    out = []
    for label, tradeoff, ops in candidate_ops(brief, base):
        try:
            nb, nm, _ = apply_edits(brief, base, ops, use_assumptions=use_assumptions)
        except (EditError, EditConflict, ImpossibleLayout):
            continue
        if [i for i in validate_model(nm) if i["severity"] == "error"]:
            continue
        sig = _sig(nm)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(dict(label=label, tradeoff=tradeoff, ops=ops, model=nm, brief=nb, metrics=measures(nb, nm)))
        if len(out) >= limit:
            break
    return out
