import { useState } from "react";
import { api, Full } from "./api";
import Viewer from "./Viewer";
import { ago, ErrorBox, Notice, Spinner, toNotice } from "./ui";

export default function Revisions({ full, reload, goTab }: { full: Full; reload: () => Promise<void>; goTab: (t: string) => void }) {
  const revs = [...full.revisions].reverse();
  const [a, setA] = useState<string>(""); const [b, setB] = useState<string>("");
  const [cmp, setCmp] = useState<any>(null); const [busy, setBusy] = useState(false); const [err, setErr] = useState<Notice | null>(null);
  const [mode, setMode] = useState<"changes" | "side" | "overlay">("changes"); const [sheetNo, setSheetNo] = useState<string>("");
  const [opacity, setOpacity] = useState(0.5);

  async function restore(id: string) {
    setBusy(true); setErr(null);
    try { await api(`/revisions/${id}/restore`, { method: "POST" }); await reload(); goTab("drawing"); } catch (e) { setErr(toNotice(e)); } finally { setBusy(false); }
  }
  async function compare() {
    setBusy(true); setErr(null); setCmp(null);
    try { const r = await api(`/projects/${full.project.id}/compare?a=${a}&b=${b}`); setCmp(r); setSheetNo(r.b.sheets?.[0]?.number ?? ""); } catch (e) { setErr(toNotice(e)); } finally { setBusy(false); }
  }
  if (!revs.length) return <div className="empty-pane"><h3>No revisions yet</h3><p className="muted">Every confirmed change saves a numbered revision you can compare and restore.</p></div>;
  return (
    <div className="panel">
      <h3>Revisions</h3>
      <ErrorBox n={err} onClose={() => setErr(null)} />
      <ul className="revlist">
        {revs.map(r => (
          <li key={r.id} className={r.id === full.current?.id ? "cur" : ""}>
            <div><strong>Rev {r.number}</strong> {r.id === full.current?.id && <span className="tag">current</span>} <span className={"tag " + r.render_status}>{r.render_status}</span>
              <div>{r.summary}</div><small className="muted">{ago(r.created_at)}</small></div>
            <div className="row">
              {r.id !== full.current?.id && <button className="btn sm" disabled={busy || full.project.status === "archived"} onClick={() => restore(r.id)}>Restore</button>}
              {r.render_status === "failed" && <button className="btn sm" onClick={async () => { try { await api(`/revisions/${r.id}/retry-render`, { method: "POST" }); await reload(); } catch (e) { setErr(toNotice(e)); } }}>Retry render</button>}
            </div>
          </li>
        ))}
      </ul>
      {revs.length > 1 && (
        <>
          <h3>Compare</h3>
          <div className="grid2">
            <label>From<select value={a} onChange={e => setA(e.target.value)}><option value="">Choose…</option>{full.revisions.map(r => <option key={r.id} value={r.id}>Rev {r.number}</option>)}</select></label>
            <label>To<select value={b} onChange={e => setB(e.target.value)}><option value="">Choose…</option>{full.revisions.map(r => <option key={r.id} value={r.id}>Rev {r.number}</option>)}</select></label>
          </div>
          <button className="btn" disabled={!a || !b || a === b || busy} onClick={compare}>{busy ? <Spinner label="Comparing…" /> : "Compare"}</button>
          {a && a === b && <small className="muted"> Pick two different revisions.</small>}
          {cmp && (
            <div className="cmp">
              <div className="seg"><button className={mode === "changes" ? "on" : ""} onClick={() => setMode("changes")}>Changes</button><button className={mode === "side" ? "on" : ""} onClick={() => setMode("side")}>Side by side</button><button className={mode === "overlay" ? "on" : ""} onClick={() => setMode("overlay")}>Overlay</button></div>
              {mode === "changes" && (
                <>
                  <h4>Model changes</h4>
                  {cmp.changes.length === 0 ? <p className="muted">No geometry or schedule differences.</p> : <ul>{cmp.changes.map((c: any, i: number) => <li key={i}>{c.text}</li>)}</ul>}
                  <h4>Sheets that differ</h4>
                  {cmp.sheets_changed.length === 0 ? <p className="muted">All sheets are identical.</p> : <ul>{cmp.sheets_changed.map((s: any) => <li key={s.id}><b>{s.number}</b> {s.title} — {s.status}</li>)}</ul>}
                </>
              )}
              {mode !== "changes" && (
                <>
                  <label>Sheet<select value={sheetNo} onChange={e => setSheetNo(e.target.value)}>{cmp.b.sheets.map((s: any) => <option key={s.id} value={s.number}>{s.number} {s.title}</option>)}</select></label>
                  <CompareSheets cmp={cmp} number={sheetNo} mode={mode} opacity={opacity} setOpacity={setOpacity} full={full} reload={reload} />
                </>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function CompareSheets({ cmp, number, mode, opacity, setOpacity, full, reload }: { cmp: any; number: string; mode: string; opacity: number; setOpacity: (n: number) => void; full: Full; reload: () => Promise<void> }) {
  const sa = cmp.a.sheets.find((s: any) => s.number === number), sb = cmp.b.sheets.find((s: any) => s.number === number);
  if (!sb) return null;
  const ra = { ...cmp.a, sheets: sa ? [sa] : [] }, rb = { ...cmp.b, sheets: [sb] };
  if (mode === "side") return (
    <div className="side">
      <div>{sa ? <Viewer full={full} reload={reload} revision={ra} label={`Rev ${cmp.a.number}`} /> : <p className="muted">Sheet {number} did not exist in Rev {cmp.a.number}.</p>}</div>
      <div><Viewer full={full} reload={reload} revision={rb} label={`Rev ${cmp.b.number}`} /></div>
    </div>
  );
  return (
    <div>
      <label>Rev {cmp.a.number} opacity<input type="range" min={0} max={1} step={0.05} value={opacity} onChange={e => setOpacity(+e.target.value)} /></label>
      <div className="overlay"><OverlayImg id={sb.artifacts.svg} o={1} /><OverlayImg id={sa?.artifacts.svg} o={opacity} tint /></div>
      <small className="muted">Rev {cmp.b.number} in black, Rev {cmp.a.number} tinted red on top. Differences show where they do not coincide.</small>
    </div>
  );
}
import { useEffect } from "react";
import { fetchBlobUrl } from "./api";
function OverlayImg({ id, o, tint }: { id?: string; o: number; tint?: boolean }) {
  const [u, setU] = useState<string | null>(null);
  useEffect(() => { let off = false, x: string | null = null; setU(null); if (id) fetchBlobUrl(`/artifacts/${id}/file`).then(v => { if (off) URL.revokeObjectURL(v); else { x = v; setU(v); } }).catch(() => undefined); return () => { off = true; if (x) URL.revokeObjectURL(x); }; }, [id]);
  if (!u) return null;
  return <img src={u} alt="" style={{ opacity: o, mixBlendMode: tint ? "multiply" : "normal", filter: tint ? "sepia(1) saturate(8) hue-rotate(-30deg)" : undefined }} />;
}
