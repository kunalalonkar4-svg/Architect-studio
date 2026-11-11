import { useCallback, useEffect, useRef, useState } from "react";
import { api, download, fetchBlobUrl, Full, Revision, Sheet } from "./api";
import { ErrorBox, Notice, Spinner, toNotice } from "./ui";

/** Sheet viewer: tabs, zoom/pan (wheel, drag, pinch, keyboard), fit page, per-sheet settings and downloads. */
export default function Viewer({ full, reload, revision, label }: { full: Full; reload: () => Promise<void>; revision?: Revision | null; label?: string }) {
  const rev = revision ?? full.current;
  const sheets = rev?.sheets ?? [];
  const [sel, setSel] = useState<string | null>(null);
  const sheet = sheets.find(s => s.id === sel) ?? sheets[0];
  const [err, setErr] = useState<Notice | null>(null);
  const job = full.jobs.find(j => j.kind === "render" && rev && j.revision_id === rev.id && (j.state === "queued" || j.state === "running"));

  useEffect(() => { if (sel && !sheets.find(s => s.id === sel)) setSel(null); }, [rev?.id]);

  if (!rev) return (
    <div className="empty-pane">
      <h3>No drawing yet</h3>
      <p className="muted">Describe your plot and rooms in the chat. Once the brief is complete (or you accept labelled assumptions) a dimensioned plan appears here.</p>
    </div>
  );
  const failed = rev.render_status === "failed";
  return (
    <div className="viewer">
      {label && <div className="vlabel">{label}</div>}
      <div className="tabs" role="tablist" aria-label="Drawing sheets">
        {sheets.map(s => <button key={s.id} role="tab" aria-selected={s.id === sheet?.id} className={s.id === sheet?.id ? "on" : ""} onClick={() => setSel(s.id)} title={s.title}>
          <b>{s.number}</b><small>{s.title.replace(/ Plan$/, "")}</small></button>)}
      </div>
      {failed && !revision && (
        <div className="errbox"><div className="errmsg">Drawing failed to render for revision {rev.number}{rev.render_error?.message ? `: ${rev.render_error.message}` : "."}</div>
          <div className="muted">Your model is saved.{full.last_good ? ` Showing the last good drawing is available in Revisions (revision ${full.last_good.number}).` : ""}</div>
          <div className="row"><button className="btn sm" onClick={async () => { try { await api(`/revisions/${rev.id}/retry-render`, { method: "POST" }); await reload(); } catch (e) { setErr(toNotice(e)); } }}>Retry rendering</button></div></div>
      )}
      {job && !revision && <div className="progress" role="progressbar" aria-valuenow={Math.round(job.progress * 100)} aria-valuemin={0} aria-valuemax={100} aria-label="Drawing progress">
        <div style={{ width: `${Math.max(5, job.progress * 100)}%` }} /><span>{job.step || "Rendering drawings…"}</span></div>}
      <ErrorBox n={err} onClose={() => setErr(null)} />
      {sheet && <SheetView key={sheet.id + rev.id} sheet={sheet} pid={full.project.id} rev={rev} readOnly={!!revision || full.project.status === "archived"} reload={reload} setErr={setErr} />}
    </div>
  );
}

function SheetView({ sheet, rev, readOnly, reload, setErr, pid }: { sheet: Sheet; rev: Revision; readOnly: boolean; reload: () => Promise<void>; setErr: (n: Notice | null) => void; pid: string }) {
  const [url, setUrl] = useState<string | null>(null); const [loadErr, setLoadErr] = useState<Notice | null>(null);
  const [nat, setNat] = useState<{ w: number; h: number } | null>(null);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const box = useRef<HTMLDivElement>(null);
  const svgId = sheet.artifacts.svg;

  useEffect(() => {
    let off = false, u: string | null = null; setUrl(null); setLoadErr(null); setNat(null);
    if (svgId) fetchBlobUrl(`/artifacts/${svgId}/file`).then(x => { if (off) URL.revokeObjectURL(x); else { u = x; setUrl(x); } }).catch(e => !off && setLoadErr(toNotice(e)));
    return () => { off = true; if (u) URL.revokeObjectURL(u); };
  }, [svgId]);

  const fit = useCallback(() => {
    const b = box.current; if (!b || !nat) return;
    const k = Math.min(b.clientWidth / nat.w, b.clientHeight / nat.h) * 0.96;
    setView({ k, x: (b.clientWidth - nat.w * k) / 2, y: Math.max(8, (b.clientHeight - nat.h * k) / 2) });
  }, [nat]);
  useEffect(fit, [fit]);
  useEffect(() => { const b = box.current; if (!b) return; const ro = new ResizeObserver(fit); ro.observe(b); return () => ro.disconnect(); }, [fit]);

  const zoomAt = (f: number, cx?: number, cy?: number) => setView(v => {
    const b = box.current!; const px = cx ?? b.clientWidth / 2, py = cy ?? b.clientHeight / 2;
    const k = Math.min(40, Math.max(0.05, v.k * f)); const r = k / v.k;
    return { k, x: px - (px - v.x) * r, y: py - (py - v.y) * r };
  });
  const pts = useRef(new Map<number, { x: number; y: number }>()); const last = useRef<{ d: number } | null>(null);
  function down(e: React.PointerEvent) { (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); pts.current.set(e.pointerId, { x: e.clientX, y: e.clientY }); last.current = null; }
  function move(e: React.PointerEvent) {
    const p = pts.current.get(e.pointerId); if (!p) return;
    const rect = box.current!.getBoundingClientRect();
    if (pts.current.size === 1) { setView(v => ({ ...v, x: v.x + e.clientX - p.x, y: v.y + e.clientY - p.y })); }
    pts.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pts.current.size === 2) {
      const [a, b] = Array.from(pts.current.values()); const d = Math.hypot(a.x - b.x, a.y - b.y);
      if (last.current) zoomAt(d / last.current.d, (a.x + b.x) / 2 - rect.left, (a.y + b.y) / 2 - rect.top);
      last.current = { d };
    }
  }
  const up = (e: React.PointerEvent) => { pts.current.delete(e.pointerId); last.current = null; };
  useEffect(() => {
    const b = box.current; if (!b) return;
    const w = (e: WheelEvent) => { e.preventDefault(); const r = b.getBoundingClientRect(); zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top); };
    b.addEventListener("wheel", w, { passive: false }); return () => b.removeEventListener("wheel", w);
  }, []);
  function key(e: React.KeyboardEvent) {
    const s = 60;
    if (e.key === "+" || e.key === "=") zoomAt(1.25); else if (e.key === "-") zoomAt(1 / 1.25); else if (e.key === "0") fit();
    else if (e.key === "ArrowLeft") setView(v => ({ ...v, x: v.x + s })); else if (e.key === "ArrowRight") setView(v => ({ ...v, x: v.x - s }));
    else if (e.key === "ArrowUp") setView(v => ({ ...v, y: v.y + s })); else if (e.key === "ArrowDown") setView(v => ({ ...v, y: v.y - s }));
    else return;
    e.preventDefault();
  }
  async function dl(kind: "pdf" | "png") {
    const id = sheet.artifacts[kind]; if (!id) return;
    try { await download(`/artifacts/${id}/file`, `${sheet.number}-r${sheet.rev}.${kind}`); } catch (e) { setErr(toNotice(e)); }
  }
  async function patch(b: Record<string, unknown>) {
    setErr(null);
    try { await api(`/projects/${pid}/sheets/${sheet.id}`, { method: "PATCH", json: b }); await reload(); } catch (e) { setErr(toNotice(e)); }
  }
  const fixed = sheet.kind === "index" || sheet.kind === "schedules";
  return (
    <>
      <div className="vbar">
        <div className="vmeta"><strong>{sheet.number} · {sheet.title}</strong><small>{sheet.paper} {sheet.orientation}{sheet.scale ? ` · 1:${sheet.scale}` : ""} · sheet rev {sheet.rev}</small></div>
        <div className="vtools" role="toolbar" aria-label="Viewer tools">
          <button className="btn sm" onClick={() => zoomAt(1 / 1.25)} aria-label="Zoom out">−</button>
          <button className="btn sm" onClick={() => zoomAt(1.25)} aria-label="Zoom in">+</button>
          <button className="btn sm" onClick={fit}>Fit page</button>
          <button className="btn sm" onClick={() => dl("pdf")} disabled={!sheet.artifacts.pdf}>PDF</button>
          <button className="btn sm" onClick={() => dl("png")} disabled={!sheet.artifacts.png}>PNG</button>
        </div>
      </div>
      <div className="canvas" ref={box} tabIndex={0} role="img" aria-label={`${sheet.number} ${sheet.title}. Arrow keys pan, plus and minus zoom, 0 fits the page.`}
        onKeyDown={key} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} onDoubleClick={fit}>
        {!svgId && <div className="center"><Spinner label="Drawing is being prepared…" /></div>}
        {loadErr && <div className="center"><ErrorBox n={loadErr} /></div>}
        {url && <img src={url} alt="" draggable={false} onLoad={e => setNat({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
          style={{ transform: `translate(${view.x}px,${view.y}px) scale(${view.k})`, width: nat?.w, height: nat?.h, opacity: nat ? 1 : 0 }} />}
      </div>
      {!readOnly && (
        <details className="sheet-set"><summary>Sheet settings</summary>
          <div className="grid2">
            <label>Paper<select value={sheet.paper} onChange={e => patch({ paper: e.target.value })}>{["A4", "A3", "A2", "A1", "A0"].map(p => <option key={p}>{p}</option>)}</select></label>
            <label>Scale<select value={sheet.scale} disabled={fixed} onChange={e => patch({ scale: +e.target.value })}>{fixed ? <option value={sheet.scale}>n/a</option> : [20, 25, 50, 100, 200, 500].map(s => <option key={s} value={s}>1:{s}</option>)}</select></label>
            <label>Orientation<select value={sheet.orientation} onChange={e => patch({ orientation: e.target.value })}><option>landscape</option><option>portrait</option></select></label>
          </div>
          <small className="muted">If content does not fit, you’ll get options: larger paper, smaller scale or splitting the sheet. Existing drawings are kept.</small>
        </details>
      )}
      {rev.validation && rev.validation.filter(i => i.severity !== "info").length > 0 && (
        <details className="sheet-set"><summary>Checks ({rev.validation.filter(i => i.severity !== "info").length})</summary>
          <ul className="issues">{rev.validation.filter(i => i.severity !== "info").map((i, k) => <li key={k} className={"sev-" + i.severity}>{i.message}{i.fix && <small> Next: {i.fix}</small>}</li>)}</ul></details>
      )}
    </>
  );
}
