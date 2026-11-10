"""Canonical, revisioned project geometry model. All lengths are millimetres. Plot origin is the
south-west corner, +x east, +y north (true north = +y)."""
from __future__ import annotations

import hashlib
import json
from typing import Literal, Optional

from pydantic import BaseModel, Field

Side = Literal["n", "e", "s", "w"]
SIDE_NAMES = {"n": "north", "e": "east", "s": "south", "w": "west"}
SIDE_FROM_NAME = {v: k for k, v in SIDE_NAMES.items()}


class Setbacks(BaseModel):
    front: Optional[float] = None   # on the road side
    rear: Optional[float] = None
    left: Optional[float] = None    # viewed from the road looking in
    right: Optional[float] = None


class Assumption(BaseModel):
    id: str
    text: str
    kind: Literal["assumed", "user", "derived"] = "assumed"


class Brief(BaseModel):
    """Editable project inputs (what the user asked for)."""
    plot_frontage_mm: Optional[float] = None   # length along the road
    plot_depth_mm: Optional[float] = None      # perpendicular to the road
    road_side: Optional[Side] = None
    setbacks: Setbacks = Field(default_factory=Setbacks)
    bedrooms: Optional[int] = None
    kitchen_type: Optional[Literal["open", "closed"]] = None
    parking: Optional[bool] = None
    stair: Optional[bool] = True
    stair_position: Literal["front", "rear"] = "front"
    levels_now: int = 1
    future_levels: list[str] = Field(default_factory=list)
    requested_views: list[str] = Field(default_factory=lambda: ["plan"])
    notes: str = ""
    assumptions: list[Assumption] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)  # user-supplied planning constraints, verbatim
    dims_assumed_orientation: bool = False   # "30 by 50" -> first number taken along the road

    def missing(self) -> list[dict]:
        out = []
        if not (self.plot_frontage_mm and self.plot_depth_mm):
            out.append({"id": "plot_dims", "question": "Plot size (with unit: feet or metres)?"})
        if not self.road_side:
            out.append({"id": "road_side", "question": "Which side of the plot faces the road (north/east/south/west)?"})
        sb = self.setbacks
        if any(v is None for v in (sb.front, sb.rear, sb.left, sb.right)):
            out.append({"id": "setbacks", "question": "Required open space / setbacks on front, rear, left and right (from your local rules)?"})
        if self.bedrooms is None:
            out.append({"id": "bedrooms", "question": "How many bedrooms in total (1 to 5)? Say 'duplex' if you want two floors."})
        return out

    def ready(self) -> bool:
        return not [m for m in self.missing() if m["id"] != "setbacks"]


class Level(BaseModel):
    id: str = "GF"
    name: str = "Ground Floor"
    elevation: float = 0.0
    height: float = 3000.0          # floor to floor / to roof slab top
    slab: float = 150.0
    plinth: float = 450.0           # FFL above ground level
    parapet: float = 900.0


class Space(BaseModel):
    id: str
    level: str = "GF"
    key: str
    name: str
    kind: str
    x: float; y: float; w: float; h: float
    open_to: list[str] = Field(default_factory=list)
    open_boundary: bool = False      # no walls on edges that face outside (porch / parking)

    @property
    def x2(self): return self.x + self.w
    @property
    def y2(self): return self.y + self.h


class Wall(BaseModel):
    id: str
    level: str = "GF"
    x1: float; y1: float; x2: float; y2: float
    thickness: float
    kind: Literal["ext", "int"]

    @property
    def length(self) -> float:
        return abs(self.x2 - self.x1) + abs(self.y2 - self.y1)

    @property
    def horizontal(self) -> bool:
        return abs(self.y2 - self.y1) < 1e-6


class Opening(BaseModel):
    id: str
    key: str
    mark: str
    level: str = "GF"
    type: Literal["door", "window"]
    cx: float; cy: float             # centre on the host wall centreline
    width: float
    height: float
    sill: float = 0.0
    host: Optional[str] = None       # wall id (derived)
    swing: list[float] = Field(default_factory=lambda: [0.0, 1.0])  # unit vector the leaf swings towards
    hinge: Literal["start", "end"] = "start"
    from_space: Optional[str] = None
    to_space: Optional[str] = None
    note: str = ""


class StairFlight(BaseModel):
    risers: int
    riser_mm: float
    tread_mm: float
    treads_per_flight: int
    flight_width: float
    landing: float
    clear_w: float
    clear_len: float


class Stair(BaseModel):
    id: str = "ST1"
    level: str = "GF"
    space_id: str
    x: float; y: float; w: float; h: float
    run_axis: Literal["x", "y"] = "y"
    flight: Optional[StairFlight] = None
    start: list[float] = Field(default_factory=lambda: [0.0, 1.0])  # unit vector from stair centre to the end where the up flight starts


class ViewDef(BaseModel):
    id: str
    type: Literal["site", "plan", "roof", "elevation", "section", "rooms", "openings", "index", "structure"]
    level: str = "GF"
    facing: Optional[Side] = None
    cut: Optional[dict] = None     # {"axis": "x"|"y", "at": mm, "look": side, "label": "A"}


class SheetDef(BaseModel):
    id: str
    number: str
    title: str
    kind: str
    views: list[str]
    paper: str = "A3"
    orientation: Literal["landscape", "portrait"] = "landscape"
    scale: int = 100               # 0 = not to scale (tables)


class LayoutParams(BaseModel):
    """Parametric layout inputs. Edits change these; the engine recomputes every coordinate."""
    stair_position: Literal["front", "rear"] = "front"
    parking_w: float = 3000.0
    front_band: float = 4600.0
    rear_row: float = 2900.0
    bed1_w: float = 3300.0
    kitchen_w: Optional[float] = None
    col_w_front: float = 2300.0
    col_w_rear: float = 1314.0
    stair_w: float = 2300.0
    level_height: float = 3000.0
    ext_t: float = 230.0
    int_t: float = 115.0


class ProjectModel(BaseModel):
    version: int = 1
    units: str = "mm"
    plot: Optional[dict] = None   # {"w","h","frontage","depth","road_side","setbacks":{...},"setback_source":{...}}
    levels: list[Level] = Field(default_factory=lambda: [Level()])
    spaces: list[Space] = Field(default_factory=list)
    walls: list[Wall] = Field(default_factory=list)
    openings: list[Opening] = Field(default_factory=list)
    stairs: list[Stair] = Field(default_factory=list)
    views: list[ViewDef] = Field(default_factory=list)
    sheets: list[SheetDef] = Field(default_factory=list)
    params: LayoutParams = Field(default_factory=LayoutParams)
    opening_overrides: dict = Field(default_factory=dict)   # key -> {width,height,sill,shift}
    space_notes: dict = Field(default_factory=dict)
    roof_approved: bool = False
    assumptions: list[Assumption] = Field(default_factory=list)
    review_status: str = "concept_unreviewed"

    def level(self, lid="GF") -> Level:
        return next(l for l in self.levels if l.id == lid)

    @property
    def top_level(self) -> Level:
        return self.levels[-1]

    def total_height(self) -> float:
        t = self.levels[-1]
        return t.elevation + t.height

    def at_level(self, lid: str) -> "ProjectModel":
        """Copy of the model holding only one level's spaces, walls, openings and stairs (for per-floor plans)."""
        m = self.model_copy(deep=False)
        m.spaces = [x for x in self.spaces if x.level == lid]
        m.walls = [x for x in self.walls if x.level == lid]
        m.openings = [x for x in self.openings if x.level == lid]
        m.stairs = [x for x in self.stairs if x.level == lid]
        return m

    def space(self, sid) -> Optional[Space]:
        return next((s for s in self.spaces if s.id == sid or s.key == sid), None)

    def opening_by_mark(self, mark: str) -> Optional[Opening]:
        return next((o for o in self.openings if o.mark.lower() == mark.lower() or o.key == mark), None)

    def footprint(self) -> Optional[tuple]:
        """Centreline bbox of all spaces."""
        if not self.spaces:
            return None
        return (min(s.x for s in self.spaces), min(s.y for s in self.spaces),
                max(s.x2 for s in self.spaces), max(s.y2 for s in self.spaces))

    def outer_bounds(self) -> Optional[tuple]:
        f = self.footprint()
        if not f:
            return None
        t = self.params.ext_t / 2
        return (f[0] - t, f[1] - t, f[2] + t, f[3] + t)


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def digest(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()[:16]
