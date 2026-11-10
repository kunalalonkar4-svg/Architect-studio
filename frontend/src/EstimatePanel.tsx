import { useEffect, useMemo, useState } from "react";
import { api, download, Full } from "./api";
import { ErrorBox, Notice, Spinner, toNotice } from "./ui";

interface Item { id: string; name: string; unit: string; qty: number; basis: string }
interface Est { revision: number; currency: string; built_up_m2: number; carpet_m2: number; items: Item[]; rates: Record<string, number>; disclaimer: string }
const inr = (n: number) => "₹ " + Math.round(n).toLocaleString("en-IN");

export default function EstimatePanel({ full }: { full: Full }) {
  const [view, setView] = useState<"cost" | "structure">("cost");
  return (
    <>
      <div className="panel" style={{ paddingBottom: 0 }}>
        <div className="seg" role="tablist" aria-label="Estimate sections">
          <button role="tab" aria-selected={view === "cost"} className={view === "cost" ? "on" : ""} onClick={() => setView("cost")}>Cost (BOQ)</button>
          <button role="tab" aria-selected={view === "structure"} className={view === "structure" ? "on" : ""} onClick={() => setView("structure")}>Structure (prelim.)</button>
        </div>
      </div>
      {view === "cost" ? <CostView full={full} /> : <StructureView full={full} />}
    </>
  );
}

interface SItem { id: string; name: string; value: string; status: string; basis: string; note: string }
interface Struct { revision: number; assumptions: Record<string, any>; items: SItem[]; disclaimer: string }

function StructureView({ full }: { full: Full }) {
  const pid = full.project.id; const revId = full.current?.id;
  const [sbc, setSbc] = useState("150"); const [d, setD] = useState<Struct | null>(null); const [err, setErr] = useState<Notice | null>(null);
  useEffect(() => {
    if (!revId) return; let off = false; setErr(null);
    const t = setTimeout(() => api<Struct>(`/projects/${pid}/structure?sbc=${encodeURIComponent(sbc)}`).then(x => !off && setD(x)).catch(e => !off && setErr(toNotice(e))), 300);
    return () => { off = true; clearTimeout(t); };
  }, [pid, revId, sbc]);
  if (!full.current) return <div className="empty-pane"><h3>No drawing yet</h3><p className="muted">Generate the drawings first.</p></div>;
  return (
    <div className="panel">
      <h3>Preliminary structure · revision {d?.revision ?? full.current.number}</h3>
      <div className="banner warn slim">Rough sizes for early planning only. Not a structural design. A licensed structural engineer must design and check everything.</div>
      <label>Soil safe bearing capacity (kN/m²)<small> — from your soil test; 150 is only an assumption</small><input inputMode="decimal" value={sbc} onChange={e => setSbc(e.target.value)} /></label>
      <ErrorBox n={err} />
      {!d && !err && <Spinner label="Calculating…" />}
      {d && d.items.map(i => (
        <div className="est-row" key={i.id}>
          <div className="est-name"><strong>{i.name}</strong><small>{i.basis}</small>{i.note && <small className={i.status === "check" ? "note warn" : ""}>{i.note}</small>}</div>
          <div className="est-qty">{i.status === "check" ? "⚠ check" : ""}</div><div className="est-amt">{i.value}</div>
        </div>))}
      {d && <><p className="fine"><b>Assumed:</b> {Object.entries(d.assumptions).map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`).join(" · ")}</p><p className="fine">{d.disclaimer}</p></>}
    </div>
  );
}

function CostView({ full }: { full: Full }) {
  const pid = full.project.id; const revId = full.current?.id;
  const [est, setEst] = useState<Est | null>(null); const [err, setErr] = useState<Notice | null>(null);
  const [rates, setRates] = useState<Record<string, string>>({}); const [cont, setCont] = useState("10");
  const key = `drafta.rates.${pid}`;

  useEffect(() => {
    if (!revId) { setEst(null); return; }
    let off = false; setErr(null);
    api<Est>(`/projects/${pid}/estimate`).then(e => {
      if (off) return; setEst(e);
      let saved: Record<string, string> = {}; try { saved = JSON.parse(localStorage.getItem(key) || "{}"); } catch { /* ignore */ }
      setRates(Object.fromEntries(Object.entries(e.rates).map(([k, v]) => [k, saved[k] ?? String(v)])));
    }).catch(e => !off && setErr(toNotice(e)));
    return () => { off = true; };
  }, [pid, revId]);
  useEffect(() => { if (Object.keys(rates).length) try { localStorage.setItem(key, JSON.stringify(rates)); } catch { /* ignore */ } }, [rates]);

  const rows = useMemo(() => (est?.items ?? []).map(i => { const r = parseFloat(rates[i.id] ?? "0") || 0; return { ...i, rate: r, amount: i.qty * r }; }), [est, rates]);
  const sub = rows.reduce((s, r) => s + r.amount, 0); const c = (parseFloat(cont) || 0) / 100 * sub; const total = sub + c;

  if (!full.current) return <div className="empty-pane"><h3>No estimate yet</h3><p className="muted">Generate the drawings first. The estimate is calculated from the same model as the drawings.</p></div>;
  if (err) return <div className="panel"><ErrorBox n={err} /></div>;
  if (!est) return <div className="empty-pane"><Spinner label="Calculating quantities…" /></div>;
  const csv = () => {
    const lines = [["Item", "Qty", "Unit", "Rate (INR)", "Amount (INR)"], ...rows.map(r => [r.name, r.qty, r.unit, r.rate, Math.round(r.amount)]), ["Contingency " + cont + "%", "", "", "", Math.round(c)], ["TOTAL", "", "", "", Math.round(total)]];
    const url = URL.createObjectURL(new Blob([lines.map(l => l.map(x => `"${String(x).replace(/"/g, '""')}"`).join(",")).join("\n")], { type: "text/csv" }));
    const a = document.createElement("a"); a.href = url; a.download = `${full.project.name}-estimate-rev${est.revision}.csv`; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 5000);
  };
  return (
    <div className="panel">
      <h3>Cost estimate · revision {est.revision}</h3>
      <div className="grid2"><div className="stat"><small>Built-up (outer footprint)</small><b>{est.built_up_m2} m²</b></div><div className="stat"><small>Room floor area</small><b>{est.carpet_m2} m²</b></div></div>
      <div className="banner warn slim">Rates are placeholders. Replace them with your local rates. This is not a quotation.</div>
      <div className="est">
        {rows.map(r => (
          <div className="est-row" key={r.id}>
            <div className="est-name"><strong>{r.name}</strong><small>{r.basis}</small></div>
            <div className="est-qty">{r.qty} {r.unit}</div>
            <label className="est-rate">Rate ₹/{r.unit}<input inputMode="decimal" value={rates[r.id] ?? ""} onChange={e => setRates(p => ({ ...p, [r.id]: e.target.value }))} /></label>
            <div className="est-amt">{inr(r.amount)}</div>
          </div>
        ))}
        <div className="est-row"><div className="est-name"><strong>Contingency</strong></div><div className="est-qty" /><label className="est-rate">%<input inputMode="decimal" value={cont} onChange={e => setCont(e.target.value)} /></label><div className="est-amt">{inr(c)}</div></div>
        <div className="est-row total"><div className="est-name"><strong>Estimated total</strong><small>≈ {inr(total / (est.built_up_m2 || 1))} per m² built-up</small></div><div className="est-qty" /><div /><div className="est-amt">{inr(total)}</div></div>
      </div>
      <div className="row"><button className="btn" onClick={() => download(`/projects/${full.project.id}/estimate.xlsx?cont=${encodeURIComponent(cont)}&rates=${encodeURIComponent(JSON.stringify(Object.fromEntries(Object.entries(rates).map(([k, v]) => [k, parseFloat(v) || 0]))))}`, `${full.project.name}-BOQ-rev${est.revision}.xlsx`)}>Download Excel (BOQ)</button><button className="btn ghost" onClick={csv}>CSV</button><button className="btn ghost" onClick={() => { const e = est.rates; setRates(Object.fromEntries(Object.entries(e).map(([k, v]) => [k, String(v)]))); }}>Reset rates</button></div>
      <p className="fine">{est.disclaimer}</p>
    </div>
  );
}
