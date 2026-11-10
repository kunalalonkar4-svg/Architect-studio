"""PRELIMINARY structural sizing for early planning only (IS 456 style rules of thumb).
Not a structural design. Needs a licensed structural engineer, soil investigation and code checks before use."""
from __future__ import annotations

import math

from .layout import room_metrics
from .model import ProjectModel


def _up(v: float, step: float) -> float:
    return math.ceil(v / step) * step


def prelim(model: ProjectModel, sbc_kn_m2: float = 150.0, fck: float = 20.0, fy: float = 500.0, bay_m2: float = 16.0) -> dict:
    lv = model.levels[0]
    rooms = [(s, room_metrics(model, s)) for s in model.spaces if not s.open_boundary]
    spans = [(s.name, sorted([m["clear_w"], m["clear_d"]])) for s, m in rooms]
    short = max((sp[1][0] for sp in spans), default=0.0)            # largest short-span of any slab panel (mm)
    long_ = max((sp[1][1] for sp in spans), default=0.0)
    # Slab: two-way, continuous-ish, span/depth ~ 30; add cover; round to 25 mm; never below 125
    slab_req = max(125.0, _up(short / 30 + 25, 25))
    slab_ok = lv.slab >= slab_req
    # Beam: depth ~ L/12 for continuous spans (rule of thumb), width = wall thickness (230)
    beam_d = max(300.0, _up(long_ / 12, 25))
    # Column: simplified axial capacity Pu = 0.4 fck Ac + (0.67 fy - 0.4 fck) Asc, Asc = 1% Ag
    w_service = 10.0                                                   # kN/m2: slab + finishes + live + share of beams/walls (single storey, rough)
    pu = 1.5 * w_service * bay_m2                                      # kN, factored, for an assumed tributary bay
    cap_per_mm2 = (0.4 * fck + (0.67 * fy - 0.4 * fck) * 0.01) / 1000   # kN per mm2 of gross area
    ag = pu / cap_per_mm2
    side = max(230.0, _up(math.sqrt(ag), 25))
    col_b, col_d = (230.0, max(230.0, _up(ag / 230.0, 25)))
    # Isolated footing under that column at the stated SBC (service load = Pu/1.5 plus 10% self weight)
    p_service = pu / 1.5 * 1.1
    f_side = _up(math.sqrt(p_service / sbc_kn_m2) * 1000, 100)
    f_depth = max(300.0, _up((f_side - col_d) / 2 * 0.6 + 100, 50))
    # Steel indicators (rule-of-thumb kg per m3 of concrete)
    return dict(
        assumptions=dict(sbc_kn_m2=sbc_kn_m2, concrete=f"M{fck:.0f}", steel=f"Fe{fy:.0f}", tributary_bay_m2=bay_m2, load_kn_m2=w_service, storeys="1 (ground floor + roof slab)"),
        items=[
            dict(id="slab", name="Roof slab thickness", value=f"{slab_req:.0f} mm", status="ok" if slab_ok else "check",
                 basis=f"Largest short panel span {short:.0f} mm ÷ 30 + 25 mm cover, min 125 mm. Model has {lv.slab:.0f} mm.",
                 note="" if slab_ok else f"Model slab {lv.slab:.0f} mm is below this rough requirement."),
            dict(id="beam", name="Beam size (depth × width)", value=f"{beam_d:.0f} × 230 mm", status="info", basis=f"Longest panel span {long_:.0f} mm ÷ 12, width equal to wall thickness.", note=""),
            dict(id="column", name="Column size", value=f"{col_b:.0f} × {col_d:.0f} mm", status="info",
                 basis=f"Assumed tributary bay {bay_m2:.0f} m² × {w_service:.0f} kN/m² × 1.5 = {pu:.0f} kN; axial capacity with 1% steel at M{fck:.0f}/Fe{fy:.0f}.", note=f"Square equivalent about {side:.0f} mm."),
            dict(id="footing", name="Isolated footing (plan × depth)", value=f"{f_side:.0f} × {f_side:.0f} × {f_depth:.0f} mm", status="info",
                 basis=f"Service load {p_service:.0f} kN ÷ assumed safe bearing capacity {sbc_kn_m2:.0f} kN/m².", note="Depends entirely on a soil test. Do not use the assumed bearing capacity for construction."),
        ],
        disclaimer="Preliminary rule-of-thumb sizes for early planning only. This is not a structural design or drawing and must not be used for construction. A licensed structural engineer must design and check the structure against current IS codes, with a soil investigation report.",
    )
