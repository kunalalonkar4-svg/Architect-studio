import { useEffect, useState } from "react";
import { api, Full } from "./api";
import { ErrorBox, Notice, toNotice } from "./ui";

type Unit = "mm" | "cm" | "m" | "ft" | "in";
const F: Record<Unit, number> = { mm: 1, cm: 10, m: 1000, ft: 304.8, in: 25.4 };
interface L { v: string; u: Unit }
const fromMm = (mm: number | null | undefined, u: Unit): L => ({ v: mm == null ? "" : String(+(mm / F[u]).toFixed(3)), u });
const VIEWS = ["site", "plan", "roof", "elevations", "section", "structure", "schedules", "index"];
const SIDES: Record<string, string> = { n: "north", e: "east", s: "south", w: "west" };

export default function BriefPanel({ full, reload, goTab }: { full: Full; reload: () => Promise<void>; goTab: (t: string) => void }) {
  const b = full.brief; const sb = b.setbacks ?? {};
  const [dirty, setDirty] = useState<Set<string>>(new Set());
  const [f, setF] = useState(() => init());
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<Notice | null>(null); const [ok, setOk] = useState("");
  const [useAssume, setUseAssume] = useState(full.use_assumptions);
  function init() {
    return {
      frontage: fromMm(b.plot_frontage_mm, "ft"), depth: fromMm(b.plot_depth_mm, "ft"),
      front: fromMm(sb.front, "m"), rear: fromMm(sb.rear, "m"), left: fromMm(sb.left, "m"), right: fromMm(sb.right, "m"),
      road: (b.road_side ? SIDES[b.road_side] ?? b.road_side : "") as string, bedrooms: b.bedrooms == null ? "" : String(b.bedrooms), floors: String(b.levels_now ?? 1), kitchen: (b.kitchen_type ?? "") as string,
      parking: b.parking == null ? "" : b.parking ? "yes" : "no", stairPos: (b.stair_position ?? "front") as string, views: (b.requested_views ?? ["plan"]) as string[], notes: (b.notes ?? "") as string,
    };
  }
  useEffect(() => { setF(init()); setDirty(new Set()); setOk(""); }, [full.project.id, JSON.stringify(full.brief)]);
  const set = (k: string, v: any) => { setF(p => ({ ...p, [k]: v })); setDirty(d => new Set(d).add(k)); setOk(""); };
  const len = (x: L) => ({ value: parseFloat(x.v), unit: x.u });
  const lenKeys = ["frontage", "depth", "front", "rear", "left", "right"] as const;
  const bad = lenKeys.filter(k => dirty.has(k) && !(parseFloat((f as any)[k].v) >= 0));

  async function save() {
    const p: any = {}; setErr(null); setOk("");
    if (dirty.has("frontage")) p.plot_frontage = len(f.frontage);
    if (dirty.has("depth")) p.plot_depth = len(f.depth);
    for (const k of ["front", "rear", "left", "right"] as const) if (dirty.has(k)) p["setback_" + k] = len(f[k]);
    if (dirty.has("road") && f.road) p.road_side = f.road;
    if (dirty.has("bedrooms") && f.bedrooms !== "") p.bedrooms = parseInt(f.bedrooms, 10);
    if (dirty.has("floors")) p.floors = parseInt(f.floors, 10);
    if (dirty.has("kitchen") && f.kitchen) p.kitchen_type = f.kitchen;
    if (dirty.has("parking") && f.parking) p.parking = f.parking === "yes";
    if (dirty.has("stairPos")) p.stair_position = f.stairPos;
    if (dirty.has("views")) p.requested_views = f.views;
    if (dirty.has("notes")) p.notes = f.notes;
    if (dirty.has("frontage") || dirty.has("depth")) p.dims_orientation_assumed = false;
    if (!Object.keys(p).length) { setOk("Nothing changed."); return; }
    setBusy(true);
    try {
      const r = await api(`/projects/${full.project.id}/brief`, { method: "PUT", json: p });
      await reload();
      const proposed = (r.events ?? []).some((e: any) => e.type === "proposal");
      setOk(proposed ? "Saved as a proposed change. Review it in the chat and confirm to create a revision." : "Brief saved.");
      if (proposed) goTab("chat");
    } catch (e) { setErr(toNotice(e)); } finally { setBusy(false); }
  }
  async function generate() {
    setBusy(true); setErr(null); setOk("");
    try { await api(`/projects/${full.project.id}/generate`, { json: { use_assumptions: useAssume } }); await reload(); goTab("drawing"); }
    catch (e) { setErr(toNotice(e)); } finally { setBusy(false); }
  }
  const ro = full.project.status === "archived";
  const has = !!full.current;
  const Len = ({ k, label, hint }: { k: typeof lenKeys[number]; label: string; hint?: string }) => (
    <label>{label}{hint && <small> {hint}</small>}
      <span className="lenrow"><input inputMode="decimal" disabled={ro} value={f[k].v} aria-invalid={bad.includes(k)} onChange={e => set(k, { ...f[k], v: e.target.value })} />
        <select disabled={ro} aria-label={`${label} unit`} value={f[k].u} onChange={e => { const u = e.target.value as Unit; const mm = parseFloat(f[k].v) * F[f[k].u]; set(k, isFinite(mm) ? fromMm(mm, u) : { ...f[k], u }); }}>
          {(["ft", "in", "m", "cm", "mm"] as Unit[]).map(u => <option key={u}>{u}</option>)}</select></span></label>
  );
  return (
    <div className="panel">
      <h3>Project brief</h3>
      {full.missing.length > 0
        ? <div className="banner warn"><strong>Still needed:</strong><ul>{full.missing.map(m => <li key={m.id}>{m.question}</li>)}</ul></div>
        : <div className="banner ok">Brief is complete.</div>}
      {b.dims_assumed_orientation && <div className="banner warn">“30 by 50” was read as 30 along the road and 50 deep. Edit the sizes below if that is wrong.</div>}
      <fieldset disabled={ro}><legend>Plot</legend>
        <div className="grid2"><Len k="frontage" label="Frontage (along road)" /><Len k="depth" label="Depth" /></div>
        <label>Road is on the<select value={f.road} onChange={e => set("road", e.target.value)}><option value="">Choose…</option>{["north", "east", "south", "west"].map(s => <option key={s}>{s}</option>)}</select></label>
      </fieldset>
      <fieldset disabled={ro}><legend>Required open space / setbacks</legend>
        <small className="muted">Enter values from your local rules. If you leave them blank you can proceed with labelled concept assumptions.</small>
        <div className="grid2"><Len k="front" label="Front" /><Len k="rear" label="Rear" /><Len k="left" label="Left" /><Len k="right" label="Right" /></div>
      </fieldset>
      <fieldset disabled={ro}><legend>Rooms</legend>
        <div className="grid2">
          <label>Bedrooms<select value={f.bedrooms} onChange={e => set("bedrooms", e.target.value)}><option value="">Choose…</option>{[1, 2, 3, 4, 5].map(n => <option key={n}>{n}</option>)}</select></label>
          <label>Floors<select value={f.floors} onChange={e => set("floors", e.target.value)}><option value="1">1 (ground only)</option><option value="2">2 (duplex: ground + first)</option></select></label>
          <label>Kitchen<select value={f.kitchen} onChange={e => set("kitchen", e.target.value)}><option value="">Choose…</option><option value="open">Open</option><option value="closed">Closed</option></select></label>
          <label>Parking<select value={f.parking} onChange={e => set("parking", e.target.value)}><option value="">Choose…</option><option value="yes">Yes</option><option value="no">No</option></select></label>
          <label>Staircase<select value={f.stairPos} onChange={e => set("stairPos", e.target.value)}><option value="front">Front</option><option value="rear">Rear</option></select></label>
        </div>
      </fieldset>
      <fieldset disabled={ro}><legend>Drawings to produce</legend>
        <div className="checks">{VIEWS.map(v => <label key={v} className="check"><input type="checkbox" checked={f.views.includes(v)} onChange={e => set("views", e.target.checked ? [...f.views, v] : f.views.filter(x => x !== v))} /> {v}</label>)}</div>
      </fieldset>
      <label>Notes<textarea rows={2} disabled={ro} value={f.notes} onChange={e => set("notes", e.target.value)} maxLength={2000} /></label>
      {b.assumptions?.length > 0 && <div className="assume"><strong>Assumptions &amp; open items</strong><ul>{b.assumptions.map((a: any) => <li key={a.id}><span className={"tag " + a.kind}>{a.kind}</span> {a.text}</li>)}</ul></div>}
      <ErrorBox n={err} onClose={() => setErr(null)} />
      {bad.length > 0 && <div className="note err">Enter a number for: {bad.join(", ")}.</div>}
      {ok && <div className="note ok" role="status">{ok}</div>}
      <div className="row">
        <button className="btn" disabled={busy || ro || dirty.size === 0 || bad.length > 0} onClick={save}>Save brief</button>
        {!has && <>
          <label className="check"><input type="checkbox" checked={useAssume} onChange={e => setUseAssume(e.target.checked)} /> Proceed with labelled concept assumptions</label>
          <button className="btn primary" disabled={busy || ro || dirty.size > 0 || (full.missing.length > 0 && !useAssume && full.missing.some(m => m.id !== "setbacks"))} onClick={generate}>Generate drawings</button>
        </>}
      </div>
      {!has && dirty.size > 0 && <small className="muted">Save the brief before generating.</small>}
      {has && !ro && <QuickEdits full={full} reload={reload} goTab={goTab} />}
    </div>
  );
}

function QuickEdits({ full, reload, goTab }: { full: Full; reload: () => Promise<void>; goTab: (t: string) => void }) {
  const ops = full.current?.model_summary?.openings ?? [];
  const [mark, setMark] = useState(""); const [w, setW] = useState(""); const [err, setErr] = useState<Notice | null>(null); const [busy, setBusy] = useState(false);
  const cur = ops.find((o: any) => o.mark === mark);
  async function submit(summary: string, edits: any[]) {
    setBusy(true); setErr(null);
    try { await api(`/projects/${full.project.id}/edits`, { json: { summary, edits } }); await reload(); goTab("chat"); } catch (e) { setErr(toNotice(e)); } finally { setBusy(false); }
  }
  return (
    <details className="quick"><summary>Quick edits (proposed first, saved only when you confirm)</summary>
      <div className="grid2">
        <label>Opening<select value={mark} onChange={e => { setMark(e.target.value); setW(String(ops.find((o: any) => o.mark === e.target.value)?.width ?? "")); }}><option value="">Choose…</option>{ops.map((o: any) => <option key={o.mark} value={o.mark}>{o.mark} · {o.type} · {Math.round(o.width)} mm</option>)}</select></label>
        <label>New width (mm)<input inputMode="numeric" value={w} onChange={e => setW(e.target.value)} disabled={!mark} /></label>
      </div>
      <button className="btn sm" disabled={!mark || !(parseFloat(w) > 0) || busy || parseFloat(w) === cur?.width} onClick={() => submit(`Change ${mark} width to ${w} mm`, [{ op: "set_opening", mark, width: { value: parseFloat(w), unit: "mm" } }])}>Propose opening change</button>
      <div className="row"><span>Move stair to</span>
        <button className="btn sm" disabled={busy} onClick={() => submit("Move the staircase to the front", [{ op: "move_stair", position: "front" }])}>Front</button>
        <button className="btn sm" disabled={busy} onClick={() => submit("Move the staircase to the rear", [{ op: "move_stair", position: "rear" }])}>Rear</button></div>
      <ErrorBox n={err} onClose={() => setErr(null)} />
    </details>
  );
}
