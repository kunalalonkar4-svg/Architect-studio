"""Acceptance 1: Hinglish prompt, no attachment -> brief, relevant follow-up, dimensioned plan preview + real vector PDF."""
import io
import pymupdf
from conftest import chat, new_project, run_jobs

HINGLISH = ("30 by 50 feet ka east-facing plot hai. Ground floor par 2 bedrooms, open kitchen, parking aur staircase chahiye. "
            "First floor future mein add karenge.")


def test_hinglish_to_plan_and_pdf(client, auth):
    pid = new_project(client, auth, "Sharma ghar")
    txt, events, _ = chat(client, auth, pid, HINGLISH)
    brief = next(e for e in events if e["type"] == "brief")["brief"]
    assert round(brief["plot_frontage_mm"]) == 9144 and round(brief["plot_depth_mm"]) == 15240
    assert brief["road_side"] == "e" and brief["bedrooms"] == 2 and brief["kitchen_type"] == "open"
    assert brief["parking"] is True and brief["future_levels"] == ["First Floor"]
    clar = next(e for e in events if e["type"] == "clarification")
    assert any(q["id"] == "setbacks" for q in clar["questions"])            # relevant follow-up
    assert "Aapke brief" in txt                                              # replies in Hinglish
    assert client.get(f"/api/projects/{pid}", headers=auth).json()["current"] is None   # nothing drawn without the needed input

    txt, events, _ = chat(client, auth, pid, "front 3 m, rear 1.5 m, side 0 rakho")
    rev_ev = next(e for e in events if e["type"] == "revision")
    assert rev_ev["number"] == 1
    assert run_jobs() >= 1
    d = client.get(f"/api/projects/{pid}", headers=auth).json()
    cur = d["current"]
    assert cur["render_status"] == "done"
    sheet = cur["sheets"][0]
    assert sheet["number"] == "A-102" and sheet["ready"]
    # dimensioned preview (PNG + SVG) and real vector PDF
    png = client.get(f"/api/artifacts/{sheet['artifacts']['png']}/file", headers=auth)
    assert png.status_code == 200 and png.content[:4] == b"\x89PNG"
    svg = client.get(f"/api/artifacts/{sheet['artifacts']['svg']}/file", headers=auth).text
    assert "10740" in svg and "9144" in svg                                   # overall dimensions on the plan
    pdfb = client.get(f"/api/artifacts/{sheet['artifacts']['pdf']}/file", headers=auth).content
    doc = pymupdf.open(stream=pdfb, filetype="pdf")
    page = doc[0]
    assert abs(page.rect.width / 72 * 25.4 - 420) < 0.3 and abs(page.rect.height / 72 * 25.4 - 297) < 0.3   # A3 exact
    assert len(page.get_drawings()) > 200                                      # vector paths, not an image
    assert not page.get_images()
    text = page.get_text()
    assert "BEDROOM 1" in text and "KITCHEN" in text and "10740" in text and "Actual Size" in text
    # assumptions: setbacks supplied by the user are not labelled as assumed
    ids = [a["id"] for a in cur["model_summary"]["assumptions"] if a["kind"] == "assumed"]
    assert ids == ["dims_orientation"]          # only the plot-orientation assumption (30 ft taken along the road) is flagged


def test_proceed_with_assumptions_is_labelled(client, auth):
    pid = new_project(client, auth)
    chat(client, auth, pid, HINGLISH)
    _, events, _ = chat(client, auth, pid, "assumptions ke saath aage badho")
    assert any(e["type"] == "revision" for e in events)
    run_jobs()
    cur = client.get(f"/api/projects/{pid}", headers=auth).json()["current"]
    assumed = [a["text"] for a in cur["model_summary"]["assumptions"] if a["kind"] == "assumed"]
    sb = [a for a in assumed if 'open space' in a]
    assert len(sb) == 4 and all("assumed for concept only" in t for t in sb)
    assert any(i["code"] == "assumed_setback" for i in cur["validation"])
