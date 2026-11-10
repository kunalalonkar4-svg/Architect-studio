import { useEffect, useMemo, useState } from "react";
import { api, Full } from "./api";
import { ErrorBox, Notice, Spinner, toNotice } from "./ui";

interface Item { id: string; name: string; unit: string; qty: number; basis: string }
interface Est { revision: number; currency: string; built_up_m2: number; carpet_m2: number; items: Item[]; rates: Record<string, number>; disclaimer: string }
const inr = (n: number) => "₹ " + Math.round(n).toLocaleString("en-IN");

export default function EstimatePanel({ full }: { full: Full }) {
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
      <div className="row"><button className="btn" onClick={csv}>Download CSV</button><button className="btn ghost" onClick={() => { const e = est.rates; setRates(Object.fromEntries(Object.entries(e).map(([k, v]) => [k, String(v)]))); }}>Reset rates</button></div>
      <p className="fine">{est.disclaimer}</p>
    </div>
  );
}
