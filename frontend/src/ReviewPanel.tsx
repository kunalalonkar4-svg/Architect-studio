import { useEffect, useState } from "react";
import { api, Full } from "./api";
import { ErrorBox, Notice, Spinner, toNotice } from "./ui";

interface Item { code: string; status: "ok" | "warn" | "fail" | "info"; title: string; detail: string; objects: string[]; fix: string }
interface Review {
  revision: number; counts: Record<string, number>; disclaimer: string;
  planning: { measured: Record<string, number>; items: Item[] };
  vastu: { score: number | null; items: Item[]; note: string };
  light_ventilation: { items: Item[] };
  grid: { longest_span_m: number; columns: { x: number; y: number }[]; items: Item[]; note: string };
}
const MARK: Record<Item["status"], string> = { ok: "✓", warn: "!", fail: "✕", info: "i" };
const WORD: Record<Item["status"], string> = { ok: "Fine", warn: "Check", fail: "Over limit", info: "Note" };

function Rows({ items }: { items: Item[] }) {
  if (!items.length) return <p className="muted">Nothing to report.</p>;
  return <ul className="rv-list">{items.map((i, n) => (
    <li key={i.code + n} className={"rv " + i.status}>
      <span className="rv-mark" aria-label={WORD[i.status]} title={WORD[i.status]}>{MARK[i.status]}</span>
      <div><strong>{i.title}</strong>{i.detail && <small>{i.detail}</small>}{i.fix && <small className="rv-fix">Fix: {i.fix}</small>}</div>
    </li>))}</ul>;
}

export default function ReviewPanel({ full }: { full: Full }) {
  const pid = full.project.id; const revId = full.current?.id; const key = `drafta.limits.${pid}`;
  const [lim, setLim] = useState<{ far: string; coverage: string; height: string }>(() => {
    try { return { far: "", coverage: "", height: "", ...JSON.parse(localStorage.getItem(key) || "{}") }; } catch { return { far: "", coverage: "", height: "" }; }
  });
  const [d, setD] = useState<Review | null>(null); const [err, setErr] = useState<Notice | null>(null);

  useEffect(() => { try { localStorage.setItem(key, JSON.stringify(lim)); } catch { /* ignore */ } }, [lim, key]);
  useEffect(() => {
    if (!revId) { setD(null); return; }
    let off = false; setErr(null);
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(lim)) if (v.trim() !== "" && !isNaN(parseFloat(v))) q.set(k, v);
    const t = setTimeout(() => api<Review>(`/projects/${pid}/review?${q}`).then(x => !off && setD(x)).catch(e => !off && setErr(toNotice(e))), 300);
    return () => { off = true; clearTimeout(t); };
  }, [pid, revId, lim]);

  if (!full.current) return <div className="empty-pane"><h3>Nothing to review yet</h3><p className="muted">Generate the drawings first. The review reads the same model as the drawings.</p></div>;
  const m = d?.planning.measured;
  const field = (id: "far" | "coverage" | "height", label: string, hint: string) => (
    <label>{label}<small> {hint}</small><input inputMode="decimal" value={lim[id]} placeholder="not set" onChange={e => setLim(p => ({ ...p, [id]: e.target.value }))} /></label>
  );
  return (
    <div className="panel">
      <h3>Design review · revision {d?.revision ?? full.current.number}</h3>
      <div className="banner warn slim">Advisory checks on a concept drawing. They do not replace your local authority or a licensed architect and engineer.</div>
      <ErrorBox n={err} />
      {!d && !err && <Spinner label="Reviewing…" />}
      {d && <>
        <div className="grid2" role="group" aria-label="Summary">
          <div className="stat"><small>Over limit</small><b>{d.counts.fail}</b></div><div className="stat"><small>To check</small><b>{d.counts.warn}</b></div>
          <div className="stat"><small>Fine</small><b>{d.counts.ok}</b></div><div className="stat"><small>Vastu score</small><b>{d.vastu.score ?? "–"}{d.vastu.score != null && "/100"}</b></div>
        </div>

        <h4>Planning limits</h4>
        <p className="fine">Enter the limits from your own authority's rules. Nothing is guessed for your city.</p>
        <div className="grid2">
          {field("far", "Maximum FAR", "(e.g. 1.75)")}{field("coverage", "Maximum ground coverage %", "")}{field("height", "Maximum height (m)", "")}
        </div>
        {m && <div className="grid2">
          <div className="stat"><small>Plot</small><b>{m.plot_area_m2} m²</b><small>{m.plot_area_sqft} sq ft</small></div>
          <div className="stat"><small>FAR</small><b>{m.far}</b></div>
          <div className="stat"><small>Ground coverage</small><b>{m.coverage_pct}%</b></div>
          <div className="stat"><small>Height with parapet</small><b>{m.height_m} m</b></div>
        </div>}
        <Rows items={d.planning.items} />

        <h4>Vastu</h4>
        <Rows items={d.vastu.items} />
        <p className="fine">{d.vastu.note}</p>

        <h4>Light and ventilation</h4>
        <Rows items={d.light_ventilation.items} />

        <h4>Column grid</h4>
        <p className="fine">{d.grid.columns.length} columns · longest span {d.grid.longest_span_m} m</p>
        <Rows items={d.grid.items} />
        <p className="fine">{d.grid.note}</p>
        <p className="fine">{d.disclaimer}</p>
      </>}
    </div>
  );
}
