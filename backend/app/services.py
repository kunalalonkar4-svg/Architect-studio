"""Project services: sheet configuration, revisions, render/export orchestration."""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import zipfile
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import storage
from .engine import layout as L
from .engine.edits import apply_edits, diff_models
from .engine.model import Brief, ProjectModel, SheetDef, ViewDef, SIDE_FROM_NAME, digest
from .engine.sheets import (PAPERS, SCALES, TABLE_KINDS, SheetOverflow, compose_sheet, paper_size, sheet_signature)
from .engine.validate import validate_model
from .engine.views import default_sections
from .models import Artifact, Job, Message, Project, Proposal, Revision, User, now


class ServiceError(Exception):
    def __init__(self, code: str, message: str, next_actions: list | None = None, detail: dict | None = None, status: int = 422):
        super().__init__(message)
        self.code, self.message, self.next_actions, self.detail, self.status = code, message, next_actions or [], detail or {}, status

    def as_dict(self):
        return dict(code=self.code, message=self.message, next_actions=self.next_actions, detail=self.detail)


SHEET_KINDS = {
    "index": ("G-001", "Cover, Index and Notes", 0),
    "site": ("A-101", "Site Plan", 100),
    "plan": ("A-102", "Ground Floor Plan", 50),
    "roof": ("A-103", "Roof / Terrace Plan", 100),
    "elevations": ("A-201", "Elevations", 100),
    "section": ("A-301", "Sections", 50),
    "schedules": ("A-401", "Schedules", 0),
}
KIND_ORDER = list(SHEET_KINDS)


def facing_of(model: ProjectModel, name: str) -> str:
    name = name.lower()
    road = model.plot["road_side"]
    if name in SIDE_FROM_NAME:
        return SIDE_FROM_NAME[name]
    if name in ("n", "e", "s", "w"):
        return name
    opp = {"n": "s", "s": "n", "e": "w", "w": "e"}
    left = {"s": "w", "n": "e", "e": "s", "w": "n"}
    right = {"s": "e", "n": "w", "e": "n", "w": "s"}
    return {"front": road, "road": road, "rear": opp[road], "back": opp[road], "left": left[road], "right": right[road]}[name]


def ensure_sheet(model: ProjectModel, kind: str, paper: str | None = None, scale: int | None = None,
                 facings: list[str] | None = None, orientation: str | None = None, cut: dict | None = None) -> SheetDef:
    if kind not in SHEET_KINDS:
        raise ServiceError("unknown_view", f"'{kind}' is not a supported drawing type.", [f"Supported: {', '.join(SHEET_KINDS)}"])
    number, title, dscale = SHEET_KINDS[kind]
    sid = f"sheet-{kind}"
    vids: list[str] = []
    if kind in ("plan", "site", "roof"):
        vid = f"v-{kind}"
        _put_view(model, ViewDef(id=vid, type=kind)); vids = [vid]
    elif kind == "elevations":
        fs = [facing_of(model, f) for f in (facings or ["front", "rear", "left", "right"])]
        for f in dict.fromkeys(fs):
            vid = f"v-elev-{f}"
            _put_view(model, ViewDef(id=vid, type="elevation", facing=f)); vids.append(vid)
        if facings is None:
            pass
    elif kind == "section":
        c = cut or default_sections(model)[0]
        vid = f"v-sec-{c.get('label', 'A')}"
        _put_view(model, ViewDef(id=vid, type="section", cut=c)); vids = [vid]
    elif kind == "schedules":
        for t in ("rooms", "openings"):
            _put_view(model, ViewDef(id=f"v-{t}", type=t)); vids.append(f"v-{t}")
    elif kind == "index":
        _put_view(model, ViewDef(id="v-index", type="index")); vids = ["v-index"]
    existing = next((s for s in model.sheets if s.id == sid), None)
    if existing and kind == "elevations" and facings is not None:
        # keep earlier facings unless the user restricted explicitly
        pass
    sd = SheetDef(id=sid, number=number, title=title, kind=kind, views=vids,
                  paper=paper or (existing.paper if existing else "A3"),
                  orientation=orientation or (existing.orientation if existing else "landscape"),
                  scale=0 if kind in TABLE_KINDS else (scale or (existing.scale if existing else dscale)))
    model.sheets = [s for s in model.sheets if s.id != sid] + [sd]
    model.sheets.sort(key=lambda s: KIND_ORDER.index(s.kind))
    return sd


def _put_view(model: ProjectModel, vd: ViewDef):
    model.views = [v for v in model.views if v.id != vd.id] + [vd]


def autofit(model: ProjectModel, sd: SheetDef, meta: dict, explicit_paper=False, explicit_scale=False):
    """Pick the smallest paper (and, if needed, scale) on which the sheet fits unless the user fixed them."""
    if sd.kind in TABLE_KINDS and explicit_paper:
        compose_sheet(model, sd, meta); return
    papers = [sd.paper] if explicit_paper else list(PAPERS)
    scales = [sd.scale] if (explicit_scale or sd.kind in TABLE_KINDS) else [s for s in SCALES if s >= sd.scale]
    last = None
    for sc in scales:
        for p in papers:
            sd2 = sd.model_copy(update=dict(paper=p, scale=sc))
            try:
                compose_sheet(model, sd2, meta)
                sd.paper, sd.scale = p, sc
                return
            except SheetOverflow as e:
                last = e
    if last:
        raise last


def project_date(rev: Optional[Revision] = None) -> str:
    return (rev.created_at if rev else now()).strftime("%Y-%m-%d")


def title_block_meta(db: Session, project: Project, user: User) -> dict:
    meta = dict(project_name=project.name, firm_name=user.firm_name or "", firm_line=user.firm_line or "",
                client=project.client, address=project.address)
    sig = [project.name, user.firm_name, user.firm_line, project.client, project.address, user.logo_key, project.review_status]
    if user.logo_key and storage.exists(user.logo_key):
        meta["logo"] = dict(data=storage.get(user.logo_key), mime=user.logo_mime or "image/png")
    meta["title_block_sig"] = digest(sig)
    return meta


def sheet_meta(db, project, user, model: ProjectModel, brief: Brief, sheet_revs: dict, rev_number: int, created: dt.datetime) -> dict:
    meta = title_block_meta(db, project, user)
    meta["date"] = created.strftime("%Y-%m-%d")
    meta["revision"] = str(rev_number)
    meta["sheet_rev"] = {n: str(v["rev"]) for n, v in sheet_revs.items()}
    meta["future_levels"] = brief.future_levels
    meta["missing"] = open_items(model, brief)
    meta["sheet_index"] = [dict(number=s.number, title=s.title, scale=("NTS" if not s.scale or s.kind in TABLE_KINDS else f"1:{s.scale}"),
                                paper=s.paper, rev=str(sheet_revs.get(s.number, {}).get("rev", rev_number))) for s in model.sheets]
    return meta


def sheet_meta_for(sd, base_meta: dict, sheet_revs: dict) -> dict:
    m = dict(base_meta)
    m["revision_history"] = sheet_revs.get(sd.number, {}).get("history", [])
    return m


def open_items(model: ProjectModel, brief: Brief) -> list[str]:
    out = []
    if model.plot:
        for k, s in model.plot["setback_source"].items():
            if s == "assumed":
                out.append(f"{k.capitalize()} open space ({model.plot['setbacks'][k]:.0f} mm) is assumed. Confirm with local rules.")
    out.append("Local planning rules (FAR, coverage, height, parking norms) have not been verified.")
    out.append("Survey, soil and structural design are not part of this concept draft.")
    if not model.roof_approved:
        out.append("Roof / terrace geometry has not been approved by the user.")
    for fl in brief.future_levels:
        out.append(f"{fl} is not drawn; foundation and stair provisions need structural review.")
    return out


def compute_sheet_state(db, project, user, model: ProjectModel, brief: Brief, prev: Optional[Revision], number: int, created, summary: str):
    """Returns (sheet_sigs, sheet_revs) where a sheet's revision label advances only when its content changed."""
    prev_sigs = prev.sheet_sigs if prev else {}
    prev_revs = prev.sheet_revs if prev else {}
    revs: dict = {}
    sigs: dict = {}
    ordered = sorted(model.sheets, key=lambda s: (s.kind == "index"))   # index last: it lists the others' revisions
    for sd in ordered:
        base = sheet_meta(db, project, user, model, brief, revs, number, created)
        c_sig = sheet_signature(model, sd, base, with_titleblock=False)
        old = prev_sigs.get(sd.id, {}).get("c")
        if old == c_sig and sd.number in prev_revs:
            revs[sd.number] = prev_revs[sd.number]
        else:
            hist = list(prev_revs.get(sd.number, {}).get("history", [])) + [dict(n=number, date=created.strftime("%Y-%m-%d"), text=summary[:60] or "Issued")]
            revs[sd.number] = dict(rev=number, history=hist[-6:])
        base = sheet_meta(db, project, user, model, brief, revs, number, created)
        sigs[sd.id] = dict(c=c_sig, r=sheet_signature(model, sd, sheet_meta_for(sd, base, revs), with_titleblock=True))
    return sigs, revs


def create_revision(db: Session, project: Project, user: User, brief: Brief, model: ProjectModel, summary: str,
                    changes: list | None = None, allow_errors: bool = False) -> Revision:
    issues = validate_model(model)
    errors = [i for i in issues if i["severity"] == "error"]
    if errors and not allow_errors:
        raise ServiceError("validation_failed", "The drawing has errors that must be fixed first.",
                           [e["fix"] or e["message"] for e in errors], dict(issues=issues))
    prev = db.get(Revision, project.current_revision_id) if project.current_revision_id else None
    number = (db.scalar(select(func.max(Revision.number)).where(Revision.project_id == project.id)) or 0) + 1
    created = now()
    sigs, revs = compute_sheet_state(db, project, user, model, brief, prev, number, created, summary)
    rev = Revision(project_id=project.id, number=number, summary=summary, changes=changes or [], model=model.model_dump(),
                   brief=brief.model_dump(), sheet_sigs=sigs, sheet_revs=revs, render_status="queued", validation=issues, created_at=created)
    db.add(rev)
    db.flush()
    project.current_revision_id = rev.id
    project.brief = brief.model_dump()
    project.updated_at = now()
    enqueue_render(db, project, rev)
    return rev


def enqueue_render(db: Session, project: Project, rev: Revision, retry: bool = False) -> Job:
    key = hashlib.sha256(f"render:{rev.id}".encode()).hexdigest()[:32]
    job = db.scalar(select(Job).where(Job.project_id == project.id, Job.kind == "render", Job.key == key))
    if job:
        if retry and job.state == "failed":
            job.state, job.error, job.error_detail, job.progress, job.step = "queued", "", {}, 0.0, "Queued (retry)"
            rev.render_status, rev.render_error = "queued", ""
        return job
    job = Job(project_id=project.id, kind="render", revision_id=rev.id, key=key, params={}, step="Queued")
    db.add(job)
    db.flush()
    return job


def enqueue_export(db: Session, project: Project, rev: Revision, params: dict, retry: bool = False) -> Job:
    key = hashlib.sha256(f"export:{rev.id}:{digest(params)}".encode()).hexdigest()[:32]
    job = db.scalar(select(Job).where(Job.project_id == project.id, Job.kind == "export", Job.key == key))
    if job:
        if retry and job.state == "failed":
            job.state, job.error, job.error_detail, job.progress, job.step = "queued", "", {}, 0.0, "Queued (retry)"
        return job
    job = Job(project_id=project.id, kind="export", revision_id=rev.id, key=key, params=params, step="Queued")
    db.add(job)
    db.flush()
    return job


def precheck_export(rev: Revision, project_meta_fn, params: dict):
    """Fail fast (before queueing) if any selected sheet cannot fit the chosen paper/scale."""
    model = ProjectModel.model_validate(rev.model)
    sel = [s for s in model.sheets if s.id in params["sheet_ids"]]
    if not sel:
        raise ServiceError("no_sheets", "Select at least one sheet to export.", ["Pick sheets in the export panel"])
    for sd in sel:
        meta = project_meta_fn(sd)
        try:
            compose_sheet(model, sd, meta, paper=params.get("paper"), scale=params.get("scale") if sd.kind not in TABLE_KINDS else None,
                          orientation=params.get("orientation"))
        except SheetOverflow as e:
            raise ServiceError("sheet_overflow", str(e), [s["text"] for s in e.suggestions],
                               dict(sheet=sd.number, needed_mm=list(e.needed), available_mm=list(e.avail), suggestions=e.suggestions))
    return model, sel


def new_proposal(db, project, base_rev, kind, ops, preserve, summary, changes, affected, options=None, issues=None) -> Proposal:
    for p in db.scalars(select(Proposal).where(Proposal.project_id == project.id, Proposal.state == "pending")):
        p.state = "stale"
    pr = Proposal(project_id=project.id, kind=kind, base_revision_id=base_rev.id, ops=ops, preserve=preserve, summary=summary,
                  changes=changes, affected_sheets=affected, options=options or [], issues=issues or [])
    db.add(pr)
    db.flush()
    return pr


def affected_sheets(db, project, user, old: ProjectModel, new: ProjectModel, brief_old: Brief, brief_new: Brief) -> list[dict]:
    """Which sheets would actually change, by comparing generated drawing content (not guesses)."""
    meta_old = sheet_meta(db, project, user, old, brief_old, {}, 0, now())
    meta_new = sheet_meta(db, project, user, new, brief_new, {}, 0, now())
    out = []
    for sd in new.sheets:
        old_sd = next((s for s in old.sheets if s.id == sd.id), None)
        try:
            a = sheet_signature(old, old_sd, meta_old) if old_sd else None
            b = sheet_signature(new, sd, meta_new)
        except Exception:
            a, b = None, "x"
        if a != b:
            out.append(dict(id=sd.id, number=sd.number, title=sd.title))
    return out


def evaluate_edit(db, project, user, rev: Revision, ops: list[dict], preserve: list[str] | None = None):
    """Apply ops to a copy; returns (new_brief, new_model, changes, affected, issues, notes). Raises edit errors."""
    brief = Brief.model_validate(rev.brief)
    model = ProjectModel.model_validate(rev.model)
    nb, nm, notes = apply_edits(brief, model, ops, use_assumptions=project.use_assumptions, preserve=preserve)
    changes = diff_models(model, nm)
    issues = validate_model(nm)
    affected = affected_sheets(db, project, user, model, nm, brief, nb)
    return nb, nm, changes, affected, issues, notes


def storage_key(project_id: str, rev_id: str, name: str) -> str:
    return f"p/{project_id}/{rev_id}/{name}"
