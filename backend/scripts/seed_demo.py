"""Create (or refresh) a working demo project: a 30 x 50 ft east-facing plot, 2 bedrooms, full drawing set.

    python -m scripts.seed_demo            # uses DATABASE_URL / STORAGE_DIR from the environment
Demo login:  demo@example.com / demo-password-123
Works without an Anthropic key: the brief and generation use the same validated server operations the AI calls.
"""
import sys

sys.path.insert(0, ".")
from fastapi.testclient import TestClient  # noqa: E402

from app import jobs  # noqa: E402
from app.main import app  # noqa: E402

EMAIL, PW = "demo@example.com", "demo-password-123"


def main():
    c = TestClient(app)
    r = c.post("/api/auth/register", json=dict(email=EMAIL, password=PW, display_name="Demo Architect"))
    if r.status_code == 409:
        r = c.post("/api/auth/login", json=dict(email=EMAIL, password=PW))
    h = {"Authorization": "Bearer " + r.json()["token"]}
    c.patch("/api/auth/me", json=dict(firm_name="Demo Design Studio", firm_line="12 Example Road, Pune"), headers=h)
    for p in c.get("/api/projects?q=Demo%20residence", headers=h).json()["projects"]:
        return print("Demo project already exists:", p["id"])
    pid = c.post("/api/projects", json=dict(name="Demo residence – 30×50 ft east-facing", client="Mr. & Mrs. Sharma", address="Plot 14, Example Nagar"), headers=h).json()["project"]["id"]
    L = lambda v, u: dict(value=v, unit=u)
    ok = c.put(f"/api/projects/{pid}/brief", headers=h, json=dict(
        plot_frontage=L(30, "ft"), plot_depth=L(50, "ft"), road_side="east", bedrooms=2, kitchen_type="open", parking=True,
        setback_front=L(3, "m"), setback_rear=L(1.5, "m"), setback_left=L(0, "m"), setback_right=L(0, "m"),
        requested_views=["site", "plan", "roof", "elevations", "section", "schedules", "index"]))
    assert ok.status_code == 200, ok.text
    g = c.post(f"/api/projects/{pid}/generate", headers=h, json=dict(use_assumptions=False))
    assert g.status_code == 200, g.text
    jobs.run_pending_once()
    cur = c.get(f"/api/projects/{pid}", headers=h).json()["current"]
    print(f"Demo project ready: {cur['summary']} · render {cur['render_status']} · sheets: {[s['number'] for s in cur['sheets']]}")
    print(f"Login: {EMAIL} / {PW}")


if __name__ == "__main__":
    main()
