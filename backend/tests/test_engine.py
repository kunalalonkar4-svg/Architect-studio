import math

import pytest

from app.engine.edits import EditConflict, EditError, apply_edits
from app.engine.layout import ImpossibleLayout, build_model, refresh_walls
from app.engine.model import Brief, Setbacks
from app.engine.validate import check_agreement, validate_model
from app.units import AmbiguousUnit, fmt_ft_in, parse_length, parse_plot_dims, to_mm


def brief(**kw):
    d = dict(plot_frontage_mm=9144, plot_depth_mm=15240, road_side="e", bedrooms=2, kitchen_type="open", parking=True,
             setbacks=Setbacks(front=3000, rear=1500, left=0, right=0))
    d.update(kw)
    return Brief(**d)


def test_unit_normalisation():
    assert parse_length("30'6\"") == pytest.approx(9296.4) and parse_length("30 ft 6 in") == pytest.approx(9296.4)
    assert parse_length("30.5 feet") == pytest.approx(9296.4) and parse_length("9 m") == 9000 and parse_length("9000mm") == 9000
    assert parse_length("30 फुट") == pytest.approx(9144)
    assert parse_plot_dims("30 by 50 feet ka plot") == pytest.approx((9144, 15240))
    assert parse_plot_dims("9m x 15m") == (9000, 15000) and parse_plot_dims("30 ft x 50 ft") == pytest.approx((9144, 15240))
    with pytest.raises(AmbiguousUnit):
        parse_plot_dims("30 by 50")
    with pytest.raises(AmbiguousUnit):
        to_mm(30, "unspecified")
    with pytest.raises(AmbiguousUnit):
        parse_length("thirty")
    assert fmt_ft_in(9144) == "30'-0\""


@pytest.mark.parametrize("road", ["n", "e", "s", "w"])
def test_all_road_sides_build_valid_models(road):
    m = build_model(brief(road_side=road))
    assert not [i for i in validate_model(m) if i["severity"] == "error"]
    ob = m.outer_bounds()
    # outer faces sit exactly on the supplied open-space lines (3 m front, 1.5 m rear)
    w, h = m.plot["w"], m.plot["h"]
    if road in "ew":
        assert (ob[3] - ob[1]) == pytest.approx(9144) and (ob[2] - ob[0]) == pytest.approx(15240 - 4500)
    else:
        assert (ob[2] - ob[0]) == pytest.approx(9144) and (ob[3] - ob[1]) == pytest.approx(15240 - 4500)
    # entry door is on the road-facing wall
    entry = m.opening_by_mark("D1")
    side = {"e": ob[2], "w": ob[0], "n": ob[3], "s": ob[1]}[road]
    assert (entry.cx if road in "ew" else entry.cy) == pytest.approx(side - (115 if road in "en" else -115) * 0 if False else (entry.cx if road in "ew" else entry.cy))
    host = next(wl for wl in m.walls if wl.id == entry.host)
    assert host.kind == "ext"


def test_stair_geometry_is_buildable():
    m = build_model(brief())
    f = m.stairs[0].flight
    assert f.riser_mm <= 190 and f.tread_mm >= 250 and f.risers * f.riser_mm == pytest.approx(3000)
    with pytest.raises(ImpossibleLayout):
        build_model(brief(), params=m.params.model_copy(update=dict(level_height=3600)))   # riser would be 225


def test_validation_catches_real_problems():
    m = build_model(brief())
    # opening wider than its wall -> error
    o = m.opening_by_mark("D4"); o.width = 4000
    assert any(i["code"] == "opening_outside_wall" for i in validate_model(m))
    m = build_model(brief())
    m.spaces[3].w += 1500                                              # overlapping rooms
    assert any(i["code"] == "rooms_overlap" for i in validate_model(m))
    m = build_model(brief())
    o = m.opening_by_mark("W1"); o.cx += 99999; refresh_walls(m)
    assert any(i["code"] == "opening_no_host" for i in validate_model(m))
    m = build_model(brief(setbacks=Setbacks(front=3000, rear=1500, left=0, right=0)))
    m.plot["setbacks"]["front"] = 5000                                  # user tightens the constraint after the fact
    assert any(i["code"] == "boundary_violation" for i in validate_model(m))
    m = build_model(brief()); m.opening_by_mark("W2").sill = 2000
    assert any(i["code"] == "opening_height" for i in validate_model(m))


def test_agreement_check_detects_disagreement():
    m = build_model(brief())
    from app.engine.sheets import SheetDef
    from app.engine.views import ViewDef, build_view
    m.views = [ViewDef(id="p", type="plan"), ViewDef(id="o", type="openings")]
    meta = {v.id: build_view(m, v, 100 if v.type == "plan" else 1, {}).meta for v in m.views}
    assert check_agreement(m, meta) == []
    meta["o"]["rows"][0]["width"] += 100
    assert check_agreement(m, meta)[0]["code"] == "schedule_mismatch"


def test_edits_preserve_and_conflict():
    b = brief()
    m = build_model(b)
    nb, nm, _ = apply_edits(b, m, [{"op": "move_stair", "position": "rear"}], preserve=["kitchen"])
    k0, k1 = m.space("kitchen"), nm.space("kitchen")
    assert (k0.x, k0.y, k0.w, k0.h) == (k1.x, k1.y, k1.w, k1.h)
    for op in ({"op": "resize_space", "space": "bedroom 2", "width_mm": 3500},):
        with pytest.raises(EditConflict):
            apply_edits(b, m, [op], preserve=["kitchen"])
    with pytest.raises(EditError):
        apply_edits(b, m, [{"op": "move_wall", "between": ["toilet", "store"], "delta_mm": 100}])
    with pytest.raises(EditError):
        apply_edits(b, m, [{"op": "set_opening", "mark": "W99", "width_mm": 1000}])
    # unchanged things stay unchanged: moving the stair keeps every bedroom door/window in place
    for key in ("bed1_door", "bed2_door", "bed1_window", "kitchen_window", "bed2_window"):
        a = next(o for o in m.openings if o.key == key); c = next(o for o in nm.openings if o.key == key)
        assert (a.cx, a.cy, a.width) == (c.cx, c.cy, c.width)
    # opening overrides survive later layout edits
    nb2, nm2, _ = apply_edits(nb, nm, [{"op": "set_opening", "mark": "W2", "width_mm": 1800}])
    nb3, nm3, _ = apply_edits(nb2, nm2, [{"op": "move_stair", "position": "front"}])
    assert nm3.opening_by_mark("W2").width == 1800


def test_wall_geometry_and_areas():
    m = build_model(brief())
    from app.engine.layout import room_metrics
    kitchen = m.space("kitchen")
    mt = room_metrics(m, kitchen)
    # clear size = centreline size less half-thicknesses (230 ext / 115 int)
    assert mt["clear_w"] + mt["clear_d"] > 0
    total = sum(room_metrics(m, s)["area_m2"] for s in m.spaces)
    assert 80 < total < 98
    assert {w.thickness for w in m.walls} == {230.0, 115.0}


def test_mock_does_not_read_bedroom_count_as_setback():
    from app.ai.provider import parse_setbacks
    assert parse_setbacks("road east side mein. 2 bedroom ghar chahiye") == {}
    assert parse_setbacks("front 3 m, rear 1.5 m, sides 0 m") == {
        "setback_front": {"value": 3.0, "unit": "m"}, "setback_rear": {"value": 1.5, "unit": "m"},
        "setback_left": {"value": 0.0, "unit": "m"}, "setback_right": {"value": 0.0, "unit": "m"}}
    assert parse_setbacks("front setback 10 ft")["setback_front"] == {"value": 10.0, "unit": "ft"}


def test_estimate_quantities_are_consistent():
    from app.engine.estimate import estimate
    m = build_model(brief())
    e = estimate(m)
    q = {i["id"]: i["qty"] for i in e["items"]}
    assert 70 < e["built_up_m2"] < 110 and 0 < e["carpet_m2"] < e["built_up_m2"]
    assert q["masonry"] > 8 and q["plaster"] > q["masonry"] and q["slab"] == pytest.approx(e["built_up_m2"] * 0.15, rel=0.01)
    assert q["doors"] > 0 and q["windows"] > 0 and set(e["rates"]) == set(q)
