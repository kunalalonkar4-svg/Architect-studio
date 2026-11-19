"""Site pack for the owner to take to a contractor, engineer or architect: a build-stage checklist, specification notes taken from what the
drawings and estimate actually say, and a list of questions to settle first. It is a checklist, not a contract document, a specification
approved by anyone, or a structural design."""
from __future__ import annotations

from .estimate import estimate
from .model import Brief, ProjectModel
from .review import column_grid
from .structural import columns, prelim

NOT_A_CONTRACT = ("Owner's checklist generated from the concept drawings. It is not a contract document, a bill of quantities for tender, or a structural "
                  "design. A licensed architect or engineer must confirm every item marked 'to confirm' before work starts.")


def _row(text: str, source: str = "general") -> dict:
    return dict(text=text, source=source)       # source: drawings | estimate | assumed | general | to_confirm


def site_pack(model: ProjectModel, brief: Brief) -> dict:
    est = estimate(model)
    pre = prelim(model)
    sz = pre["sizes"]
    cols = columns(model)
    grid = column_grid(model)
    doors = [o for o in model.openings if o.type == "door"]
    wins = [o for o in model.openings if o.type == "window"]
    wet = [s for s in model.spaces if s.kind in ("toilet", "bath", "wc") or "toilet" in s.name.lower() or "bath" in s.name.lower()]
    nlev = len(model.levels)
    ext_t = model.params.ext_t; int_t = model.params.int_t
    user_cols = [c for c in cols if c["user"]]
    assumed = [a.text for a in model.assumptions]

    stages = [
        dict(name="1. Before you start", items=[
            _row("Soil investigation report in hand (bearing capacity and water table).", "to_confirm"),
            _row("Local building rules checked: open space, coverage, height, approvals. Drafta only checks values you enter.", "to_confirm"),
            _row("Drawings signed off by your architect and engineer, with the structural design issued by the engineer.", "to_confirm"),
            _row("Written quotation with item rates, payment stages and finish dates from at least two contractors."),
            _row("Boundary pillars and plot corners checked against the sale deed or survey before marking the house.")]),
        dict(name="2. Setting out and excavation", items=[
            _row(f"Mark the house outline from the site plan. Outer size about {(model.outer_bounds()[2]-model.outer_bounds()[0])/1000:.2f} x {(model.outer_bounds()[3]-model.outer_bounds()[1])/1000:.2f} m.", "drawings"),
            _row("Check diagonals of the marked rectangle before digging; mark column centres from the structural drawing.", "general"),
            _row(f"{len(cols)} column positions on the concept layout ({len(user_cols)} placed or moved by you). The engineer's drawing decides the final positions.", "drawings"),
            _row(f"Footings: concept size {sz['footing']:.0f} x {sz['footing']:.0f} x {sz['footing_depth']:.0f} mm for an assumed soil capacity of 150 kN/m2. Depth and size depend on the soil test.", "to_confirm")]),
        dict(name="3. Foundation and plinth", items=[
            _row("Level PCC bed under each footing before steel is placed."),
            _row("Check bar sizes, spacing and cover against the engineer's drawing before concreting. Do not concrete without that check.", "to_confirm"),
            _row("Anti-termite treatment where the soil needs it; damp-proof course at plinth level."),
            _row(f"Plinth level about {model.levels[0].plinth:.0f} mm above ground level in the model.", "drawings")]),
        dict(name="4. Structure", items=[
            _row(f"Columns about {sz['col_b']:.0f} x {sz['col_d']:.0f} mm (concept size, rule of thumb for {nlev} floor{'s' if nlev > 1 else ''}).", "to_confirm"),
            _row(f"Roof beams about {sz['beam_b']:.0f} x {sz['beam_d']:.0f} mm and slab about {sz['slab']:.0f} mm (concept).", "to_confirm"),
            *([_row(f"{len([i for i in grid['items'] if i['status'] == 'warn'])} long column span(s) flagged. Ask the engineer how they will be handled.", "to_confirm")] if any(i["status"] == "warn" for i in grid["items"]) else []),
            _row("Cube tests for concrete and a record of every pour (date, grade, quantity)."),
            _row("Curing for at least 7 days; keep props until the engineer allows them to be removed.")]),
        dict(name="5. Walls, doors and windows", items=[
            _row(f"External walls {ext_t:.0f} mm and internal walls {int_t:.0f} mm thick in the drawings.", "drawings"),
            _row(f"{len(doors)} doors and {len(wins)} windows in the schedule. Check sizes and sill heights against the drawing.", "drawings"),
            _row("Lintels over every opening; sunshade or drip detail over windows.")]),
        dict(name="6. Services and waterproofing", items=[
            _row(f"{len(wet)} wet area(s). Waterproofing test (flood for 48 hours) before tiling.", "drawings"),
            _row("Electrical and plumbing follow the concept sheet only as a starting point. The electrician and plumber give their own layout.", "to_confirm"),
            _row("Pressure-test water lines and check drain slopes before closing walls.")]),
        dict(name="7. Finishes and handover", items=[
            _row("Plaster, flooring, paint and fittings as agreed in the written specification."),
            _row("Snag list walk-through with photos before the last payment."),
            _row("Collect warranties, test reports and as-built drawings at handover.")]),
    ]

    spec = [
        _row(f"Walling: {dict(brick='brick', aac='AAC blocks', flyash='fly-ash bricks').get(est['options']['selected'].get('masonry'), 'brick')} in the estimate, "
             f"external {ext_t:.0f} mm, internal {int_t:.0f} mm.", "estimate"),
        _row(f"Concrete grade used in the estimate: {est['options']['selected'].get('concrete', 'M20')}. Steel Fe500 assumed. The engineer sets the real grades.", "assumed"),
        _row(f"Floor-to-floor height {model.levels[0].height:.0f} mm; slab {model.levels[0].slab:.0f} mm in the model.", "drawings"),
        _row(f"Built-up area about {est['built_up_sqft']:.0f} sq ft over {est['floors']} floor{'s' if est['floors'] > 1 else ''}; rough cost about Rs {est['subtotal_inr']:,.0f} at placeholder rates.", "estimate"),
        *[_row(a, "assumed") for a in assumed[:6]],
        _row("Every finish (tiles, paint, fittings, doors) needs a named brand and grade in your written agreement; the drawings do not set them.", "to_confirm"),
    ]

    questions = [
        "What is the safe bearing capacity of the soil, and at what depth does the report recommend founding?",
        "Which foundation type does the engineer recommend for this soil and for the number of floors you may add later?",
        "Which bar sizes, spacing and concrete grade will be used, and will you give me the structural drawings before work starts?",
        "What is the rate per item, what is included and excluded, and how are extra items priced?",
        "What are the payment stages and what work must be complete for each payment?",
        "Who supplies materials, and which brands are in the quotation?",
        "How long will each stage take, and what happens if the schedule slips or the monsoon stops work?",
        "How will you protect the neighbours' walls and drains while you dig?",
        "Who arranges the approvals, inspections and completion certificate?",
        *([f"Why are there {sum(1 for i in grid['items'] if i['status'] == 'warn')} long span(s) in the column grid, and how will you handle them?"] if any(i["status"] == "warn" for i in grid["items"]) else []),
        *([f"You asked for {len(user_cols)} column(s) in custom positions. Can you confirm them with calculations?"] if user_cols else []),
    ]
    return dict(title="Site pack", notice=NOT_A_CONTRACT, stages=stages, specification=spec, questions=questions,
                sources=dict(drawings="Read from the drawing model", estimate="From the concept estimate", assumed="Assumed for concept work", to_confirm="Needs confirmation by a licensed professional or the soil report", general="General good practice"))


def to_markdown(pack: dict, project_name: str = "") -> str:
    lines = [f"# {pack['title']}" + (f": {project_name}" if project_name else ""), "", f"> {pack['notice']}", ""]
    tag = {"to_confirm": " **(to confirm)**", "assumed": " _(assumed)_"}
    for st in pack["stages"]:
        lines += [f"## {st['name']}", ""] + [f"- [ ] {i['text']}{tag.get(i['source'], '')}" for i in st["items"]] + [""]
    lines += ["## Specification notes", ""] + [f"- {i['text']}{tag.get(i['source'], '')}" for i in pack["specification"]] + ["", "## Questions to ask before you sign", ""]
    lines += [f"{n}. {q}" for n, q in enumerate(pack["questions"], 1)]
    return "\n".join(lines) + "\n"
