from conftest import make_user
from test_acceptance_2_3 import make_project


def _share(client, auth, pid, **kw):
    r = client.post(f"/api/projects/{pid}/shares", json=kw, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()["share"]


def test_share_link_is_public_readonly_and_revocable(client, auth):
    pid = make_project(client, auth, views=None)
    s = _share(client, auth, pid)
    tok = s["token"]
    assert len(tok) >= 24
    r = client.get(f"/api/public/share/{tok}")          # no auth header
    assert r.status_code == 200
    d = r.json()
    assert d["project"]["revision"] == s["revision"] and "Not reviewed" in d["notice"]
    assert "address" not in str(d["project"]).lower() and "client" not in d["project"]
    ready = [x for x in d["sheets"] if x["ready"]]
    assert ready
    svg = client.get(f"/api/public/share/{tok}/sheet/{ready[0]['id']}.svg")
    assert svg.status_code == 200 and svg.headers["content-type"].startswith("image/svg")
    assert client.get(f"/api/public/share/{tok}/model3d").json()["walls"]
    assert client.get("/api/public/share/not-a-token").status_code == 404
    # revoke
    assert client.delete(f"/api/projects/{pid}/shares/{s['id']}", headers=auth).json()["share"]["active"] is False
    assert client.get(f"/api/public/share/{tok}").status_code == 404
    assert client.get(f"/api/public/share/{tok}/model3d").status_code == 404


def test_comments_from_guests_and_owner(client, auth):
    pid = make_project(client, auth, views=None)
    s = _share(client, auth, pid)
    tok = s["token"]
    r = client.post(f"/api/public/share/{tok}/comments", json=dict(body="Is the kitchen window too small?", author="Uncle Raj"))
    assert r.status_code == 201
    assert client.post(f"/api/public/share/{tok}/comments", json=dict(body="   ")).status_code == 422
    assert client.post(f"/api/public/share/{tok}/comments", json=dict(body="x" * 2001)).status_code == 422
    cs = client.get(f"/api/projects/{pid}/comments", headers=auth).json()["comments"]
    assert [c["author"] for c in cs] == ["Uncle Raj"]
    cid = cs[0]["id"]
    assert client.post(f"/api/projects/{pid}/comments", json=dict(body="Will check."), headers=auth).status_code == 201
    pub = client.get(f"/api/public/share/{tok}").json()["comments"]
    assert [c["from_owner"] for c in pub] == [False, True]
    assert client.post(f"/api/projects/{pid}/comments/{cid}/resolve", headers=auth).json()["comment"]["resolved"] is True
    # comments off
    s2 = _share(client, auth, pid, allow_comments=False)
    assert client.post(f"/api/public/share/{s2['token']}/comments", json=dict(body="hi")).status_code == 403


def test_sharing_and_comments_are_private_to_the_owner(client, auth):
    pid = make_project(client, auth, views=None)
    s = _share(client, auth, pid)
    other = make_user(client, "Mallory")
    assert client.post(f"/api/projects/{pid}/shares", json={}, headers=other).status_code == 404
    assert client.get(f"/api/projects/{pid}/shares", headers=other).status_code == 404
    assert client.delete(f"/api/projects/{pid}/shares/{s['id']}", headers=other).status_code == 404
    assert client.get(f"/api/projects/{pid}/comments", headers=other).status_code == 404
    assert client.get(f"/api/projects/{pid}/review-requests", headers=other).status_code == 404
    assert client.get(f"/api/public/share/{s['token']}").status_code == 200   # the link itself still works


def test_share_is_pinned_to_the_shared_revision(client, auth):
    pid = make_project(client, auth, views=None)
    s = _share(client, auth, pid)
    d = client.get(f"/api/public/share/{s['token']}").json()
    assert d["project"]["revision"] == s["revision"]


def test_review_request_is_an_owner_record_not_an_approval(client, auth):
    pid = make_project(client, auth, views=None)
    r = client.post(f"/api/projects/{pid}/review-requests", json=dict(kind="structural", reviewer_name="Er. Rao", note="Check the 2nd floor allowance"), headers=auth)
    assert r.status_code == 201
    body = r.json()
    assert body["request"]["status"] == "requested" and "does not assign" in body["info"]
    assert client.post(f"/api/projects/{pid}/review-requests", json=dict(kind="wizard"), headers=auth).status_code == 422
    rid = body["request"]["id"]
    assert client.patch(f"/api/projects/{pid}/review-requests/{rid}", json=dict(status="reviewed", outcome_note="OK with changes"), headers=auth).json()["request"]["status"] == "reviewed"
    lst = client.get(f"/api/projects/{pid}/review-requests", headers=auth).json()["requests"]
    assert len(lst) == 1
    # a reviewed record must not flip the project to an approved state
    assert client.get(f"/api/projects/{pid}", headers=auth).json()["project"]["review_status"] == "concept_unreviewed"


def test_samples_need_no_sign_in(client):
    lst = client.get("/api/public/samples").json()
    assert len(lst["samples"]) == 3 and "example" in lst["note"].lower()
    for s in lst["samples"]:
        d = client.get(f"/api/public/samples/{s['id']}")
        assert d.status_code == 200, d.text
        j = d.json()
        assert j["rooms"] and j["estimate"]["subtotal_inr"] > 0 and "planning" in j["review"]
        assert client.get(j["plan_url"]).headers["content-type"].startswith("image/svg")
        assert client.get(f"/api/public/samples/{s['id']}/model3d").json()["walls"]
    assert client.get("/api/public/samples/nope").status_code == 404
