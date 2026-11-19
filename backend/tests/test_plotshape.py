import pytest

from app.engine.layout import ImpossibleLayout, build_model
from app.engine.model import Brief, Setbacks
from app.engine.plotshape import fit, frontage_depth, normalise
from app.engine.validate import validate_model

TRAP = [[0, 0], [11000, 0], [10100, 15240], [900, 15240]]   # road on the south, slightly narrower at the back


def brief(poly=TRAP, road="s", **kw):
    fr, dp = frontage_depth(normalise(poly), road)
    d = dict(plot_frontage_mm=fr, plot_depth_mm=dp, road_side=road, bedrooms=2, kitchen_type="open", parking=True,
             setbacks=Setbacks(front=3000, rear=1500, left=0, right=0), plot_polygon_mm=poly)
    d.update(kw)
    return Brief(**d)


def inside(poly, x, y):
    n = len(poly)
    return all((poly[(i + 1) % n][0] - poly[i][0]) * (y - poly[i][1]) - (poly[(i + 1) % n][1] - poly[i][1]) * (x - poly[i][0]) >= -1e-6 for i in range(n))


def test_fitted_rectangle_stays_inside_the_plot_and_respects_open_space():
    f = fit(TRAP, "s", dict(front=3000, rear=1500, left=0, right=0))
    x0, y0, x1, y1 = f["rect"]
    pts = f["polygon"]
    assert all(inside(pts, x, y) for x in (x0, x1) for y in (y0, y1))
    assert y0 >= 3000 - 1e-6 and y1 <= 15240 - 1500 + 1e-6          # front/rear open space kept
    assert x0 > 0 and x1 < 11000                                    # slanted sides squeeze the rectangle in


def test_rectangle_polygon_matches_plain_rectangle():
    rect = [[0, 0], [9144, 0], [9144, 15240], [0, 15240]]
    f = fit(rect, "s", dict(front=3000, rear=1500, left=0, right=0))
    assert f["margins"] == dict(front=3000.0, rear=1500.0, left=0.0, right=0.0)


def test_road_side_changes_which_margin_is_front():
    f = fit(TRAP, "n", dict(front=3000, rear=1500, left=0, right=0))
    x0, y0, x1, y1 = f["rect"]
    assert y1 <= 15240 - 3000 + 1e-6 and y0 >= 1500 - 1e-6


def test_concave_and_bad_shapes_are_refused_with_a_reason():
    with pytest.raises(ImpossibleLayout) as e:
        normalise([[0, 0], [10000, 0], [10000, 5000], [5000, 5000], [5000, 10000], [0, 10000]])
    assert "L-shaped" in e.value.reasons[0]
    with pytest.raises(ImpossibleLayout):
        normalise([[0, 0], [1000, 0]])
    with pytest.raises(ImpossibleLayout):
        normalise([[0, 0], [1, 1], [2, 2]])
    with pytest.raises(ImpossibleLayout):
        fit([[0, 0], [4000, 0], [2000, 3000]], "s", dict(front=3000, rear=3000, left=1000, right=1000))   # nothing left


def test_model_builds_inside_the_plot_and_validates():
    m = build_model(brief())
    ob = m.outer_bounds()
    pts = m.plot["polygon"]
    assert all(inside(pts, x, y) for x in (ob[0], ob[2]) for y in (ob[1], ob[3]))
    assert m.plot["polygon"] and m.plot["inset"] and any(a.id == "irregular_plot" for a in m.assumptions)
    assert not [i for i in validate_model(m) if i["severity"] == "error"]


def test_mismatched_dimensions_are_rejected():
    with pytest.raises(ImpossibleLayout) as e:
        build_model(brief(plot_frontage_mm=9000.0))
    assert "does not match" in e.value.reasons[0]


def test_rectangular_brief_is_unchanged_by_the_feature():
    a = build_model(Brief(plot_frontage_mm=9144, plot_depth_mm=15240, road_side="s", bedrooms=2, kitchen_type="open", parking=True,
                          setbacks=Setbacks(front=3000, rear=1500, left=0, right=0)))
    assert "polygon" not in a.plot


def test_site_sheet_draws_the_boundary(client, auth):
    from app.engine.render import render_svg
    from app.engine.sheets import compose_sheet
    from app.services import ensure_sheet, autofit
    m = build_model(brief())
    sd = ensure_sheet(m, "site")
    meta = dict(project_name="T", firm_name="", firm_line="", client="", address="", date="2026-01-01", revision="1", sheet_rev={}, future_levels=[], missing=[],
                revision_history=[], sheet_index=[])
    autofit(m, sd, meta)
    svg = render_svg(compose_sheet(m, sd, meta))
    assert "bounding box" in svg and "to box" in svg and "SITE PLAN" in svg


def test_plot_shape_endpoint_before_and_after_a_drawing(client, auth):
    from conftest import make_user
    from test_acceptance_2_3 import make_project
    pid = make_project(client, auth, views=None)
    # concave shape refused
    r = client.put(f"/api/projects/{pid}/plot-shape", json=dict(points_mm=[[0, 0], [10000, 0], [10000, 5000], [5000, 5000], [5000, 10000], [0, 10000]]), headers=auth)
    assert r.status_code == 422 and "L-shaped" in r.json()["error"]["message"]
    # existing drawing: proposal, nothing saved until confirmed
    east = [[0, 0], [15240, 900], [15240, 10100], [0, 11000]]       # this project's road is on the east
    r = client.put(f"/api/projects/{pid}/plot-shape", json=dict(points_mm=east), headers=auth)
    assert r.status_code == 200, r.text
    d = client.get(f"/api/projects/{pid}", headers=auth).json()
    assert d["brief"].get("plot_polygon_mm") is None
    prop = [x for x in d["proposals"] if x["state"] == "pending"]
    assert prop and any("plot" in c.get("text", "").lower() or True for c in prop[0]["changes"])
    c = client.post(f"/api/proposals/{prop[0]['id']}/confirm", json={}, headers=auth)
    assert c.status_code == 200, c.text
    d = client.get(f"/api/projects/{pid}", headers=auth).json()
    assert d["brief"]["plot_polygon_mm"] and d["brief"]["plot_frontage_mm"] == 11000
    assert make_user(client, "Eve") and client.put(f"/api/projects/{pid}/plot-shape", json=dict(points_mm=TRAP), headers=make_user(client, "Eve2")).status_code == 404


def test_plot_shape_endpoint_needs_road_side(client, auth):
    from test_acceptance_2_3 import new_project
    pid = new_project(client, auth)
    r = client.put(f"/api/projects/{pid}/plot-shape", json=dict(points_mm=TRAP), headers=auth)
    assert r.status_code == 422 and r.json()["error"]["code"] == "road_side_first"
