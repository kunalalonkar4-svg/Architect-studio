from __future__ import annotations

import io
import json
import re
import shutil
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import storage
from ..ai import ops as aiops
from ..ai.orchestrator import run_turn
from ..ai.provider import ProviderError, provider_status
from ..ai.tools import ProposeEdit, UpdateBrief
from ..config import settings
from ..db import get_db
from ..engine.edits import diff_models
from ..engine.model import Brief, ProjectModel
from ..engine.sheets import SheetOverflow
from ..models import AIUsage, Artifact, Attachment, Job, Message, Project, Proposal, Revision, User, now
from ..security import current_user, hash_password, make_token, owned_project, verify_password
from ..services import (ServiceError, affected_sheets, autofit, create_revision, enqueue_export, enqueue_render, evaluate_edit, precheck_export,
                        sheet_meta, sheet_meta_for)

router = APIRouter(prefix="/api")


# ------------------------------------------------------------------ helpers
def svc_error(e: ServiceError):
    return JSONResponse(status_code=e.status, content=dict(error=e.as_dict()))


def user_json(u: User) -> dict:
    return dict(id=u.id, email=u.email, display_name=u.display_name, firm_name=u.firm_name, firm_line=u.firm_line, has_logo=bool(u.logo_key))


def project_summary(p: Project) -> dict:
    return dict(id=p.id, name=p.name, status=p.status, client=p.client, address=p.address, updated_at=p.updated_at.isoformat(),
                created_at=p.created_at.isoformat(), current_revision_id=p.current_revision_id, review_status=p.review_status)


def sheets_json(db: Session, rev: Revision) -> list[dict]:
    model = ProjectModel.model_validate(rev.model)
    arts = list(db.scalars(select(Artifact).where(Artifact.revision_id == rev.id, Artifact.purpose == "preview")))
    out = []
    for s in model.sheets:
        a = {x.kind: x.id for x in arts if x.sheet_id == s.id}
        out.append(dict(id=s.id, number=s.number, title=s.title, kind=s.kind, paper=s.paper, orientation=s.orientation, scale=s.scale,
                        rev=rev.sheet_revs.get(s.number, {}).get("rev", rev.number), artifacts=a, ready={"svg", "png", "pdf"} <= set(a)))
    return out


def revision_json(db: Session, rev: Revision, detail: bool = True) -> dict:
    d = dict(id=rev.id, number=rev.number, summary=rev.summary, changes=rev.changes, created_at=rev.created_at.isoformat(),
             render_status=rev.render_status, render_error=rev.render_error)
    if detail:
        model = ProjectModel.model_validate(rev.model)
        d.update(sheets=sheets_json(db, rev), validation=rev.validation, brief=rev.brief,
                 model_summary=dict(plot=model.plot, spaces=[dict(key=s.key, name=s.name, w=s.w, h=s.h) for s in model.spaces],
                                    openings=[dict(mark=o.mark, key=o.key, type=o.type, width=o.width, height=o.height, sill=o.sill, between=[o.from_space, o.to_space]) for o in model.openings],
                                    level_height=model.levels[0].height, stair=model.stairs[0].flight.model_dump() if model.stairs and model.stairs[0].flight else None,
                                    params=model.params.model_dump(), assumptions=[a.model_dump() for a in model.assumptions]))
    return d


def proposal_json(p: Proposal) -> dict:
    return dict(id=p.id, kind=p.kind, state=p.state, summary=p.summary, changes=p.changes, affected_sheets=p.affected_sheets, options=p.options,
                issues=p.issues, base_revision_id=p.base_revision_id, blocking=[i for i in p.issues if i["severity"] == "error"], created_at=p.created_at.isoformat())


def job_json(db: Session, j: Job) -> dict:
    d = dict(id=j.id, kind=j.kind, state=j.state, progress=j.progress, step=j.step, error=j.error, error_detail=j.error_detail,
             revision_id=j.revision_id, params={k: v for k, v in (j.params or {}).items() if k != "artifact_id"}, created_at=j.created_at.isoformat())
    aid = (j.params or {}).get("artifact_id")
    if aid:
        a = db.get(Artifact, aid)
        if a:
            d["artifact"] = dict(id=a.id, name=a.name, size=a.size, kind=a.kind, checks=a.meta.get("checks"))
    return d


def message_json(m: Message) -> dict:
    return dict(id=m.id, role=m.role, content=m.content, events=m.events, status=m.status, attachment_ids=m.attachment_ids, created_at=m.created_at.isoformat())


# ------------------------------------------------------------------ health / auth
@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return dict(ok=True, ai=provider_status(), db="ok")


class RegisterIn(BaseModel):
    email: str = Field(min_length=5, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(default="", max_length=200)


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/auth/register")
def register(b: RegisterIn, db: Session = Depends(get_db)):
    email = b.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists")
    u = User(email=email, password_hash=hash_password(b.password), display_name=b.display_name.strip() or email.split("@")[0])
    db.add(u); db.commit()
    return dict(token=make_token(u.id), user=user_json(u))


@router.post("/auth/login")
def login(b: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == b.email.strip().lower()))
    if not u or not verify_password(b.password, u.password_hash):
        raise HTTPException(401, "Email or password is incorrect")
    return dict(token=make_token(u.id), user=user_json(u))


@router.get("/auth/me")
def me(u: User = Depends(current_user)):
    return dict(user=user_json(u), ai=provider_status())


class ProfileIn(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=200)
    firm_name: Optional[str] = Field(default=None, max_length=200)
    firm_line: Optional[str] = Field(default=None, max_length=300)


@router.patch("/auth/me")
def update_me(b: ProfileIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    for k, v in b.model_dump(exclude_none=True).items():
        setattr(u, k, v.strip())
    db.commit()
    return dict(user=user_json(u))


MAGIC = {b"\x89PNG\r\n\x1a\n": "image/png", b"\xff\xd8\xff": "image/jpeg", b"%PDF-": "application/pdf"}


def sniff(data: bytes) -> str | None:
    for m, mime in MAGIC.items():
        if data.startswith(m):
            return mime
    try:
        data[:4000].decode("utf-8")
        return "text/plain"
    except UnicodeDecodeError:
        return None


@router.post("/auth/logo")
async def upload_logo(file: UploadFile = File(...), u: User = Depends(current_user), db: Session = Depends(get_db)):
    data = await file.read(1_000_001)
    if len(data) > 1_000_000:
        raise HTTPException(413, "Logo must be under 1 MB")
    mime = sniff(data)
    if mime not in ("image/png", "image/jpeg"):
        raise HTTPException(415, "Logo must be a PNG or JPEG image")
    key = f"u/{u.id}/logo"
    storage.put(key, data)
    u.logo_key, u.logo_mime = key, mime
    db.commit()
    return dict(user=user_json(u))


@router.delete("/auth/logo")
def delete_logo(u: User = Depends(current_user), db: Session = Depends(get_db)):
    if u.logo_key:
        storage.delete(u.logo_key)
    u.logo_key = u.logo_mime = None
    db.commit()
    return dict(user=user_json(u))


@router.get("/auth/logo")
def get_logo(u: User = Depends(current_user)):
    if not u.logo_key or not storage.exists(u.logo_key):
        raise HTTPException(404, "No logo")
    return Response(storage.get(u.logo_key), media_type=u.logo_mime or "image/png", headers={"X-Content-Type-Options": "nosniff"})


# ------------------------------------------------------------------ projects
class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    client: str = Field(default="", max_length=200)
    address: str = Field(default="", max_length=400)


class ProjectPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    client: Optional[str] = Field(default=None, max_length=200)
    address: Optional[str] = Field(default=None, max_length=400)
    review_status: Optional[str] = Field(default=None, pattern="^(concept_unreviewed|issued_for_review_by_owner)$")


@router.get("/projects")
def list_projects(q: str = "", status: str = "active", u: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Project).where(Project.owner_id == u.id).order_by(Project.updated_at.desc())
    if status in ("active", "archived"):
        stmt = stmt.where(Project.status == status)
    if q.strip():
        like = f"%{q.strip().replace('%', '').replace('_', '')}%"
        msg_hits = select(Message.project_id).where(Message.content.ilike(like))
        stmt = stmt.where(Project.name.ilike(like) | Project.client.ilike(like) | Project.address.ilike(like) | Project.id.in_(msg_hits))
    return dict(projects=[project_summary(p) for p in db.scalars(stmt)])


@router.post("/projects", status_code=201)
def create_project(b: ProjectIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = Project(owner_id=u.id, name=b.name.strip(), client=b.client.strip(), address=b.address.strip(), brief=Brief().model_dump())
    db.add(p); db.commit()
    return dict(project=project_summary(p))


def full_project(db: Session, p: Project) -> dict:
    msgs = list(db.scalars(select(Message).where(Message.project_id == p.id).order_by(Message.created_at)))
    revs = list(db.scalars(select(Revision).where(Revision.project_id == p.id).order_by(Revision.number)))
    cur = db.get(Revision, p.current_revision_id) if p.current_revision_id else None
    good = db.get(Revision, p.last_good_revision_id) if p.last_good_revision_id else None
    props = list(db.scalars(select(Proposal).where(Proposal.project_id == p.id, Proposal.state == "pending").order_by(Proposal.created_at)))
    jobs = list(db.scalars(select(Job).where(Job.project_id == p.id).order_by(Job.created_at.desc()).limit(15)))
    atts = list(db.scalars(select(Attachment).where(Attachment.project_id == p.id).order_by(Attachment.created_at)))
    brief = Brief.model_validate(p.brief or {})
    return dict(project=project_summary(p), brief=brief.model_dump(), missing=brief.missing(), messages=[message_json(m) for m in msgs],
                revisions=[revision_json(db, r, False) for r in revs], current=revision_json(db, cur) if cur else None,
                last_good=revision_json(db, good) if good and cur and good.id != cur.id else None,
                proposals=[proposal_json(x) for x in props], jobs=[job_json(db, j) for j in jobs],
                attachments=[dict(id=a.id, filename=a.filename, mime=a.mime, size=a.size) for a in atts], ai=provider_status(),
                use_assumptions=p.use_assumptions)


@router.get("/projects/{pid}")
def get_project(pid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    return full_project(db, owned_project(db, u, pid))


@router.patch("/projects/{pid}")
def patch_project(pid: str, b: ProjectPatch, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    for k, v in b.model_dump(exclude_none=True).items():
        setattr(p, k, v.strip() if isinstance(v, str) else v)
    p.updated_at = now()
    db.commit()
    return dict(project=project_summary(p))


@router.post("/projects/{pid}/archive")
def archive(pid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid); p.status = "archived"; db.commit()
    return dict(project=project_summary(p))


@router.post("/projects/{pid}/unarchive")
def unarchive(pid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid); p.status = "active"; db.commit()
    return dict(project=project_summary(p))


@router.post("/projects/{pid}/duplicate", status_code=201)
def duplicate(pid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    n = Project(owner_id=u.id, name=f"{p.name} (copy)", client=p.client, address=p.address, brief=p.brief, use_assumptions=p.use_assumptions)
    db.add(n); db.flush()
    cur = db.get(Revision, p.current_revision_id) if p.current_revision_id else None
    if cur:
        model, brief = ProjectModel.model_validate(cur.model), Brief.model_validate(cur.brief)
        create_revision(db, n, u, brief, model, f"Duplicated from '{p.name}' revision {cur.number}", allow_errors=True)
    db.commit()
    return dict(project=project_summary(n))


@router.delete("/projects/{pid}")
def delete_project(pid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    keys = {a.storage_key for a in db.scalars(select(Artifact).where(Artifact.project_id == p.id))} | {a.storage_key for a in db.scalars(select(Attachment).where(Attachment.project_id == p.id))}
    db.delete(p); db.commit()
    for k in keys:
        storage.delete(k)
    if settings.storage_backend == "db":
        from sqlalchemy import text
        db.execute(text("DELETE FROM blobs WHERE key LIKE :p"), dict(p=f"p/{pid}/%")); db.commit()
    else:
        shutil.rmtree(settings.storage_dir / "p" / pid, ignore_errors=True)
    return dict(ok=True)


# ------------------------------------------------------------------ brief / generate / edits (same validated operations the AI uses)
def run_op(db, u, p, name, payload) -> JSONResponse:
    out = aiops.execute_tool(aiops.Ctx(db, p, u), name, payload)
    db.commit()
    return JSONResponse(dict(ok=not out.is_error, result=out.result, events=out.events), status_code=422 if out.is_error else 200)


@router.put("/projects/{pid}/brief")
def put_brief(pid: str, b: UpdateBrief, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    return run_op(db, u, p, "update_brief", b.model_dump(exclude_none=True))


class GenerateIn(BaseModel):
    use_assumptions: bool = False
    stair_position: Optional[str] = None


@router.post("/projects/{pid}/generate")
def generate(pid: str, b: GenerateIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    return run_op(db, u, p, "generate_layout", b.model_dump(exclude_none=True))


@router.post("/projects/{pid}/edits")
def propose_edit_api(pid: str, b: ProposeEdit, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    return run_op(db, u, p, "propose_edit", b.model_dump(exclude_none=True))


@router.post("/projects/{pid}/views")
def views_api(pid: str, b: dict, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    return run_op(db, u, p, "generate_views", b)


class SheetPatch(BaseModel):
    paper: Optional[str] = Field(default=None, pattern="^A[0-4]$")
    scale: Optional[int] = None
    orientation: Optional[str] = Field(default=None, pattern="^(landscape|portrait)$")


@router.patch("/projects/{pid}/sheets/{sheet_id}")
def patch_sheet(pid: str, sheet_id: str, b: SheetPatch, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    rev = db.get(Revision, p.current_revision_id) if p.current_revision_id else None
    if not rev:
        raise HTTPException(404, "No drawing yet")
    model, brief = ProjectModel.model_validate(rev.model), Brief.model_validate(rev.brief)
    sd = next((s for s in model.sheets if s.id == sheet_id), None)
    if not sd:
        raise HTTPException(404, "Sheet not found")
    if b.scale is not None and b.scale not in (20, 25, 50, 100, 200, 500):
        raise HTTPException(422, "Unsupported scale. Use 1:20, 1:25, 1:50, 1:100, 1:200 or 1:500")
    if b.paper: sd.paper = b.paper
    if b.scale and sd.kind not in ("schedules", "index"): sd.scale = b.scale
    if b.orientation: sd.orientation = b.orientation
    meta = sheet_meta(db, p, u, model, brief, {}, 0, now())
    meta["sheet_index"] = []
    try:
        from ..engine.sheets import compose_sheet
        compose_sheet(model, sd, meta)
    except SheetOverflow as e:
        return svc_error(ServiceError("sheet_overflow", str(e), [s["text"] for s in e.suggestions], dict(sheet=e.sheet_number, suggestions=e.suggestions, needed_mm=list(e.needed), available_mm=list(e.avail))))
    try:
        r = create_revision(db, p, u, brief, model, f"Sheet {sd.number} set to {sd.paper} 1:{sd.scale}" if sd.scale else f"Sheet {sd.number} set to {sd.paper}")
    except ServiceError as e:
        return svc_error(e)
    db.commit()
    return dict(revision=revision_json(db, r, False))


# ------------------------------------------------------------------ proposals
class ConfirmIn(BaseModel):
    option: Optional[int] = None


@router.post("/proposals/{prid}/confirm")
def confirm_proposal(prid: str, b: ConfirmIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    pr = db.get(Proposal, prid)
    if not pr:
        raise HTTPException(404, "Proposal not found")
    p = owned_project(db, u, pr.project_id)
    if pr.state != "pending":
        return svc_error(ServiceError("proposal_not_pending", f"This proposal is {pr.state}.", ["Ask for the change again"], status=409))
    cur = db.get(Revision, p.current_revision_id) if p.current_revision_id else None
    if (cur.id if cur else "") != pr.base_revision_id:
        pr.state = "stale"; db.commit()
        return svc_error(ServiceError("proposal_stale", "The drawing changed after this proposal was made, so it cannot be applied safely.", ["Ask for the change again on the current revision"], status=409))
    try:
        if pr.kind == "options":
            if b.option is None or not (0 <= b.option < len(pr.options)):
                return svc_error(ServiceError("choose_option", "Choose one of the options.", [o["label"] for o in pr.options], status=422))
            opt = pr.options[b.option]
            ops, label = opt["ops"], opt["label"]
        else:
            ops, label = pr.ops, pr.summary
        if cur is None:
            from ..engine.layout import build_model
            from ..engine.edits import apply_edits
            brief = Brief.model_validate(p.brief or {})
            base = build_model(brief, use_assumptions=p.use_assumptions)
            nb, nm, notes = apply_edits(brief, base, ops, use_assumptions=p.use_assumptions)
            aiops.prepare_sheets(aiops.Ctx(db, p, u), nm, nb, [dict(kind=k) for k in (nb.requested_views or ["plan"])])
            changes = []
        else:
            nb, nm, changes, affected, issues, notes = evaluate_edit(db, p, u, cur, ops, pr.preserve)
        rev = create_revision(db, p, u, nb, nm, label[:120], changes)
    except ServiceError as e:
        return svc_error(e)
    except Exception as e:  # noqa: BLE001
        from ..engine.edits import EditError
        from ..engine.layout import ImpossibleLayout
        if isinstance(e, EditError):
            return svc_error(ServiceError(e.code, e.message, e.options))
        if isinstance(e, ImpossibleLayout):
            return svc_error(ServiceError("impossible_layout", "; ".join(e.reasons), e.suggestions))
        raise
    pr.state = "confirmed"
    db.add(Message(project_id=p.id, role="system", content=f"Revision {rev.number} saved: {label}", events=[dict(type="revision", revision_id=rev.id, number=rev.number, summary=rev.summary, render_status=rev.render_status)]))
    db.commit()
    return dict(revision=revision_json(db, rev, False))


@router.post("/proposals/{prid}/reject")
def reject_proposal(prid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    pr = db.get(Proposal, prid)
    if not pr:
        raise HTTPException(404, "Proposal not found")
    owned_project(db, u, pr.project_id)
    if pr.state == "pending":
        pr.state = "rejected"; db.commit()
    return dict(ok=True)


# ------------------------------------------------------------------ revisions / compare
@router.get("/projects/{pid}/revisions")
def revisions(pid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    return dict(revisions=[revision_json(db, r, False) for r in db.scalars(select(Revision).where(Revision.project_id == p.id).order_by(Revision.number))], current=p.current_revision_id)


def _rev(db, u, rid) -> tuple[Project, Revision]:
    r = db.get(Revision, rid)
    if not r:
        raise HTTPException(404, "Revision not found")
    return owned_project(db, u, r.project_id), r


@router.get("/revisions/{rid}")
def get_revision(rid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    _, r = _rev(db, u, rid)
    return dict(revision=revision_json(db, r))


@router.post("/revisions/{rid}/restore", status_code=201)
def restore(rid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p, r = _rev(db, u, rid)
    if p.status == "archived":
        raise HTTPException(409, "Project is archived")
    model, brief = ProjectModel.model_validate(r.model), Brief.model_validate(r.brief)
    try:
        n = create_revision(db, p, u, brief, model, f"Restored revision {r.number}", allow_errors=True)
    except ServiceError as e:
        return svc_error(e)
    db.add(Message(project_id=p.id, role="system", content=f"Restored revision {r.number} as revision {n.number}", events=[dict(type="revision", revision_id=n.id, number=n.number, summary=n.summary, render_status=n.render_status)]))
    db.commit()
    return dict(revision=revision_json(db, n, False))


@router.post("/revisions/{rid}/retry-render")
def retry_render(rid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p, r = _rev(db, u, rid)
    j = enqueue_render(db, p, r, retry=True)
    db.commit()
    return dict(job=job_json(db, j))


@router.get("/projects/{pid}/compare")
def compare(pid: str, a: str, b: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    ra, rb = db.get(Revision, a), db.get(Revision, b)
    if not ra or not rb or ra.project_id != p.id or rb.project_id != p.id:
        raise HTTPException(404, "Revision not found")
    ma, mb = ProjectModel.model_validate(ra.model), ProjectModel.model_validate(rb.model)
    changed = []
    for s in mb.sheets:
        sa, sb_ = ra.sheet_sigs.get(s.id, {}).get("c"), rb.sheet_sigs.get(s.id, {}).get("c")
        if sa != sb_:
            changed.append(dict(id=s.id, number=s.number, title=s.title, status="new" if sa is None else "changed"))
    return dict(a=revision_json(db, ra, True), b=revision_json(db, rb, True), changes=diff_models(ma, mb), sheets_changed=changed)


# ------------------------------------------------------------------ chat (SSE)
class ChatIn(BaseModel):
    content: str = Field(min_length=1, max_length=6000)
    attachment_ids: list[str] = Field(default_factory=list)
    consent: bool = False
    retry_of: Optional[str] = None


def sse(ev: dict) -> str:
    return f"data: {json.dumps(ev, default=str)}\n\n"


@router.post("/projects/{pid}/chat")
def chat(pid: str, b: ChatIn, request: Request, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    if p.status == "archived":
        return JSONResponse(status_code=409, content=dict(error=dict(code="project_archived", message="This project is archived. Unarchive it to continue.", next_actions=["Unarchive"])))
    if b.attachment_ids:
        atts = [a for a in (db.get(Attachment, i) for i in b.attachment_ids) if a and a.project_id == p.id]
        if len(atts) != len(set(b.attachment_ids)):
            raise HTTPException(404, "Attachment not found")
        if not b.consent:
            live = provider_status()["live"]
            return JSONResponse(status_code=409, content=dict(error=dict(
                code="consent_required",
                message=("These files will be sent to Anthropic's API so Claude can read them: " if live else "The mock assistant is active, so these files stay on this server and are not sent to any AI provider: ")
                + ", ".join(f"{a.filename} ({a.mime}, {a.size // 1024} KB)" for a in atts) + ". Only their content is sent, separately from your project data.",
                next_actions=["Confirm to send", "Remove the attachment"], detail=dict(files=[dict(id=a.id, filename=a.filename, size=a.size, mime=a.mime) for a in atts], provider=provider_status()["provider"]))))
    existing = None
    text = b.content
    if b.retry_of:
        old = db.get(Message, b.retry_of)
        if old and old.project_id == p.id and old.role == "assistant" and old.status in ("error", "cancelled"):
            prev_user = db.scalar(select(Message).where(Message.project_id == p.id, Message.role == "user", Message.created_at < old.created_at).order_by(Message.created_at.desc()).limit(1))
            if prev_user:
                existing, text = prev_user.id, prev_user.content
                db.delete(old); db.commit()

    def gen():
        partial = ""
        try:
            for ev in run_turn(db, p, u, text, b.attachment_ids, existing_user_id=existing):
                if ev["type"] == "text":
                    partial += ev["delta"]
                yield sse(ev)
        except GeneratorExit:                       # client cancelled the stream
            try:
                db.rollback()
                db.add(Message(project_id=p.id, role="assistant", content=partial, status="cancelled")); db.commit()
            except Exception:
                pass
            raise
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ attachments
ALLOWED_UP = {"image/png", "image/jpeg", "application/pdf", "text/plain"}


@router.post("/projects/{pid}/attachments", status_code=201)
async def upload_attachment(pid: str, file: UploadFile = File(...), u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File is larger than {settings.max_upload_mb} MB")
    if not data:
        raise HTTPException(422, "File is empty")
    mime = sniff(data)
    if mime not in ALLOWED_UP:
        raise HTTPException(415, "Unsupported file type. Use PNG, JPEG, PDF or plain text.")
    name = re.sub(r"[^A-Za-z0-9._ \-]", "_", (file.filename or "file"))[:120]
    aid = str(uuid.uuid4())
    key = f"p/{p.id}/att/{aid}"
    sha, size = storage.put(key, data)
    a = Attachment(id=aid, project_id=p.id, owner_id=u.id, filename=name, mime=mime, size=size, sha256=sha, storage_key=key)
    db.add(a); db.commit()
    live = provider_status()["live"]
    return dict(attachment=dict(id=a.id, filename=a.filename, mime=a.mime, size=a.size),
                notice=("When you send this file, its content is sent to Anthropic's API for Claude to read." if live else "Mock assistant is active: this file stays on the server."))


@router.delete("/attachments/{aid}")
def delete_attachment(aid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Attachment, aid)
    if not a:
        raise HTTPException(404, "Not found")
    owned_project(db, u, a.project_id)
    storage.delete(a.storage_key); db.delete(a); db.commit()
    return dict(ok=True)


@router.get("/attachments/{aid}/file")
def get_attachment(aid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Attachment, aid)
    if not a:
        raise HTTPException(404, "Not found")
    owned_project(db, u, a.project_id)
    return Response(storage.get(a.storage_key), media_type=a.mime, headers={"X-Content-Type-Options": "nosniff", "Content-Disposition": f'attachment; filename="{a.filename}"'})


# ------------------------------------------------------------------ exports / jobs / artifacts
class ExportIn(BaseModel):
    format: str = Field(pattern="^(pdf|dxf|png)$")
    sheet_ids: list[str] = Field(default_factory=list)
    revision_id: Optional[str] = None
    paper: Optional[str] = Field(default=None, pattern="^A[0-4]$")
    orientation: Optional[str] = Field(default=None, pattern="^(landscape|portrait)$")
    scale: Optional[int] = None
    dpi: Optional[int] = Field(default=None, ge=72, le=300)


@router.post("/projects/{pid}/exports", status_code=201)
def create_export(pid: str, b: ExportIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    rid = b.revision_id or p.current_revision_id
    rev = db.get(Revision, rid) if rid else None
    if not rev or rev.project_id != p.id:
        raise HTTPException(404, "Revision not found")
    model = ProjectModel.model_validate(rev.model)
    ids = b.sheet_ids or [s.id for s in model.sheets]
    if b.scale is not None and b.scale not in (20, 25, 50, 100, 200, 500):
        return svc_error(ServiceError("bad_scale", "Unsupported scale. Use 1:20, 1:25, 1:50, 1:100, 1:200 or 1:500.", ["Pick a supported scale"]))
    params = dict(format=b.format, sheet_ids=ids, paper=b.paper, scale=b.scale, orientation=b.orientation)
    if b.dpi: params["dpi"] = b.dpi
    brief = Brief.model_validate(rev.brief)
    base = sheet_meta(db, p, u, model, brief, rev.sheet_revs, rev.number, rev.created_at)
    try:
        precheck_export(rev, lambda sd: sheet_meta_for(sd, base, rev.sheet_revs), params)
    except ServiceError as e:
        return svc_error(e)
    j = enqueue_export(db, p, rev, params)
    db.commit()
    return dict(job=job_json(db, j))


@router.get("/projects/{pid}/estimate")
def estimate_api(pid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..engine.estimate import estimate
    p = owned_project(db, u, pid)
    rev = db.get(Revision, p.current_revision_id) if p.current_revision_id else None
    if not rev:
        return svc_error(ServiceError("no_drawing", "There is no drawing yet, so there is nothing to estimate.", ["Generate the layout first"], status=404))
    return dict(revision=rev.number, **estimate(ProjectModel.model_validate(rev.model)))


@router.get("/projects/{pid}/jobs")
def jobs(pid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    return dict(jobs=[job_json(db, j) for j in db.scalars(select(Job).where(Job.project_id == p.id).order_by(Job.created_at.desc()).limit(30))])


@router.get("/projects/{pid}/status")
def status(pid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    """Lightweight poll target for drawing progress (separate from chat)."""
    p = owned_project(db, u, pid)
    cur = db.get(Revision, p.current_revision_id) if p.current_revision_id else None
    js = list(db.scalars(select(Job).where(Job.project_id == p.id).order_by(Job.created_at.desc()).limit(10)))
    return dict(current_revision_id=p.current_revision_id, render_status=cur.render_status if cur else None, last_good_revision_id=p.last_good_revision_id,
                jobs=[job_json(db, j) for j in js])


@router.post("/jobs/{jid}/retry")
def retry_job(jid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    j = db.get(Job, jid)
    if not j:
        raise HTTPException(404, "Job not found")
    p = owned_project(db, u, j.project_id)
    rev = db.get(Revision, j.revision_id)
    if j.state != "failed":
        return dict(job=job_json(db, j))
    if j.kind == "render":
        enqueue_render(db, p, rev, retry=True)
    else:
        enqueue_export(db, p, rev, {k: v for k, v in j.params.items() if k != "artifact_id"}, retry=True)
    db.commit()
    return dict(job=job_json(db, j))


MIME = {"svg": "image/svg+xml", "png": "image/png", "pdf": "application/pdf", "dxf": "application/dxf", "zip": "application/zip"}


@router.get("/artifacts/{aid}/file")
def artifact_file(aid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Artifact, aid)
    if not a:
        raise HTTPException(404, "Not found")
    owned_project(db, u, a.project_id)
    if not storage.exists(a.storage_key):
        raise HTTPException(404, "File missing")
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=300"}
    if a.kind == "svg":
        headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"
    if a.purpose == "export":
        headers["Content-Disposition"] = f'attachment; filename="{a.name}"'
    return Response(storage.get(a.storage_key), media_type=MIME.get(a.kind, "application/octet-stream"), headers=headers)
