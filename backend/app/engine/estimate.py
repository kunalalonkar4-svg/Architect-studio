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
    "excavation": 350.0,  # per m3
    "pcc": 6500.0,        # per m3, PCC bed under footings/walls
    "foundation": 9500.0, # per m3, RCC footings + plinth beam (excl. steel)
    "steel": 78.0,        # per kg, reinforcement supplied, cut, bent and tied
    "waterproof": 450.0,  # per m2, terrace waterproofing
    "electrical": 650.0,  # per m2 built-up, concealed wiring + fittings (allowance)
    "plumbing": 550.0,    # per m2 built-up, supply + drainage (allowance)
    "sanitary": 25000.0,  # per toilet, fixtures + fittings (allowance)
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
    wall_len = sum(w.length for w in model.walls) / 1000.0
    trench = wall_len * 0.9 * 1.2                              # 900 mm wide x 1.2 m deep
    pcc = wall_len * 0.9 * 0.1
    found = wall_len * 0.6 * 0.3 + wall_len * 0.23 * 0.3     # footing strip + plinth beam
    beams = wall_len * 0.23 * 0.3
    steel_kg = slab_v * 80 + found * 70 + beams * 120          # rule-of-thumb kg per m3
    toilets = sum(1 for sp in model.spaces if sp.kind in ("toilet", "bath", "bathroom"))
    items = [
        dict(id="masonry", name="Masonry (walls)", unit="m³", qty=round(mas, 2), basis="Wall centreline length × thickness × height under slab, less openings"),
        dict(id="plaster", name="Plaster (both faces)", unit="m²", qty=round(plaster, 2), basis="Wall area × 2 faces, less openings"),
        dict(id="flooring", name="Flooring (enclosed rooms)", unit="m²", qty=round(floor, 2), basis="Sum of room clear areas, excluding open porch/parking"),
        dict(id="slab", name="RCC roof slab", unit="m³", qty=round(slab_v, 2), basis=f"Outer footprint × {lv.slab:.0f} mm slab"),
        dict(id="doors", name=f"Doors ({nd} nos.)", unit="m²", qty=round(door_a, 2), basis="Sum of door opening areas"),
        dict(id="windows", name=f"Windows ({nw} nos.)", unit="m²", qty=round(win_a, 2), basis="Sum of window opening areas"),
        dict(id="paint", name="Interior painting", unit="m²", qty=round(paint, 2), basis="Plastered wall area + ceiling (approx.)"),
        dict(id="excavation", name="Excavation for foundation", unit="m³", qty=round(trench, 2), basis="Wall length × 0.9 m wide × 1.2 m deep (assumed trench)"),
        dict(id="pcc", name="PCC under foundation", unit="m³", qty=round(pcc, 2), basis="Wall length × 0.9 m × 100 mm"),
        dict(id="foundation", name="RCC footing strip + plinth beam", unit="m³", qty=round(found, 2), basis="Assumed 600×300 strip footing and 230×300 plinth beam along all walls"),
        dict(id="steel", name="Reinforcement steel", unit="kg", qty=round(steel_kg, 0), basis="Rule of thumb: slab 80, foundation 70, beams 120 kg/m³ of concrete (beams assumed at wall lines)"),
        dict(id="waterproof", name="Terrace waterproofing", unit="m²", qty=round(footprint, 2), basis="Outer footprint"),
        dict(id="electrical", name="Electrical (allowance)", unit="m²", qty=round(footprint, 2), basis="Allowance per m² built-up, replace with a real electrical estimate"),
        dict(id="plumbing", name="Plumbing (allowance)", unit="m²", qty=round(footprint, 2), basis="Allowance per m² built-up, replace with a real plumbing estimate"),
        dict(id="sanitary", name=f"Sanitary fixtures ({toilets} toilet(s))", unit="no.", qty=float(toilets), basis="Allowance per toilet"),
    ]
    return dict(currency="INR", built_up_m2=round(footprint, 2), carpet_m2=round(floor, 2), items=items, rates=DEFAULT_RATES,
                disclaimer="Concept-level quantities from the drawing model. Rates are editable placeholders, not market prices or a quotation. Foundation, steel, electrical and plumbing lines are rule-of-thumb allowances, not designed quantities. Excludes site development, boundary wall, lift, furniture, premium finishes, taxes, labour contingencies and site conditions.")
