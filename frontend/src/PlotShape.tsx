import { useState } from "react";
import { api, Full } from "./api";
import { ErrorBox, Notice, toNotice } from "./ui";

const F = { ft: 304.8, m: 1000 } as const;

function parse(text: string, unit: keyof typeof F): number[][] | string {
  const rows = text.split(/\n/).map(l => l.trim()).filter(Boolean);
  const out: number[][] = [];
  for (const [i, r] of rows.entries()) {
    const n = r.split(/[\s,;]+/).filter(Boolean).map(Number);
    if (n.length !== 2 || n.some(v => !isFinite(v))) return `Line ${i + 1}: write two numbers, like 0, 0`;
    out.push([n[0] * F[unit], n[1] * F[unit]]);
  }
  return out.length < 3 ? "Enter at least three corners, one per line." : out;
}

function Preview({ pts }: { pts: number[][] }) {
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]); const x0 = Math.min(...xs), y0 = Math.min(...ys); const w = Math.max(...xs) - x0 || 1, h = Math.max(...ys) - y0 || 1;
  const pad = Math.max(w, h) * 0.08; const d = pts.map(p => `${p[0] - x0},${h - (p[1] - y0)}`).join(" ");
  return <svg className="ps-prev" viewBox={`${-pad} ${-pad} ${w + 2 * pad} ${h + 2 * pad}`} role="img" aria-label="Plot outline preview (north is up)"><polygon points={d} fill="#dfe9d2" stroke="#222" strokeWidth={Math.max(w, h) / 120} /></svg>;
}

export default function PlotShape({ full, reload, goTab }: { full: Full; reload: () => Promise<void>; goTab: (t: string) => void }) {
  const cur: number[][] | null = full.brief.plot_polygon_mm ?? null; const road = full.brief.road_side;
  const [open, setOpen] = useState(!!cur); const [unit, setUnit] = useState<keyof typeof F>("ft");
  const [text, setText] = useState(() => cur ? cur.map(p => `${+(p[0] / 304.8).toFixed(2)}, ${+(p[1] / 304.8).toFixed(2)}`).join("\n") : "");
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<Notice | null>(null); const [msg, setMsg] = useState("");
  const parsed = parse(text, unit); const pts = Array.isArray(parsed) ? parsed : null;
  async function send(body: unknown) {
    setBusy(true); setErr(null); setMsg("");
    try {
      const r = await api(`/projects/${full.project.id}/plot-shape`, { method: "PUT", json: body });
      await reload();
      if (r.result?.proposal_id) goTab("chat"); else setMsg("Plot shape saved.");
    } catch (e) { setErr(toNotice(e)); } finally { setBusy(false); }
  }
  if (!open) return <button className="btn link" onClick={() => setOpen(true)}>My plot is not a rectangle</button>;
  return (
    <fieldset className="plotshape"><legend>Plot shape (irregular plot)</legend>
      <p className="fine">Enter each corner of the plot, one per line, going around the plot. x is towards east and y is towards north, measured from any corner. Convex shapes only (trapezium, angled corner, kite). The house is fitted in the largest rectangle that stays inside after your open-space values. Boundary lengths come only from what you enter, not a survey.</p>
      {!road && <div className="note err">Choose which side faces the road first.</div>}
      <label className="inl">Units<select value={unit} onChange={e => setUnit(e.target.value as keyof typeof F)}><option value="ft">feet</option><option value="m">metres</option></select></label>
      <textarea rows={5} value={text} onChange={e => setText(e.target.value)} placeholder={"0, 0\n36, 0\n33, 50\n3, 50"} aria-label="Plot corners" />
      {text.trim() && !pts && <div className="note err">{parsed as string}</div>}
      {pts && <Preview pts={pts} />}
      <ErrorBox n={err} onClose={() => setErr(null)} />{msg && <div className="note ok" role="status">{msg}</div>}
      <div className="row">
        <button type="button" className="btn primary" disabled={busy || !pts || !road} onClick={() => send({ points_mm: pts })}>Use this plot shape</button>
        {cur && <button type="button" className="btn" disabled={busy} onClick={() => send({ clear: true })}>Back to a rectangle</button>}
        <button type="button" className="btn ghost" onClick={() => setOpen(false)}>Hide</button>
      </div>
      <p className="fine">{full.current ? "Your drawing is not changed until you confirm the proposal in Chat." : "Saved to the brief; generate the drawings next."}</p>
    </fieldset>
  );
}
