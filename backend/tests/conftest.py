import os
import shutil
import sys
import tempfile
import uuid

os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://studio:studio@localhost:5432/studio_test")
os.environ["AI_PROVIDER"] = "mock"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["RUN_WORKER_IN_API"] = "0"
_tmp = tempfile.mkdtemp(prefix="studio-test-")
os.environ["STORAGE_DIR"] = _tmp
os.environ["FRONTEND_DIR"] = "/nonexistent"
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import Base, engine
from app.main import app
from app import jobs


@pytest.fixture(scope="session", autouse=True)
def _db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    shutil.rmtree(_tmp, ignore_errors=True)


@pytest.fixture()
def client():
    jobs.RENDER_FAULT.clear()
    with TestClient(app) as c:
        yield c


def make_user(client, name="Asha"):
    email = f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com"
    r = client.post("/api/auth/register", json=dict(email=email, password="correct horse battery", display_name=name))
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture()
def auth(client):
    return make_user(client)


def chat(client, auth, pid, text_, **kw):
    """Consume the SSE stream and return (full_text, events, raw_events)."""
    with client.stream("POST", f"/api/projects/{pid}/chat", json=dict(content=text_, **kw), headers=auth) as r:
        assert r.status_code == 200, r.read()
        evs = []
        for line in r.iter_lines():
            if line.startswith("data: "):
                evs.append(json.loads(line[6:]))
    txt = "".join(e["delta"] for e in evs if e["type"] == "text")
    return txt, [e["event"] for e in evs if e["type"] == "event"], evs


def new_project(client, auth, name="Test house"):
    return client.post("/api/projects", json=dict(name=name), headers=auth).json()["project"]["id"]


def run_jobs():
    return jobs.run_pending_once()
