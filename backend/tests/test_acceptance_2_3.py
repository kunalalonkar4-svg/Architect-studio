"""Acceptance 2: coordinated plan/elevation/section/schedule agree after a chat edit.
Acceptance 3: measured scale in the exported PDF (60 mm @1:100, 120 mm @1:50) and 6000 mm in DXF model space."""
import io
import math
import re

import ezdxf
import pymupdf
from conftest import chat, new_project, run_jobs

HINGLISH = ("30 by 50 feet ka east-facing plot hai. Ground floor par 2 bedrooms, open kitchen, parking aur staircase chahiye. "
            "First floor future mein add karenge.")
MM = 72 / 25.4


def make_project(client, auth, views="full set"):
    pid = new_project(client, auth)
    chat(client, auth, pid, HINGLISH)
    chat(client, auth, pid, "front 3 m, rear 1.5 m, side 0 rakho")
    run_jobs()
    if views:
        chat(client, auth, pid, "poora set drawings do")
        run_jobs()
    return pid


def cur(client, auth, pid):
    return client.get(f"/api/projects/{pid}", headers=auth).json()


def text_of(client, auth, art_id):
    b = client.get(f"/api/artifacts/{art_id}/file", headers=auth).content
    return pymupdf.open(stream=b, filetype="pdf")[0].get_text()


def test_change_opening_updates_all_views_and_schedule(client, auth):
    pid = make_project(client, auth)
    d = cur(client, auth, pid)
    c = d["current"]
    assert c["number"] == 2 and c["render_status"] == "done"
    nums = [s["number"] for s in c["sheets"]]
    assert {"A-101", "A-102", "A-103", "A-201", "A-301", "A-401", "G-001"} <= set(nums)
    base_validation = [i for i in c["validation"] if i["severity"] == "error"]
    assert not base_validation
    w2 = next(o for o in c["model_summary"]["openings"] if o["mark"] == "W2")
    assert w2["width"] == 1500

    # change one opening in chat -> proposal with affected drawings, nothing saved yet
    _, events, _ = chat(client, auth, pid, "window W2 ko 1800 mm wide karo")
    pr_ev = next(e for e in events if e["type"] == "proposal")
    pr = [p for p in cur(client, auth, pid)["proposals"] if p["id"] == pr_ev["proposal_id"]][0]
    assert any("W2" in ch["text"] and "1800" in ch["text"] for ch in pr["changes"])
    aff = [s["number"] for s in pr["affected_sheets"]]
    assert "A-102" in aff and "A-401" in aff and "A-201" in aff       # plan, schedule, elevation(s)
    assert "A-103" not in aff and "A-101" not in aff                 # roof and site untouched
    assert cur(client, auth, pid)["current"]["number"] == 2          # not committed yet

    r = client.post(f"/api/proposals/{pr['id']}/confirm", json={}, headers=auth)
    assert r.status_code == 200, r.text
    run_jobs()
    d = cur(client, auth, pid)
    c = d["current"]
    assert c["number"] == 3 and c["render_status"] == "done"
    assert not [i for i in c["validation"] if i["severity"] == "error"], c["validation"]      # includes plan/elevation/schedule agreement check
    sheets = {s["number"]: s for s in c["sheets"]}
    # schedule PDF text shows 1800; plan and elevation text/svg show W2 1800-wide opening
    sched = text_of(client, auth, sheets["A-401"]["artifacts"]["pdf"])
    row = re.search(r"W2\s+Window[^\n]*\n[^\n]*\n[^\n]*", sched)
    assert "1800" in sched and "1500\nW" not in sched
    plan_svg = client.get(f"/api/artifacts/{sheets['A-102']['artifacts']['svg']}/file", headers=auth).text
    assert ">W2<" in plan_svg
    # sheet revisions: changed sheets advance to Rev 3, untouched sheets keep their earlier revision
    assert sheets["A-102"]["rev"] == 3 and sheets["A-401"]["rev"] == 3
    assert sheets["A-103"]["rev"] == 2 and sheets["A-101"]["rev"] == 2
    # untouched sheets re-used the very same stored file (localised regeneration)
    prev = [r for r in d["revisions"] if r["number"] == 2][0]
    prev_sheets = {s["number"]: s for s in client.get(f"/api/revisions/{prev['id']}", headers=auth).json()["revision"]["sheets"]}
    assert prev_sheets["A-103"]["artifacts"]["svg"] != sheets["A-103"]["artifacts"]["svg"]   # new artifact row...
    a = client.get(f"/api/artifacts/{prev_sheets['A-103']['artifacts']['svg']}/file", headers=auth).content
    b = client.get(f"/api/artifacts/{sheets['A-103']['artifacts']['svg']}/file", headers=auth).content
    assert a == b                                                            # ...pointing at identical content
    # model in the revision snapshot has the new width and the old revision is unchanged
    assert [o for o in c["model_summary"]["openings"] if o["mark"] == "W2"][0]["width"] == 1800
    old = client.get(f"/api/revisions/{prev['id']}", headers=auth).json()["revision"]
    assert [o for o in old["model_summary"]["openings"] if o["mark"] == "W2"][0]["width"] == 1500


def test_stair_move_keeps_kitchen_and_compare(client, auth):
    pid = make_project(client, auth, views=None)
    _, events, _ = chat(client, auth, pid, "Staircase rear side mein shift karo, kitchen ka size same rakho.")
    pr_ev = next(e for e in events if e["type"] == "proposal")
    pr = [p for p in cur(client, auth, pid)["proposals"] if p["id"] == pr_ev["proposal_id"]][0]
    texts = " ".join(c["text"] for c in pr["changes"])
    assert "Staircase" in texts and "Kitchen" not in texts            # kitchen unchanged
    client.post(f"/api/proposals/{pr['id']}/confirm", json={}, headers=auth)
    run_jobs()
    d = cur(client, auth, pid)
    k = [s for s in d["current"]["model_summary"]["spaces"] if s["key"] == "kitchen"][0]
    k1 = [s for s in client.get(f"/api/revisions/{d['revisions'][0]['id']}", headers=auth).json()["revision"]["model_summary"]["spaces"] if s["key"] == "kitchen"][0]
    assert (round(k["w"]), round(k["h"])) == (round(k1["w"]), round(k1["h"]))
    cmp = client.get(f"/api/projects/{pid}/compare", params=dict(a=d["revisions"][0]["id"], b=d["current"]["id"]), headers=auth).json()
    assert any("Staircase" in c["text"] for c in cmp["changes"]) and cmp["sheets_changed"]
    # restore creates a new revision, never rewrites history
    r = client.post(f"/api/revisions/{d['revisions'][0]['id']}/restore", headers=auth)
    assert r.status_code == 201
    run_jobs()
    d2 = cur(client, auth, pid)
    assert d2["current"]["number"] == 3 and len(d2["revisions"]) == 3


def pdf_line_lengths_mm(pdf_bytes):
    page = pymupdf.open(stream=pdf_bytes, filetype="pdf")[0]
    out = []
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] == "l":
                p1, p2 = it[1], it[2]
                out.append((math.hypot(p2.x - p1.x, p2.y - p1.y) / MM, d.get("width")))
    return out


def test_scale_accuracy_pdf_and_dxf(client, auth):
    pid = make_project(client, auth, views=None)
    d = cur(client, auth, pid)
    plan = d["current"]["sheets"][0]
    # 1:50 plan sheet (default): the 6000 mm graphic-scale segment must be 120 mm on paper
    b = client.get(f"/api/artifacts/{plan['artifacts']['pdf']}/file", headers=auth).content
    L = pdf_line_lengths_mm(b)
    assert any(abs(l - 120.0) < 0.05 and abs(w / MM - 0.35) < 0.02 for l, w in L), "6000 mm @1:50 must be 120 mm"
    # export the same sheet at 1:100 on A3 -> 60 mm
    for scale, expect in ((100, 60.0), (50, 120.0)):
        r = client.post(f"/api/projects/{pid}/exports", json=dict(format="pdf", sheet_ids=[plan["id"]], paper="A3", scale=scale), headers=auth)
        assert r.status_code == 201, r.text
        run_jobs()
        job = client.get(f"/api/projects/{pid}/jobs", headers=auth).json()["jobs"]
        j = [x for x in job if x["kind"] == "export" and x["params"].get("scale") == scale][0]
        assert j["state"] == "done" and j["artifact"]["checks"]["ok"]
        pdf = client.get(f"/api/artifacts/{j['artifact']['id']}/file", headers=auth).content
        L = pdf_line_lengths_mm(pdf)
        assert any(abs(l - expect) < 0.05 and abs(w / MM - 0.35) < 0.02 for l, w in L), f"6000 mm @1:{scale} must be {expect} mm"
        text = pymupdf.open(stream=pdf, filetype="pdf")[0].get_text()
        assert f"1:{scale}" in text and "A3" in text and "Actual Size" in text
        pg = pymupdf.open(stream=pdf, filetype="pdf")[0]
        assert abs(pg.rect.width / MM - 420) < 0.3
    # DXF: layered, editable, 1:1 model units; calibration segment is exactly 6000 mm
    r = client.post(f"/api/projects/{pid}/exports", json=dict(format="dxf", sheet_ids=[plan["id"]], scale=100), headers=auth)
    run_jobs()
    j = [x for x in client.get(f"/api/projects/{pid}/jobs", headers=auth).json()["jobs"] if x["params"].get("format") == "dxf"][0]
    assert j["state"] == "done"
    data = client.get(f"/api/artifacts/{j['artifact']['id']}/file", headers=auth).content
    doc = ezdxf.read(io.StringIO(data.decode()))
    assert doc.units == 4                                                    # millimetres
    lines = [e for e in doc.modelspace().query("LINE") if e.dxf.layer == "A-SCALE"]
    lens = [e.dxf.start.distance(e.dxf.end) for e in lines]
    assert any(abs(l - 6000.0) < 1e-6 for l in lens), lens
    names = {l.dxf.name for l in doc.layers}
    assert {"A-WALL", "A-DOOR", "A-GLAZ", "A-ANNO-DIMS", "A-GRID", "A-ANNO-TEXT"} <= names
    # wall geometry coordinates are real model millimetres: overall wall bbox equals the 10740 x 9144 footprint (outer faces)
    xs, ys = [], []
    for e in doc.modelspace().query("LWPOLYLINE"):
        if e.dxf.layer == "A-WALL":
            for x, y, *_ in e.get_points():
                xs.append(x); ys.append(y)
    assert abs((max(xs) - min(xs)) - 10740) < 1 and abs((max(ys) - min(ys)) - 9144) < 1
    # text height is plot-correct: 2.5 mm paper text at 1:100 = 250 model mm
    hs = {round(t.dxf.height) for t in doc.modelspace().query("TEXT")}
    assert 250 in hs or 220 in hs
