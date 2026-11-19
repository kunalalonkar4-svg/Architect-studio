"""Share links with comments, review requests, and sample projects that need no sign-in.

Honesty rules: a share link is read-only and pinned to one revision; comments are plain notes from whoever holds the link;
a review request is a record the owner keeps. No reviewer is assigned, nobody signs or approves anything, and the status
changes only when the owner changes it."""
from __future__ import annotations

import datetime as dt
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import storage
from ..db import get_db
from ..engine.estimate import estimate
from ..engine.model import Brief, ProjectModel
from ..engine.review import review
from ..models import Artifact, Comment, Project, ReviewRequest, Revision, ShareLink, User, now
from ..security import current_user, owned_project
from .routes import MIME, model3d_payload

router = APIRouter(prefix="/api")

MAX_COMMENTS_PER_SHARE = 200
NOT_REVIEWED = ("Concept drawing. Not reviewed, signed, stamped or approved by any architect or engineer. "
                "Check local rules with a licensed professional before relying on it.")


# ------------------------------------------------------------------ owner side: share links
class ShareIn(BaseModel):
    allow_comments: bool = True


def share_json(s: ShareLink, rev_no: Optional[int] = None, n_comments: int = 0) -> dict:
    return dict(id=s.id, token=s.token, path=f"#/share/{s.token}", revision_id=s.revision_id, revision=rev_no, allow_comments=s.allow_comments,
                active=s.revoked_at is None, created_at=s.created_at.isoformat(), comments=n_comments)


def _current_rev(db: Session, p: Project) -> Revision:
    rev = db.get(Revision, p.current_revision_id) if p.current_revision_id else None
    if not rev:
        raise HTTPException(409, "There is no drawing yet, so there is nothing to share.")
    return rev


@router.post("/projects/{pid}/shares", status_code=201)
def create_share(pid: str, b: ShareIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    rev = _current_rev(db, p)
    if rev.render_status != "done":
        raise HTTPException(409, "Drawings are still being prepared. Share once they are ready.")
    s = ShareLink(project_id=p.id, revision_id=rev.id, token=secrets.token_urlsafe(24), allow_comments=b.allow_comments)
    db.add(s); db.commit()
    return dict(share=share_json(s, rev.number))


@router.get("/projects/{pid}/shares")
def list_shares(pid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    out = []
    for s in db.scalars(select(ShareLink).where(ShareLink.project_id == p.id).order_by(ShareLink.created_at.desc())):
        rev = db.get(Revision, s.revision_id)
        n = db.scalar(select(func.count()).select_from(Comment).where(Comment.share_id == s.id)) or 0
        out.append(share_json(s, rev.number if rev else None, n))
    return dict(shares=out)


@router.delete("/projects/{pid}/shares/{sid}")
def revoke_share(pid: str, sid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    s = db.get(ShareLink, sid)
    if not s or s.project_id != p.id:
        raise HTTPException(404, "Share link not found")
    s.revoked_at = s.revoked_at or now(); db.commit()
    return dict(share=share_json(s))


# ------------------------------------------------------------------ comments
class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    author: str = Field(default="", max_length=80)
    sheet_id: Optional[str] = Field(default=None, max_length=100)


def comment_json(c: Comment, rev_no: Optional[int] = None) -> dict:
    return dict(id=c.id, author=c.author, from_owner=c.from_owner, body=c.body, sheet_id=c.sheet_id, resolved=c.resolved,
                revision=rev_no, created_at=c.created_at.isoformat())


@router.get("/projects/{pid}/comments")
def list_comments(pid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    nums = {r.id: r.number for r in db.scalars(select(Revision).where(Revision.project_id == p.id))}
    rows = db.scalars(select(Comment).where(Comment.project_id == p.id).order_by(Comment.created_at))
    return dict(comments=[comment_json(c, nums.get(c.revision_id)) for c in rows])


@router.post("/projects/{pid}/comments", status_code=201)
def owner_comment(pid: str, b: CommentIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    rev = _current_rev(db, p)
    c = Comment(project_id=p.id, revision_id=rev.id, sheet_id=b.sheet_id, author=(u.display_name or "Owner")[:80], from_owner=True, body=b.body.strip())
    db.add(c); db.commit()
    return dict(comment=comment_json(c, rev.number))


@router.post("/projects/{pid}/comments/{cid}/resolve")
def toggle_resolved(pid: str, cid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    c = db.get(Comment, cid)
    if not c or c.project_id != p.id:
        raise HTTPException(404, "Comment not found")
    c.resolved = not c.resolved; db.commit()
    return dict(comment=comment_json(c))


# ------------------------------------------------------------------ public read-only view
def _active_share(db: Session, token: str) -> tuple[ShareLink, Project, Revision]:
    s = db.scalar(select(ShareLink).where(ShareLink.token == token))
    if not s or s.revoked_at is not None:
        raise HTTPException(404, "This link is not available. Ask the sender for a new one.")
    p = db.get(Project, s.project_id); rev = db.get(Revision, s.revision_id)
    if not p or not rev:
        raise HTTPException(404, "This link is not available. Ask the sender for a new one.")
    return s, p, rev


@router.get("/public/share/{token}")
def public_share(token: str, db: Session = Depends(get_db)):
    s, p, rev = _active_share(db, token)
    owner = db.get(User, p.owner_id)
    model = ProjectModel.model_validate(rev.model)
    arts = list(db.scalars(select(Artifact).where(Artifact.revision_id == rev.id, Artifact.purpose == "preview")))
    sheets = [dict(id=sd.id, number=sd.number, title=sd.title, ready=any(a.sheet_id == sd.id and a.kind == "svg" for a in arts)) for sd in model.sheets]
    rows = db.scalars(select(Comment).where(Comment.share_id == s.id).order_by(Comment.created_at))
    owner_rows = db.scalars(select(Comment).where(Comment.project_id == p.id, Comment.from_owner.is_(True)).order_by(Comment.created_at))
    cs = sorted([*rows, *owner_rows], key=lambda c: c.created_at)
    return dict(project=dict(name=p.name, firm=(owner.firm_name if owner else "") or "", revision=rev.number, shared_at=s.created_at.isoformat()),
                sheets=sheets, comments=[comment_json(c, rev.number) for c in cs], allow_comments=s.allow_comments, notice=NOT_REVIEWED)


@router.get("/public/share/{token}/sheet/{sheet_id}.{kind}")
def public_sheet(token: str, sheet_id: str, kind: str, db: Session = Depends(get_db)):
    s, p, rev = _active_share(db, token)
    if kind not in ("svg", "png"):
        raise HTTPException(404, "Not found")
    a = db.scalar(select(Artifact).where(Artifact.revision_id == rev.id, Artifact.sheet_id == sheet_id, Artifact.kind == kind, Artifact.purpose == "preview"))
    if not a or not storage.exists(a.storage_key):
        raise HTTPException(404, "Sheet not available")
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=300"}
    if kind == "svg":
        headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"
    return Response(storage.get(a.storage_key), media_type=MIME[kind], headers=headers)


@router.get("/public/share/{token}/model3d")
def public_model3d(token: str, db: Session = Depends(get_db)):
    _, _, rev = _active_share(db, token)
    return model3d_payload(ProjectModel.model_validate(rev.model), rev.number)


@router.post("/public/share/{token}/comments", status_code=201)
def public_comment(token: str, b: CommentIn, db: Session = Depends(get_db)):
    s, p, rev = _active_share(db, token)
    if not s.allow_comments:
        raise HTTPException(403, "Comments are turned off for this link.")
    n = db.scalar(select(func.count()).select_from(Comment).where(Comment.share_id == s.id)) or 0
    if n >= MAX_COMMENTS_PER_SHARE:
        raise HTTPException(429, "This link has reached its comment limit. Ask the owner for a new link.")
    body = b.body.strip()
    if not body:
        raise HTTPException(422, "Write a comment first.")
    c = Comment(project_id=p.id, share_id=s.id, revision_id=rev.id, sheet_id=b.sheet_id, author=(b.author.strip() or "Guest")[:80], body=body)
    db.add(c); db.commit()
    return dict(comment=comment_json(c, rev.number))


# ------------------------------------------------------------------ review requests (owner-maintained record)
KINDS = {"architect": "Architect review", "structural": "Structural engineer review", "mep": "MEP engineer review"}


class ReviewReqIn(BaseModel):
    kind: str = Field(pattern="^(architect|structural|mep)$")
    reviewer_name: str = Field(default="", max_length=200)
    reviewer_contact: str = Field(default="", max_length=300)
    note: str = Field(default="", max_length=2000)


class ReviewReqPatch(BaseModel):
    status: Optional[str] = Field(default=None, pattern="^(requested|sent|reviewed|cancelled)$")
    outcome_note: Optional[str] = Field(default=None, max_length=2000)


def rr_json(r: ReviewRequest, rev_no: Optional[int] = None) -> dict:
    return dict(id=r.id, kind=r.kind, label=KINDS.get(r.kind, r.kind), reviewer_name=r.reviewer_name, reviewer_contact=r.reviewer_contact, note=r.note,
                status=r.status, outcome_note=r.outcome_note, revision=rev_no, created_at=r.created_at.isoformat(), updated_at=r.updated_at.isoformat())


REVIEW_INFO = ("This is your own checklist of professional reviews. Drafta does not assign or employ reviewers, and a status here is not an approval. "
               "Share the link or export the drawing set with your own architect or engineer, then record what they tell you.")


@router.get("/projects/{pid}/review-requests")
def list_review_requests(pid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    nums = {r.id: r.number for r in db.scalars(select(Revision).where(Revision.project_id == p.id))}
    rows = db.scalars(select(ReviewRequest).where(ReviewRequest.project_id == p.id).order_by(ReviewRequest.created_at.desc()))
    return dict(requests=[rr_json(r, nums.get(r.revision_id)) for r in rows], info=REVIEW_INFO)


@router.post("/projects/{pid}/review-requests", status_code=201)
def create_review_request(pid: str, b: ReviewReqIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    rev = _current_rev(db, p)
    r = ReviewRequest(project_id=p.id, revision_id=rev.id, kind=b.kind, reviewer_name=b.reviewer_name.strip(), reviewer_contact=b.reviewer_contact.strip(), note=b.note.strip())
    db.add(r); db.commit()
    return dict(request=rr_json(r, rev.number), info=REVIEW_INFO)


@router.patch("/projects/{pid}/review-requests/{rid}")
def patch_review_request(pid: str, rid: str, b: ReviewReqPatch, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, u, pid)
    r = db.get(ReviewRequest, rid)
    if not r or r.project_id != p.id:
        raise HTTPException(404, "Review request not found")
    if b.status is not None:
        r.status = b.status
    if b.outcome_note is not None:
        r.outcome_note = b.outcome_note.strip()
    r.updated_at = now(); db.commit()
    return dict(request=rr_json(r))


# ------------------------------------------------------------------ sample projects, no sign-in
SAMPLES = {
    "east-2bhk": dict(title="30 × 50 ft, east road, 2 bedrooms", brief=dict(plot_frontage_mm=9144, plot_depth_mm=15240, road_side="e", bedrooms=2, parking=True, kitchen_type="open",
                      setbacks=dict(front=3000, rear=1500, left=0, right=0))),
    "north-1bhk": dict(title="30 × 45 ft, north road, 1 bedroom", brief=dict(plot_frontage_mm=9144, plot_depth_mm=13716, road_side="n", bedrooms=1, parking=False, kitchen_type="closed",
                       setbacks=dict(front=1500, rear=1000, left=0, right=0))),
    "south-duplex": dict(title="30 × 50 ft, south road, 3 bedroom duplex", brief=dict(plot_frontage_mm=9144, plot_depth_mm=15240, road_side="s", bedrooms=3, levels_now=2, parking=True,
                         setbacks=dict(front=3000, rear=1500, left=0, right=0))),
}
SAMPLE_NOTE = ("Sample with example inputs. Setbacks here are example values, not your local rules. Concept only, not reviewed, signed or approved.")
_cache: dict[str, dict] = {}


def _sample(sid: str) -> dict:
    if sid in _cache:
        return _cache[sid]
    if sid not in SAMPLES:
        raise HTTPException(404, "Sample not found")
    from ..engine.layout import build_model
    from ..engine.render import render_svg
    from ..engine.sheets import compose_sheet
    from ..services import autofit, ensure_sheet, open_items
    brief = Brief.model_validate(SAMPLES[sid]["brief"])
    model = build_model(brief, use_assumptions=False)
    sd = ensure_sheet(model, "plan")
    meta = dict(project_name=SAMPLES[sid]["title"], firm_name="Sample", firm_line="", client="", address="", date=dt.date.today().isoformat(), revision="1",
                sheet_rev={}, future_levels=[], missing=open_items(model, brief), revision_history=[],
                sheet_index=[dict(number=s.number, title=s.title, scale=f"1:{s.scale}", paper=s.paper, rev="1") for s in model.sheets])
    autofit(model, sd, meta)
    svg = render_svg(compose_sheet(model, sd, meta))
    out = dict(model=model, svg=svg, review=review(model), estimate=estimate(model))
    _cache[sid] = out
    return out


@router.get("/public/samples")
def list_samples():
    return dict(samples=[dict(id=k, title=v["title"]) for k, v in SAMPLES.items()], note=SAMPLE_NOTE)


@router.get("/public/samples/{sid}")
def get_sample(sid: str):
    d = _sample(sid); m: ProjectModel = d["model"]
    fp = m.footprint()
    return dict(id=sid, title=SAMPLES[sid]["title"], note=SAMPLE_NOTE, rooms=[dict(name=s.name, w=round(s.w), h=round(s.h), level=s.level) for s in m.spaces],
                levels=len(m.levels), review=d["review"], estimate=d["estimate"], plan_url=f"/api/public/samples/{sid}/plan.svg", footprint=fp)


@router.get("/public/samples/{sid}/plan.svg")
def sample_plan(sid: str):
    return Response(_sample(sid)["svg"].encode(), media_type="image/svg+xml",
                    headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:", "X-Content-Type-Options": "nosniff"})


@router.get("/public/samples/{sid}/model3d")
def sample_model3d(sid: str):
    return model3d_payload(_sample(sid)["model"], 1)
