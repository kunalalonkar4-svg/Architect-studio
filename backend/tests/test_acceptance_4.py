"""Acceptance 4: ambiguous dimension, impossible layout, sheet overflow, unavailable provider, failed render.
Each must show a clear next action and preserve existing project work."""
import json

import pytest
from conftest import chat, make_user, new_project, run_jobs
from test_acceptance_2_3 import HINGLISH, cur, make_project

from app import jobs
from app.ai import provider as prov


def revcount(client, auth, pid):
    return len(cur(client, auth, pid)["revisions"])


def test_ambiguous_dimension_asks_for_unit_and_stores_nothing(client, auth):
    pid = new_project(client, auth)
    txt, events, _ = chat(client, auth, pid, "30 by 50 ka east facing plot hai, 2 bedrooms")
    clar = [e for e in events if e["type"] == "clarification"]
    assert clar and any("unit" in q["id"] or "feet" in q["question"].lower() for e in clar for q in e["questions"])
    d = cur(client, auth, pid)
    assert d["brief"]["plot_frontage_mm"] is None and d["brief"]["plot_depth_mm"] is None      # never guessed
    assert d["current"] is None
    # the server also refuses an unspecified unit through the plain brief API
    r = client.put(f"/api/projects/{pid}/brief", json=dict(plot_frontage=dict(value=30, unit="unspecified"), plot_depth=dict(value=50, unit="unspecified")), headers=auth)
    assert r.json()["events"][-1]["type"] == "clarification"
    # answering with the unit fixes it
    chat(client, auth, pid, "30 by 50 feet")
    assert round(cur(client, auth, pid)["brief"]["plot_frontage_mm"]) == 9144


def test_impossible_layout_new_plot_and_edit_preserve_work(client, auth):
    pid = new_project(client, auth, "Tiny")
    chat(client, auth, pid, "20 by 30 feet ka south-facing plot hai. 2 bedrooms, parking, staircase chahiye. front 3 m, rear 1.5 m, side 0")
    d = cur(client, auth, pid)
    assert d["current"] is None
    last = d["messages"][-1]
    err = [e for e in last["events"] if e["type"] == "error"]
    assert err and err[0]["code"] == "impossible_layout" and err[0]["next_actions"]
    assert any("width" in r.lower() or "depth" in r.lower() for r in err[0]["detail"]["reasons"])

    pid2 = make_project(client, auth, views=None)
    before = revcount(client, auth, pid2)
    _, events, _ = chat(client, auth, pid2, "kitchen width 1000 mm karo")
    e = [x for x in events if x["type"] == "error"]
    assert e and e[0]["code"] == "impossible_layout" and "1900" in e[0]["message"] and e[0]["next_actions"]
    _, events, _ = chat(client, auth, pid2, "make it 7 bedroom")
    e = [x for x in events if x["type"] == "error"]
    assert e and "supported" in e[0]["message"]
    d = cur(client, auth, pid2)
    assert len(d["revisions"]) == before and d["current"]["number"] == 1 and not d["proposals"]


def test_sheet_overflow_gives_choices_and_keeps_revision(client, auth):
    pid = make_project(client, auth, views=None)
    d = cur(client, auth, pid)
    sid = d["current"]["sheets"][0]["id"]
    r = client.patch(f"/api/projects/{pid}/sheets/{sid}", json=dict(paper="A4", scale=50), headers=auth)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "sheet_overflow" and err["detail"]["needed_mm"][0] > err["detail"]["available_mm"][0] - 1 or err["detail"]["needed_mm"][1] > err["detail"]["available_mm"][1]
    kinds = {s["kind"] for s in err["detail"]["suggestions"]}
    assert "paper" in kinds and "scale" in kinds
    assert revcount(client, auth, pid) == 1
    # export at the same impossible choice is refused before a job exists
    r = client.post(f"/api/projects/{pid}/exports", json=dict(format="pdf", sheet_ids=[sid], paper="A4", scale=50), headers=auth)
    assert r.status_code == 422 and r.json()["error"]["code"] == "sheet_overflow"
    assert not [j for j in cur(client, auth, pid)["jobs"] if j["kind"] == "export"]
    # suggested larger scale works
    ok = client.patch(f"/api/projects/{pid}/sheets/{sid}", json=dict(paper="A4", scale=100), headers=auth)
    assert ok.status_code == 200
    run_jobs()
    assert cur(client, auth, pid)["current"]["render_status"] == "done"
    # explicit request through chat also explains the limit
    _, events, _ = chat(client, auth, pid, "export pdf A4 1:20")
    assert any(e["type"] == "error" and e["code"] == "sheet_overflow" for e in events)


class DownProvider:
    name, live = "anthropic", True
    def stream_turn(self, *a, **k):
        raise prov.ProviderError("unavailable", "Could not reach the AI provider (network or timeout).", True, ["Retry", "Your project and drawings are unchanged"])
        yield


def test_provider_unavailable_preserves_work_and_retry(client, auth, monkeypatch):
    pid = make_project(client, auth, views=None)
    before = cur(client, auth, pid)
    from app.ai import orchestrator
    real = orchestrator.get_provider
    monkeypatch.setattr(orchestrator, "get_provider", lambda: DownProvider())
    _, events, raw = chat(client, auth, pid, "elevation bhi do")
    err = [e for e in raw if e["type"] == "error"]
    assert err and err[0]["code"] == "unavailable" and err[0]["retriable"] and err[0]["next_actions"]
    d = cur(client, auth, pid)
    assert d["current"]["id"] == before["current"]["id"] and len(d["revisions"]) == len(before["revisions"])
    assert d["messages"][-1]["status"] == "error"
    # the drawing remains viewable while the provider is down
    assert client.get(f"/api/artifacts/{d['current']['sheets'][0]['artifacts']['png']}/file", headers=auth).status_code == 200
    # provider comes back: retry the same message (no duplicate user bubble)
    monkeypatch.setattr(orchestrator, "get_provider", real)
    n_user = len([m for m in d["messages"] if m["role"] == "user"])
    chat(client, auth, pid, "elevation bhi do", retry_of=d["messages"][-1]["id"])
    run_jobs()
    d2 = cur(client, auth, pid)
    assert len([m for m in d2["messages"] if m["role"] == "user"]) == n_user
    assert d2["current"]["number"] == 2 and any(s["kind"] == "elevations" for s in d2["current"]["sheets"])


def test_real_anthropic_provider_unreachable_maps_to_clear_error(client, auth, monkeypatch):
    """Exercises the real AnthropicProvider code path against a closed port (no key needed)."""
    import anthropic
    from app.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test-not-real")
    monkeypatch.setattr(settings, "anthropic_model", "claude-sonnet-5-5")
    monkeypatch.setattr(settings, "ai_provider", "auto")
    monkeypatch.setattr(settings, "ai_max_retries", 0)
    monkeypatch.setattr(settings, "ai_timeout_s", 2)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:9")
    prov._provider_cache.clear()
    pid = new_project(client, auth)
    try:
        _, _, raw = chat(client, auth, pid, "hello")
    finally:
        prov._provider_cache.clear()
    err = [e for e in raw if e["type"] == "error"]
    assert err and err[0]["code"] == "unavailable" and err[0]["retriable"]
    assert "sk-test-not-real" not in json.dumps(raw)
    assert cur(client, auth, pid)["current"] is None


def test_missing_key_or_model_is_explicit(client, auth, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-x")
    monkeypatch.setattr(settings, "anthropic_model", "")
    monkeypatch.setattr(settings, "ai_provider", "auto")
    prov._provider_cache.clear()
    pid = new_project(client, auth)
    try:
        _, _, raw = chat(client, auth, pid, "hello")
    finally:
        prov._provider_cache.clear()
    err = [e for e in raw if e["type"] == "error"]
    assert err and err[0]["code"] == "no_model" and "ANTHROPIC_MODEL" in err[0]["next_actions"][0]


def test_failed_render_keeps_last_good_and_retry(client, auth):
    pid = make_project(client, auth, views=None)
    good = cur(client, auth, pid)["current"]
    jobs.RENDER_FAULT.add("A-102")
    _, events, _ = chat(client, auth, pid, "window W2 ko 1800 mm wide karo")
    pr = cur(client, auth, pid)["proposals"][0]
    client.post(f"/api/proposals/{pr['id']}/confirm", json={}, headers=auth)
    run_jobs()
    d = cur(client, auth, pid)
    assert d["current"]["render_status"] == "failed" and d["current"]["number"] == 2
    assert d["last_good"]["id"] == good["id"] and d["last_good"]["sheets"][0]["ready"]          # previous drawing still available
    j = [x for x in d["jobs"] if x["kind"] == "render" and x["state"] == "failed"][0]
    assert "simulated render failure" in j["error"] and j["error_detail"]["next_actions"]
    jobs.RENDER_FAULT.clear()
    r = client.post(f"/api/jobs/{j['id']}/retry", headers=auth)
    assert r.status_code == 200
    run_jobs()
    d = cur(client, auth, pid)
    assert d["current"]["render_status"] == "done" and d["current"]["sheets"][0]["ready"]
    assert len([x for x in d["jobs"] if x["kind"] == "render" and x["revision_id"] == d["current"]["id"]]) == 1   # retry reused the job, no duplicate
