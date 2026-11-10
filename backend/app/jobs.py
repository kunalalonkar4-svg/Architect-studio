"""Database-backed job queue (SELECT ... FOR UPDATE SKIP LOCKED) with in-process or standalone workers."""
from __future__ import annotations

import datetime as dt
import io
import re
import threading
import time
import traceback
import zipfile

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import storage
from .config import settings
from .db import SessionLocal
from .engine.model import Brief, ProjectModel
from .engine.render import MM, render_dxf, render_pdf, render_png, render_svg
from .engine.sheets import SheetOverflow, TABLE_KINDS, build_sheet_views, compose_sheet, paper_size
from .engine.validate import check_agreement, validate_model
from .models import Artifact, Job, Project, Revision, User, now
from .services import ServiceError, sheet_meta, sheet_meta_for, storage_key

RENDER_FAULT: set[str] = set()   # test hook: sheet numbers that must fail to render
_stop = threading.Event()


def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")[:40] or "project"


def claim(db: Session) -> Job | None:
    job = db.scalar(select(Job).where(Job.state == "queued").order_by(Job.created_at).with_for_update(skip_locked=True).limit(1))
    if job:
        job.state, job.attempts, job.step = "running", job.attempts + 1, "Starting"
        db.commit()
    return job


def reclaim_stale(db: Session, minutes: int = 5):
    cutoff = now() - dt.timedelta(minutes=minutes)
    db.execute(update(Job).where(Job.state == "running", Job.updated_at < cutoff).values(state="queued", step="Re-queued after worker stop"))
    db.commit()


def _progress(db: Session, job: Job, frac: float, step: str):
    job.progress, job.step = frac, step
    db.commit()


def process(job_id: str):
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        try:
            if job.kind == "render":
                run_render(db, job)
            else:
                run_export(db, job)
        except ServiceError as e:
            db.rollback(); job = db.get(Job, job_id)
            job.state, job.error, job.error_detail = "failed", e.message, e.as_dict()
            _mark_failed(db, job, e.message)
            db.commit()
        except Exception as e:  # noqa: BLE001  never log request content, only the error type
            db.rollback(); job = db.get(Job, job_id)
            job.state, job.error = "failed", f"{type(e).__name__}: {str(e)[:300]}"
            _mark_failed(db, job, job.error)
            db.commit()
    finally:
        db.close()


def _mark_failed(db, job, msg):
    if job.kind == "render":
        rev = db.get(Revision, job.revision_id)
        if rev:
            rev.render_status, rev.render_error = "failed", msg


def worker_loop():
    last_reclaim = 0.0
    while not _stop.is_set():
        db = SessionLocal()
        try:
            if time.time() - last_reclaim > 30:
                reclaim_stale(db); last_reclaim = time.time()
            job = claim(db)
            jid = job.id if job else None
        except Exception:
            db.rollback(); jid = None
        finally:
            db.close()
        if jid:
            process(jid)
        else:
            time.sleep(0.25)


_threads: list[threading.Thread] = []


def start_workers(n: int | None = None):
    if _threads:
        return
    _stop.clear()
    for i in range(n or settings.worker_threads):
        t = threading.Thread(target=worker_loop, name=f"worker-{i}", daemon=True)
        t.start(); _threads.append(t)


def stop_workers():
    _stop.set()
    for t in _threads:
        t.join(timeout=3)
    _threads.clear()


def run_pending_once(max_jobs: int = 50) -> int:
    """Process queued jobs synchronously (used by tests and the standalone CLI)."""
    n = 0
    while n < max_jobs:
        db = SessionLocal()
        try:
            job = claim(db); jid = job.id if job else None
        finally:
            db.close()
        if not jid:
            break
        process(jid); n += 1
    return n


# ------------------------------------------------------------------ render
def run_render(db: Session, job: Job):
    rev = db.get(Revision, job.revision_id)
    project = db.get(Project, job.project_id)
    user = db.get(User, project.owner_id)
    model = ProjectModel.model_validate(rev.model)
    brief = Brief.model_validate(rev.brief)
    rev.render_status = "running"; db.commit()
    base = sheet_meta(db, project, user, model, brief, rev.sheet_revs, rev.number, rev.created_at)
    metas: dict = {}
    failed: list[tuple[str, str, dict]] = []
    n = max(1, len(model.sheets))
    for i, sd in enumerate(model.sheets):
        _progress(db, job, i / n, f"Drawing {sd.number} {sd.title}")
        rsig = rev.sheet_sigs[sd.id]["r"]
        existing = list(db.scalars(select(Artifact).where(Artifact.project_id == project.id, Artifact.sheet_id == sd.id,
                                                          Artifact.purpose == "preview", Artifact.meta["rsig"].as_string() == rsig)))
        by_kind = {a.kind: a for a in existing}
        if {"svg", "png", "pdf"} <= set(by_kind):
            for k in ("svg", "png", "pdf"):
                a = by_kind[k]
                if not db.scalar(select(Artifact).where(Artifact.revision_id == rev.id, Artifact.sheet_id == sd.id, Artifact.kind == k, Artifact.purpose == "preview")):
                    db.add(Artifact(project_id=project.id, revision_id=rev.id, job_id=job.id, kind=k, purpose="preview", sheet_id=sd.id,
                                    name=a.name, storage_key=a.storage_key, size=a.size, sha256=a.sha256, meta=a.meta))
            metas.update(by_kind["svg"].meta.get("views", {}))
            db.commit()
            continue
        try:
            if sd.number in RENDER_FAULT:
                raise RuntimeError("simulated render failure")
            meta = sheet_meta_for(sd, base, rev.sheet_revs)
            sh = compose_sheet(model, sd, meta)
            svg = render_svg(sh)
            pdf = render_pdf([sh], title=f"{project.name} {sd.number}")
            png = render_png(pdf, dpi=110)
            vm = {k: v for k, v in sh.meta.items()}
            metas.update(vm)
            for kind, data in (("svg", svg.encode()), ("png", png), ("pdf", pdf)):
                key = storage_key(project.id, rev.id, f"{sd.number}.{kind}")
                sha, size = storage.put(key, data)
                db.add(Artifact(project_id=project.id, revision_id=rev.id, job_id=job.id, kind=kind, purpose="preview", sheet_id=sd.id,
                                name=f"{sd.number} {sd.title}", storage_key=key, size=size, sha256=sha, meta=dict(rsig=rsig, views=vm, paper=sd.paper, scale=sd.scale)))
            db.commit()
        except SheetOverflow as e:
            failed.append((sd.number, str(e), dict(suggestions=e.suggestions, needed_mm=list(e.needed), available_mm=list(e.avail))))
        except Exception as e:  # noqa: BLE001
            failed.append((sd.number, f"{type(e).__name__}: {str(e)[:200]}", {}))
    issues = validate_model(model) + check_agreement(model, metas)
    rev.validation = issues
    if failed:
        msg = "; ".join(f"{n_}: {m}" for n_, m, _ in failed)
        job.state, job.error = "failed", msg
        job.error_detail = dict(code="render_failed", message=msg, failed=[dict(sheet=n_, message=m, **d) for n_, m, d in failed],
                                next_actions=["Retry the render", "Adjust the sheet paper or scale", "The last successful drawing is still available"])
        rev.render_status, rev.render_error = "failed", msg
        db.commit()
        return
    rev.render_status, rev.render_error = "done", ""
    project.last_good_revision_id = rev.id
    job.state, job.progress, job.step = "done", 1.0, "Done"
    db.commit()


# ------------------------------------------------------------------ export
def run_export(db: Session, job: Job):
    rev = db.get(Revision, job.revision_id)
    project = db.get(Project, job.project_id)
    user = db.get(User, project.owner_id)
    model = ProjectModel.model_validate(rev.model)
    brief = Brief.model_validate(rev.brief)
    p = job.params
    base = sheet_meta(db, project, user, model, brief, rev.sheet_revs, rev.number, rev.created_at)
    sel = [s for s in model.sheets if s.id in p["sheet_ids"]]
    fmt = p["format"]
    _progress(db, job, 0.1, "Composing sheets")
    pname = f"{slug(project.name)}_rev{rev.number}"
    checks: dict = {}
    if fmt in ("pdf", "png"):
        sheets = []
        for sd in sel:
            sheets.append(compose_sheet(model, sd, sheet_meta_for(sd, base, rev.sheet_revs), paper=p.get("paper"),
                                        scale=p.get("scale") if sd.kind not in TABLE_KINDS else None, orientation=p.get("orientation")))
        _progress(db, job, 0.5, "Writing vector PDF")
        pdf = render_pdf(sheets, title=f"{project.name} rev {rev.number}")
        checks = verify_pdf(pdf, sheets)
        if fmt == "pdf":
            data, name, mime = pdf, f"{pname}_{sheets[0].paper if len(set(s.paper for s in sheets)) == 1 else 'mixed'}.pdf", "pdf"
        else:
            import pymupdf
            doc = pymupdf.open(stream=pdf, filetype="pdf")
            pngs = [(s.number, doc[i].get_pixmap(dpi=int(p.get("dpi", 150)), alpha=False).tobytes("png")) for i, s in enumerate(sheets)]
            if len(pngs) == 1:
                data, name = pngs[0][1], f"{pname}_{pngs[0][0]}.png"
            else:
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                    for num, b in pngs:
                        z.writestr(f"{pname}_{num}.png", b)
                data, name = buf.getvalue(), f"{pname}.zip"
            checks = dict(ok=all(b[:8] == b"\x89PNG\r\n\x1a\n" for _, b in pngs), pages=len(pngs))
    elif fmt == "dxf":
        views = []
        for sd in sel:
            sc = 0 if sd.kind in TABLE_KINDS else (p.get("scale") or sd.scale or 100)
            views += build_sheet_views(model, sd, sc or 1, sheet_meta_for(sd, base, rev.sheet_revs))
        _progress(db, job, 0.5, "Writing layered DXF")
        data = render_dxf(views, title=project.name)
        name = f"{pname}_model.dxf"
        checks = verify_dxf(data)
    else:
        raise ServiceError("bad_format", f"Unsupported export format {fmt}")
    if not checks.get("ok"):
        raise ServiceError("export_validation_failed", f"The exported {fmt.upper()} failed validation: {checks}", ["Retry the export"])
    key = storage_key(project.id, rev.id, f"export/{job.id[:8]}_{name}")
    sha, size = storage.put(key, data)
    art = Artifact(project_id=project.id, revision_id=rev.id, job_id=job.id, kind=("zip" if name.endswith(".zip") else fmt), purpose="export",
                   name=name, storage_key=key, size=size, sha256=sha, meta=dict(checks=checks, params=p))
    db.add(art); db.flush()
    job.params = {**p, "artifact_id": art.id}
    job.state, job.progress, job.step = "done", 1.0, "Done"
    db.commit()


def verify_pdf(pdf: bytes, sheets) -> dict:
    import pymupdf
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    ok = doc.page_count == len(sheets)
    sizes = []
    for pg, sh in zip(doc, sheets):
        w_mm, h_mm = pg.rect.width / MM, pg.rect.height / MM
        sizes.append([round(w_mm, 2), round(h_mm, 2)])
        ok = ok and abs(w_mm - sh.size[0]) < 0.3 and abs(h_mm - sh.size[1]) < 0.3
    return dict(ok=ok, pages=doc.page_count, page_mm=sizes)


def verify_dxf(data: bytes) -> dict:
    import ezdxf
    from ezdxf import recover
    doc = ezdxf.read(io.StringIO(data.decode("utf-8")))
    aud = doc.audit()
    layers = [l.dxf.name for l in doc.layers]
    ents = len(doc.modelspace())
    return dict(ok=(not aud.errors) and doc.units == 4 and ents > 0 and "A-WALL" in layers, entities=ents, units=doc.units, layers=len(layers), audit_errors=len(aud.errors))


if __name__ == "__main__":
    print("Studio worker running; Ctrl-C to stop")
    start_workers()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_workers()
