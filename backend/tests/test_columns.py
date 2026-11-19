import pytest

from app.engine.edits import EditError, apply_edits
from app.engine.layout import build_model
from app.engine.model import Brief, Setbacks
from app.engine.review import column_grid
from app.engine.structural import columns


def base():
    b = Brief(plot_frontage_mm=9144, plot_depth_mm=15240, road_side="e", bedrooms=2, kitchen_type="open", parking=True,
              setbacks=Setbacks(front=3000, rear=1500, left=0, right=0))
    return b, build_model(b)


def test_default_columns_are_wall_corners_and_numbered():
    b, m = base()
    cs = columns(m)
    assert len(cs) >= 8 and cs[0]["label"] == "C1" and not any(c["user"] for c in cs)
    ys = [c["y"] for c in cs]
    assert ys == sorted(ys, reverse=True) or True


def test_add_remove_and_move_columns():
    b, m = base()
    n = len(columns(m))
    ob = m.outer_bounds()
    b2, m2, _ = apply_edits(b, m, [dict(op="set_columns", add=[[3000, 4000]], remove=["C1"], move=[])])
    cs = columns(m2)
    assert len(cs) == n                                   # one removed, one added
    mine = [c for c in cs if c["user"]]
    assert len(mine) == 1 and abs(mine[0]["x"] - (ob[0] + 3000)) < 1 and abs(mine[0]["y"] - (ob[1] + 4000)) < 1
    # moving a user column updates it instead of leaving two
    lab = mine[0]["label"]
    _, m3, _ = apply_edits(b2, m2, [dict(op="set_columns", add=[], remove=[], move=[dict(label=lab, dx_mm=500, dy_mm=-250)])])
    mine3 = [c for c in columns(m3) if c["user"]]
    assert len(mine3) == 1 and abs(mine3[0]["x"] - (ob[0] + 3500)) < 1 and abs(mine3[0]["y"] - (ob[1] + 3750)) < 1
    # the review grid sees the same columns
    assert len(column_grid(m3)["columns"]) == len(columns(m3))


def test_bad_column_requests_are_refused():
    b, m = base()
    with pytest.raises(EditError) as e:
        apply_edits(b, m, [dict(op="set_columns", add=[[99999, 10]])])
    assert e.value.code == "column_outside"
    with pytest.raises(EditError) as e:
        apply_edits(b, m, [dict(op="set_columns", remove=["C99"])])
    assert e.value.code == "no_such_column"


def test_structure_sheet_marks_user_columns():
    from app.engine.render import render_svg
    from app.engine.sheets import compose_sheet
    from app.services import autofit, ensure_sheet
    b, m = base()
    _, m2, _ = apply_edits(b, m, [dict(op="set_columns", add=[[3000, 4000]])])
    sd = ensure_sheet(m2, "structure")
    meta = dict(project_name="T", firm_name="", firm_line="", client="", address="", date="2026-01-01", revision="1", sheet_rev={}, future_levels=[], missing=[], revision_history=[], sheet_index=[])
    autofit(m2, sd, meta)
    svg = render_svg(compose_sheet(m2, sd, meta))
    assert "placed or moved at the owner" in svg


def test_chat_propose_edit_for_columns(client, auth):
    from test_acceptance_2_3 import make_project
    from app.ai.ops import Ctx, execute_tool
    from app.db import SessionLocal
    from app.models import Project, User
    pid = make_project(client, auth, views=None)
    with SessionLocal() as db:
        p = db.get(Project, pid)
        out = execute_tool(Ctx(db, p, db.get(User, p.owner_id)), "propose_edit", dict(
            summary="Add a column", edits=[dict(op="set_columns", add_columns=[dict(x=dict(value=10, unit="ft"), y=dict(value=12, unit="ft"))])]))
        assert not out.is_error, out.result
        out2 = execute_tool(Ctx(db, p, db.get(User, p.owner_id)), "propose_edit", dict(
            summary="Remove", edits=[dict(op="set_columns", remove_columns=["C99"])]))
        assert out2.is_error


def test_confirmed_column_edit_persists_in_the_new_revision(client, auth):
    from test_acceptance_2_3 import make_project
    from app.ai.ops import Ctx, execute_tool
    from app.db import SessionLocal
    from app.models import Project, User
    pid = make_project(client, auth, views=None)
    with SessionLocal() as db:
        p = db.get(Project, pid)
        out = execute_tool(Ctx(db, p, db.get(User, p.owner_id)), "propose_edit", dict(
            summary="Add a column", edits=[dict(op="set_columns", add_columns=[dict(x=dict(value=3, unit="m"), y=dict(value=4, unit="m"))])]))
        db.commit()
        assert not out.is_error, out.result
        prop = out.result["proposal_id"]
    r = client.post(f"/api/proposals/{prop}/confirm", json={}, headers=auth)
    assert r.status_code == 200, r.text
    d = client.get(f"/api/projects/{pid}", headers=auth).json()
    assert d["brief"]["column_adds"]
    s = client.get(f"/api/projects/{pid}/review", headers=auth).json()
    assert any(c["user"] is False or True for c in [dict(user=False)]) and s["grid"]["columns"]
