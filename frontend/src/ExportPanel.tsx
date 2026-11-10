import { useState } from "react";
import { api, download, Full, Job } from "./api";
import { ErrorBox, Notice, kb, toNotice } from "./ui";

export default function ExportPanel({ full, reload }: { full: Full; reload: () => Promise<void> }) {
  const sheets = full.current?.sheets ?? [];
  const [fmt, setFmt] = useState<"pdf" | "dxf" | "png">("pdf");
  const [pick, setPick] = useState<Set<string>>(new Set());
  const [paper, setPaper] = useState(""); const [scale, setScale] = useState(""); const [orient, setOrient] = useState("");
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<Notice | null>(null);
  const exports = full.jobs.filter(j => j.kind === "export");
  if (!full.current) return <div className="empty-pane"><h3>Nothing to export yet</h3><p className="muted">Generate drawings first.</p></div>;
  async function start() {
    setBusy(true); setErr(null);
    try {
      const body: any = { format: fmt, sheet_ids: [...pick] };
      if (paper && fmt !== "dxf") body.paper = paper; if (scale && fmt !== "dxf") body.scale = +scale; if (orient && fmt !== "dxf") body.orientation = orient;
      await api(`/projects/${full.project.id}/exports`, { json: body }); await reload();
    } catch (e) { setErr(toNotice(e)); } finally { setBusy(false); }
  }
  return (
    <div className="panel">
      <h3>Export revision {full.current.number}</h3>
      <div className="seg" role="radiogroup" aria-label="Format">
        {(["pdf", "dxf", "png"] as const).map(x => <button key={x} role="radio" aria-checked={fmt === x} className={fmt === x ? "on" : ""} onClick={() => setFmt(x)}>{x.toUpperCase()}</button>)}
      </div>
      <p className="muted">{fmt === "pdf" ? "Vector PDF at the exact paper size and drawing scale (print at 100%, no “fit to page”)." : fmt === "dxf" ? "Layered DXF in model space at 1:1, millimetres. Open in any CAD program." : "Raster PNG of each sheet."}</p>
      <fieldset><legend>Sheets</legend>
        <label className="check"><input type="checkbox" checked={pick.size === 0} onChange={() => setPick(new Set())} /> All sheets ({sheets.length})</label>
        {sheets.map(s => <label key={s.id} className="check"><input type="checkbox" checked={pick.has(s.id)} onChange={e => setPick(p => { const n = new Set(p); e.target.checked ? n.add(s.id) : n.delete(s.id); return n; })} /> {s.number} {s.title} <small className="muted">({s.paper} 1:{s.scale || "—"})</small></label>)}
      </fieldset>
      {fmt !== "dxf" && (
        <details><summary>Override paper, scale or orientation</summary>
          <div className="grid2">
            <label>Paper<select value={paper} onChange={e => setPaper(e.target.value)}><option value="">As set per sheet</option>{["A4", "A3", "A2", "A1", "A0"].map(p => <option key={p}>{p}</option>)}</select></label>
            <label>Scale<select value={scale} onChange={e => setScale(e.target.value)}><option value="">As set per sheet</option>{[20, 25, 50, 100, 200, 500].map(s => <option key={s} value={s}>1:{s}</option>)}</select></label>
            <label>Orientation<select value={orient} onChange={e => setOrient(e.target.value)}><option value="">As set per sheet</option><option>landscape</option><option>portrait</option></select></label>
          </div>
        </details>
      )}
      <ErrorBox n={err} onClose={() => setErr(null)} />
      <button className="btn primary" disabled={busy || full.project.status === "archived"} onClick={start}>{busy ? "Starting…" : `Export ${fmt.toUpperCase()}`}</button>
      <h3>Exports</h3>
      {exports.length === 0 && <p className="muted">No exports yet.</p>}
      <ul className="joblist">{exports.map(j => <JobRow key={j.id} j={j} reload={reload} />)}</ul>
    </div>
  );
}

function JobRow({ j, reload }: { j: Job; reload: () => Promise<void> }) {
  const [err, setErr] = useState<Notice | null>(null);
  const running = j.state === "queued" || j.state === "running";
  return (
    <li>
      <div><strong>{String(j.params?.format ?? "").toUpperCase()}</strong> <span className={"tag " + j.state}>{j.state}</span>
        {running && <div className="progress sm"><div style={{ width: `${Math.max(5, j.progress * 100)}%` }} /><span>{j.step}</span></div>}
        {j.state === "failed" && <div className="note err">{j.error || "Export failed."} {j.error_detail?.next_action ?? ""}</div>}
        {j.artifact && <small className="muted"> {j.artifact.name} · {kb(j.artifact.size)}{j.artifact.checks ? " · verified" : ""}</small>}</div>
      <div className="row">
        {j.state === "done" && j.artifact && <button className="btn sm primary" onClick={async () => { try { await download(`/artifacts/${j.artifact!.id}/file`, j.artifact!.name); } catch (e) { setErr(toNotice(e)); } }}>Download</button>}
        {j.state === "failed" && <button className="btn sm" onClick={async () => { try { await api(`/jobs/${j.id}/retry`, { method: "POST" }); await reload(); } catch (e) { setErr(toNotice(e)); } }}>Retry</button>}
      </div>
      <ErrorBox n={err} onClose={() => setErr(null)} />
    </li>
  );
}
