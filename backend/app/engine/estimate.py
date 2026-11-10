"""Approximate quantity take-off straight from the canonical model (no drawing parsing).
Quantities are concept-level; rates are editable placeholders supplied by the user, never a quote."""
from __future__ import annotations

from .layout import room_metrics
from .model import ProjectModel

# Placeholder INR rates. They are defaults to start from; the user edits them in the UI.
DEFAULT_RATES = {
    "masonry": 7500.0,    # per m3, brick/block masonry
    "plaster": 380.0,     # per m2, per face (cement plaster)
    "flooring": 1400.0,   # per m2
    "slab": 11000.0,      # per m3, RCC slab incl. steel + shuttering (rough)
    "doors": 120.0,       # per m2 of opening (frame + shutter, rough)
    "windows": 450.0,     # per m2 of opening
    "paint": 85.0,        # per m2
}


def estimate(model: ProjectModel) -> dict:
    lv = model.levels[0]
    h_wall = max(lv.height - lv.slab, 0) / 1000.0            # m, masonry height under slab
    ob = model.outer_bounds()
    footprint = (ob[2] - ob[0]) * (ob[3] - ob[1]) / 1e6 if ob else 0.0
    openings = {w.id: 0.0 for w in model.walls}
    door_a = win_a = 0.0
    nd = nw = 0
    for o in model.openings:
        a = o.width * o.height / 1e6
        if o.type == "door":
            door_a += a; nd += 1
        else:
            win_a += a; nw += 1
        if o.host in openings:
            openings[o.host] += a
    mas = plaster = 0.0
    for w in model.walls:
        L = w.length / 1000.0
        t = w.thickness / 1000.0
        area = max(L * h_wall - openings[w.id], 0.0)
        mas += area * t
        plaster += area * 2
    rooms = [(s, room_metrics(model, s)) for s in model.spaces]
    floor = sum(m["area_m2"] for s, m in rooms if not s.open_boundary)
    slab_v = footprint * lv.slab / 1000.0
    paint = plaster + floor                                   # walls + ceilings (approx.)
    items = [
        dict(id="masonry", name="Masonry (walls)", unit="m³", qty=round(mas, 2), basis="Wall centreline length × thickness × height under slab, less openings"),
        dict(id="plaster", name="Plaster (both faces)", unit="m²", qty=round(plaster, 2), basis="Wall area × 2 faces, less openings"),
        dict(id="flooring", name="Flooring (enclosed rooms)", unit="m²", qty=round(floor, 2), basis="Sum of room clear areas, excluding open porch/parking"),
        dict(id="slab", name="RCC roof slab", unit="m³", qty=round(slab_v, 2), basis=f"Outer footprint × {lv.slab:.0f} mm slab"),
        dict(id="doors", name=f"Doors ({nd} nos.)", unit="m²", qty=round(door_a, 2), basis="Sum of door opening areas"),
        dict(id="windows", name=f"Windows ({nw} nos.)", unit="m²", qty=round(win_a, 2), basis="Sum of window opening areas"),
        dict(id="paint", name="Interior painting", unit="m²", qty=round(paint, 2), basis="Plastered wall area + ceiling (approx.)"),
    ]
    return dict(currency="INR", built_up_m2=round(footprint, 2), carpet_m2=round(floor, 2), items=items, rates=DEFAULT_RATES,
                disclaimer="Concept-level quantities from the drawing model. Rates are editable placeholders, not market prices or a quotation. Excludes foundation, excavation, steel detailing, electrical, plumbing, finishes beyond those listed, taxes and site conditions.")
