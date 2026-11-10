"""Allow-listed application operations exposed to the model. Every call is schema-validated here and
permission-checked in ops.py before anything runs. Numbers always carry a unit; the server converts to mm."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

LENGTH = {"type": "object", "description": "A length with its unit exactly as the user stated it. Use unit 'unspecified' if the user gave no unit.",
          "properties": {"value": {"type": "number"}, "unit": {"type": "string", "enum": ["mm", "cm", "m", "ft", "in", "unspecified"]}},
          "required": ["value", "unit"], "additionalProperties": False}
SIDE = {"type": "string", "enum": ["north", "east", "south", "west"]}
VIEW_KINDS = ["site", "plan", "roof", "elevations", "section", "schedules", "index", "structure"]
FACINGS = ["front", "rear", "left", "right", "north", "east", "south", "west"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Length(Strict):
    value: float
    unit: Literal["mm", "cm", "m", "ft", "in", "unspecified"]


class UpdateBrief(Strict):
    plot_frontage: Optional[Length] = None
    plot_depth: Optional[Length] = None
    dims_orientation_assumed: Optional[bool] = None
    road_side: Optional[Literal["north", "east", "south", "west"]] = None
    setback_front: Optional[Length] = None
    setback_rear: Optional[Length] = None
    setback_left: Optional[Length] = None
    setback_right: Optional[Length] = None
    bedrooms: Optional[int] = None
    floors: Optional[int] = None
    kitchen_type: Optional[Literal["open", "closed"]] = None
    parking: Optional[bool] = None
    stair: Optional[bool] = None
    stair_position: Optional[Literal["front", "rear"]] = None
    future_levels: Optional[list[str]] = None
    requested_views: Optional[list[Literal["site", "plan", "roof", "elevations", "section", "schedules", "index", "structure"]]] = None
    constraints: Optional[list[str]] = None
    notes: Optional[str] = None
    language: Optional[Literal["en", "hi", "hinglish"]] = None


class Question(Strict):
    id: str
    question: str
    why: Optional[str] = None
    options: Optional[list[str]] = None


class AskClarification(Strict):
    questions: list[Question]


class GenerateLayout(Strict):
    use_assumptions: bool = False
    stair_position: Optional[Literal["front", "rear"]] = None
    note: Optional[str] = None


class OptionSpec(Strict):
    label: str
    stair_position: Literal["front", "rear"]
    tradeoff: Optional[str] = None


class ProposeOptions(Strict):
    options: list[OptionSpec]
    use_assumptions: bool = False


class EditItem(Strict):
    op: Literal["move_stair", "resize_space", "move_wall", "set_opening", "set_level_height", "set_brief"]
    position: Optional[Literal["front", "rear"]] = None
    space: Optional[str] = None
    width: Optional[Length] = None
    depth: Optional[Length] = None
    between: Optional[list[str]] = None
    delta: Optional[Length] = None
    mark: Optional[str] = None
    height: Optional[Length] = None
    sill: Optional[Length] = None
    shift: Optional[Length] = None
    hinge: Optional[Literal["start", "end"]] = None
    bedrooms: Optional[int] = None
    floors: Optional[int] = None
    kitchen_type: Optional[Literal["open", "closed"]] = None
    parking: Optional[bool] = None


class ProposeEdit(Strict):
    summary: str
    edits: list[EditItem]
    preserve: Optional[list[str]] = None


class PlanRoomT(Strict):
    key: str
    name: str
    kind: Literal["living", "dining", "kitchen", "bedroom", "toilet", "store", "study", "entry", "stair", "parking", "sitout",
                  "balcony", "passage", "pooja", "utility", "terrace"]
    level: Literal["GF", "FF"]
    x: float
    y: float
    w: float
    h: float


class PlanConnT(Strict):
    a: str
    b: str
    type: Literal["door", "open"]


class DesignFloorPlan(Strict):
    summary: str
    rooms: list[PlanRoomT]
    connections: list[PlanConnT]
    entry_room: str
    use_assumptions: Optional[bool] = None
    final: Optional[bool] = None


class ViewSpec(Strict):
    kind: Literal["site", "plan", "roof", "elevations", "section", "schedules", "index", "structure"]
    paper: Optional[Literal["A4", "A3", "A2", "A1", "A0"]] = None
    scale: Optional[Literal[20, 25, 50, 100, 200, 500]] = None
    facings: Optional[list[Literal["front", "rear", "left", "right", "north", "east", "south", "west"]]] = None


class GenerateViews(Strict):
    views: list[ViewSpec]


class RequestExport(Strict):
    format: Literal["pdf", "dxf", "png"]
    sheets: list[str] = Field(default_factory=lambda: ["all"])
    paper: Optional[Literal["A4", "A3", "A2", "A1", "A0"]] = None
    scale: Optional[Literal[20, 25, 50, 100, 200, 500]] = None
    orientation: Optional[Literal["landscape", "portrait"]] = None


class ExplainValidation(Strict):
    pass


class GetQuantities(Strict):
    pass


MODELS = {"update_brief": UpdateBrief, "ask_clarification": AskClarification, "generate_layout": GenerateLayout,
          "propose_options": ProposeOptions, "propose_edit": ProposeEdit, "generate_views": GenerateViews,
          "request_export": RequestExport, "explain_validation": ExplainValidation, "get_quantities": GetQuantities,
          "design_floor_plan": DesignFloorPlan}
TEMPLATE_ONLY = {"generate_layout", "propose_options"}   # fixed-template tools, kept for the offline demo provider only

DESCRIPTIONS = {
    "update_brief": "Record or correct the project brief (plot, road side, open-space/setbacks, rooms, deliverables). Only fields the user actually stated; never invent values. Put each number with its unit.",
    "ask_clarification": "Ask only the essential questions that materially change the design (e.g. which side is the road, required open spaces). Keep them short.",
    "generate_layout": "Generate the first dimensioned ground-floor layout and drawing preview from the brief. use_assumptions=true only when the user agreed to proceed with clearly labelled concept assumptions.",
    "propose_options": "Offer 2-3 alternative layouts (different stair positions). The server computes exact dimensions for each; the user then chooses one.",
    "propose_edit": "Propose changes to the existing design (move stair, resize a room, move a partition wall, change a door/window size, floor height, bedrooms). The server computes all coordinates, shows the changes and affected drawings, and commits only after the user confirms. List rooms the user said to keep unchanged in preserve.",
    "generate_views": "Add or update requested drawing sheets (site, plan, roof, elevations, section, schedules, index, structure = preliminary column/footing/beam layout). Generate only what the user asked for.",
    "request_export": "Start an export (pdf = vector sheets at exact paper size, dxf = layered model-space CAD, png). Do not say a file is ready until the app confirms.",
    "explain_validation": "Read the current validation issues of the active revision so you can explain them to the user in simple language.",
    "design_floor_plan": ("Design the house yourself, as an experienced architect: choose every room, its rectangle and how rooms connect, for ANY plot size, 1-5+ bedrooms, one or two floors. "
                          "Use envelope_mm from the project context. Coordinates are mm, wall-centreline: x along the road frontage (left to right looking in from the road), y away from the road, origin at the front-left corner of the envelope; keep every value a multiple of 25. "
                          "Rules the server enforces: rooms of one floor must tile ONE rectangle exactly (no gaps, no overlaps, inside the envelope); the first floor must have the same outer rectangle as the ground floor (use balcony/terrace rooms for unused area); "
                          "every room must be reachable from entry_room via 'door' (needs >= 1100 mm shared wall) or 'open' (no wall, >= 600 mm) connections; bedrooms, living, kitchen and study need an outside wall for a window; "
                          "two floors need a room of kind 'stair' with the identical rectangle on both floors (>= 2300 x 3000 mm for the dog-leg stair). Name first-floor keys with an f_ prefix. "
                          "WORKFLOW: call with final=false first; the server returns a drawing image of your plan with room sizes and a review checklist, but saves nothing. Review it critically, fix and re-preview as needed, then call with final=true and the identical plan to save it (server refuses final=true for a plan you have not previewed). If a design already exists, final=true creates a proposal the user confirms. If the server returns problems, fix them and call again."),
    "get_quantities": "Read the computed material quantities, placeholder-rate cost lines and PRELIMINARY structural sizes for the active revision. Use these numbers when the user asks about cost, BOQ, materials, beam/column/footing sizes; never invent quantities.",
}


def anthropic_tools(strict: bool = True) -> list[dict]:
    out = []
    for name, m in MODELS.items():
        if name in TEMPLATE_ONLY:
            continue
        schema = m.model_json_schema()
        schema = _inline(schema)
        schema.pop("title", None)
        t = {"name": name, "description": DESCRIPTIONS[name], "input_schema": schema}
        if strict:
            t["strict"] = True
        out.append(t)
    return out


def _inline(schema: dict) -> dict:
    """Inline $defs and drop pydantic noise so the schema is plain JSON Schema with additionalProperties:false."""
    defs = schema.pop("$defs", {})
    def walk(n):
        if isinstance(n, dict):
            if "$ref" in n:
                return walk(defs[n["$ref"].split("/")[-1]])
            n = {k: walk(v) for k, v in n.items() if k not in ("title", "default")}
            if n.get("type") == "object" and "additionalProperties" not in n:
                n["additionalProperties"] = False
            return n
        if isinstance(n, list):
            return [walk(x) for x in n]
        return n
    return walk(schema)
