import pytest

from app.engine.estimate import DEFAULT_RATES, estimate
from app.engine.layout import build_model
from app.engine.model import Brief, Setbacks
from app.engine.review import compass, review


def brief(**kw):
    d = dict(plot_frontage_mm=9144, plot_depth_mm=15240, road_side="e", bedrooms=2, kitchen_type="open", parking=True,
             setbacks=Setbacks(front=3000, rear=1500, left=0, right=0))
    d.update(kw)
    return Brief(**d)


def test_compass_eight_points():
    assert [compass(1, 0), compass(1, 1), compass(0, 1), compass(-1, 1), compass(-1, 0), compass(-1, -1), compass(0, -1), compass(1, -1)] == \
        ["E", "NE", "N", "NW", "W", "SW", "S", "SE"]


def test_planning_limits_only_checked_against_supplied_values():
    m = build_model(brief())
    r = review(m)["planning"]
    codes = {i["code"]: i["status"] for i in r["items"]}
    assert codes["far"] == "info" and codes["coverage"] == "info" and codes["height"] == "info"   # nothing guessed
    plot = r["measured"]["plot_area_m2"]
    assert plot == pytest.approx(9.144 * 15.24, abs=0.01)
    r2 = review(m, far_max=0.01, coverage_max_pct=90, height_max_m=20)["planning"]
    st = {i["code"]: i["status"] for i in r2["items"]}
    assert st["far"] == "fail" and st["coverage"] == "ok" and st["height"] == "ok"


def test_planning_far_scales_with_floors():
    one = review(build_model(brief()))["planning"]["measured"]
    two = review(build_model(brief(levels_now=2, bedrooms=4)))["planning"]["measured"]
    assert two["far"] > one["far"] and two["built_up_m2"] > one["built_up_m2"]


@pytest.mark.parametrize("road", ["n", "e", "s", "w"])
def test_vastu_score_is_bounded_and_explained(road):
    v = review(build_model(brief(road_side=road)))["vastu"]
    assert 0 <= v["score"] <= 100 and v["items"] and "not a building code" in v["note"]
    assert all(i["detail"] for i in v["items"])


def test_vastu_flags_kitchen_in_ne_as_warning():
    from app.engine.review import vastu
    m = build_model(brief())
    k = next(s for s in m.spaces if s.kind == "kitchen")
    fp = m.footprint()
    # move the kitchen's centre into the north-east quadrant of the building
    k.x, k.y = fp[2] - k.w, fp[3] - k.h
    item = next(i for i in vastu(m)["items"] if i["code"] == f"vastu_{k.key}")
    assert item["status"] == "warn" and "NE" in item["title"]


def test_ventilation_ratio_reports_windows_and_toilets():
    m = build_model(brief())
    lv = review(m)["light_ventilation"]["items"]
    assert any(i["code"] in ("ventilation_ok", "ventilation_low") for i in lv)
    assert any(i["code"] in ("ceiling_ok", "ceiling_low") for i in lv)
    strict = review(m, min_window_ratio=0.5)["light_ventilation"]["items"]
    assert any(i["code"] == "ventilation_low" for i in strict)


def test_column_grid_has_columns_and_spans():
    g = review(build_model(brief()))["grid"]
    assert len(g["columns"]) >= 4 and g["longest_span_m"] > 0 and g["items"]


def test_review_counts_add_up():
    r = review(build_model(brief()), far_max=0.01)
    assert r["counts"]["fail"] >= 1 and "advisory" in r["disclaimer"].lower()


def test_estimate_defaults_unchanged_and_options_move_rates():
    m = build_model(brief())
    base = estimate(m)
    assert base["rates"] == DEFAULT_RATES and base["options"]["selected"] == dict(finish="standard", concrete="M20", masonry="brick", region="standard")
    prem = estimate(m, finish="premium", region="metro")
    assert prem["rates"]["flooring"] == pytest.approx(DEFAULT_RATES["flooring"] * 1.8 * 1.15, abs=0.01)
    assert prem["subtotal_inr"] > base["subtotal_inr"] > 0
    assert base["cost_per_sqft_inr"] == pytest.approx(base["subtotal_inr"] / base["built_up_sqft"], abs=1)
    assert estimate(m, finish="nonsense")["options"]["selected"]["finish"] == "standard"


def test_review_endpoint_isolation_and_validation(client, auth):
    from conftest import make_user, new_project
    from test_acceptance_2_3 import make_project
    empty = new_project(client, auth, "blank")
    r = client.get(f"/api/projects/{empty}/review", headers=auth)
    assert r.status_code == 404 and r.json()["error"]["next_actions"]            # no drawing yet
    pid = make_project(client, auth, views=None)
    d = client.get(f"/api/projects/{pid}/review", params=dict(far=1.5, coverage=60, height=12), headers=auth).json()
    assert d["planning"]["measured"]["far"] > 0 and d["vastu"]["score"] is not None and d["grid"]["columns"]
    assert {"fail", "warn", "ok", "info"} == set(d["counts"])
    assert client.get(f"/api/projects/{pid}/review", params=dict(coverage=500), headers=auth).status_code == 422
    assert client.get(f"/api/projects/{pid}/review", headers=make_user(client, "Ravi")).status_code == 404
    e = client.get(f"/api/projects/{pid}/estimate", params=dict(finish="premium", region="metro"), headers=auth).json()
    assert e["options"]["selected"]["finish"] == "premium" and e["cost_per_sqft_inr"] > 0
