import { FormEvent, useEffect, useState } from "react";
import { api } from "./api";
import { ago, ErrorBox, Notice, Spinner, toNotice } from "./ui";
import View3D from "./View3D";

type Route = { kind: "share"; id: string } | { kind: "sample"; id: string | null };
export function parseHash(h: string): Route | null {
  const m = /^#\/share\/([\w-]{10,})$/.exec(h); if (m) return { kind: "share", id: m[1] };
  const s = /^#\/sample(?:\/([\w-]+))?$/.exec(h); if (s) return { kind: "sample", id: s[1] ?? null };
  return null;
}
const home = () => { location.hash = ""; };
const back = () => { location.hash = /^#\/sample\/.+/.test(location.hash) ? "#/sample" : ""; };
const inr = (n: number) => "₹" + Math.round(n).toLocaleString("en-IN");

function Shell({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <div className="pub">
      <header><div className="pub-l"><button className="btn sm back" onClick={back} aria-label="Back">← Back</button><span className="brand small"><span className="logo-mark" aria-hidden /> Drafta</span></div><button className="btn sm" onClick={home}>Start your own project</button></header>
      <div className="pub-body"><h2>{title}</h2>{sub && <p className="muted">{sub}</p>}{children}</div>
    </div>
  );
}

export default function PublicView({ route }: { route: Route }) {
  return route.kind === "share" ? <SharedProject token={route.id} /> : route.id ? <Sample id={route.id} /> : <SampleList />;
}

function SampleList() {
  const [d, setD] = useState<{ samples: { id: string; title: string }[]; note: string } | null>(null); const [err, setErr] = useState<Notice | null>(null);
  useEffect(() => { api("/public/samples").then(setD).catch(e => setErr(toNotice(e))); }, []);
  return (
    <Shell title="Sample projects" sub="Open a finished concept without signing in. Look at the plan, walk through it in 3D, and see the review and estimate.">
      <ErrorBox n={err} />{!d && !err && <Spinner label="Loading…" />}
      {d && <><ul className="pub-list">{d.samples.map(s => <li key={s.id}><a href={`#/sample/${s.id}`}>{s.title}</a></li>)}</ul><p className="fine">{d.note}</p></>}
    </Shell>
  );
}

function Sample({ id }: { id: string }) {
  const [d, setD] = useState<any>(null); const [err, setErr] = useState<Notice | null>(null); const [tab, setTab] = useState<"plan" | "3d" | "review" | "estimate">("plan");
  useEffect(() => { setD(null); api(`/public/samples/${id}`).then(setD).catch(e => setErr(toNotice(e))); }, [id]);
  const tabs: [typeof tab, string][] = [["plan", "Plan"], ["3d", "3D"], ["review", "Review"], ["estimate", "Estimate"]];
  return (
    <Shell title={d?.title ?? "Sample project"} sub={d?.note}>
      <p><a href="#/sample">← All samples</a></p><ErrorBox n={err} />{!d && !err && <Spinner label="Preparing the sample…" />}
      {d && <>
        <div className="pub-tabs" role="tablist">{tabs.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}</div>
        {tab === "plan" && <img className="pub-sheet" alt={`Floor plan: ${d.title}`} src={d.plan_url} />}
        {tab === "3d" && <div className="pub-3d"><View3D src={`/public/samples/${id}/model3d`} /></div>}
        {tab === "review" && <ul className="sh-list">
          <li><strong>Vastu score</strong>: {d.review.vastu.score ?? "n/a"} / 100 <small className="muted">(traditional guideline, not a rule)</small></li>
          {Object.entries(d.review.counts as Record<string, number>).map(([k, v]) => <li key={k}>{k}: {v}</li>)}
          <li className="fine">{d.review.disclaimer}</li></ul>}
        {tab === "estimate" && <div><p><strong>{inr(d.estimate.subtotal_inr)}</strong> rough construction cost for {Math.round(d.estimate.built_up_sqft)} sq ft built-up (about {inr(d.estimate.cost_per_sqft_inr)} per sq ft).</p>
          <p className="fine">Placeholder rates for illustration. Real costs depend on your city, finish, soil and contractor. Get a quote before you plan a budget.</p></div>}
      </>}
    </Shell>
  );
}

function SharedProject({ token }: { token: string }) {
  const [d, setD] = useState<any>(null); const [err, setErr] = useState<Notice | null>(null); const [tab, setTab] = useState<"sheets" | "3d" | "comments">("sheets");
  const [sheet, setSheet] = useState(""); const [author, setAuthor] = useState(""); const [body, setBody] = useState(""); const [busy, setBusy] = useState(false);
  const load = () => api(`/public/share/${token}`).then(x => { setD(x); setSheet(s => s || x.sheets.find((q: any) => q.ready)?.id || ""); }).catch(e => setErr(toNotice(e)));
  useEffect(() => { load(); }, [token]); // eslint-disable-line react-hooks/exhaustive-deps
  const send = async (e: FormEvent) => {
    e.preventDefault(); if (!body.trim()) return; setBusy(true); setErr(null);
    try { await api(`/public/share/${token}/comments`, { json: { body, author, sheet_id: tab === "sheets" && sheet ? sheet : null } }); setBody(""); await load(); } catch (x) { setErr(toNotice(x)); } finally { setBusy(false); }
  };
  if (err && !d) return <Shell title="Link not available"><ErrorBox n={err} /></Shell>;
  if (!d) return <Shell title="Opening shared project…"><Spinner label="Loading…" /></Shell>;
  const sheets = d.sheets.filter((s: any) => s.ready);
  return (
    <Shell title={d.project.name} sub={`${d.project.firm ? d.project.firm + " · " : ""}Revision ${d.project.revision} · shared ${ago(d.project.shared_at)}`}>
      <p className="notice-box">{d.notice}</p><ErrorBox n={err} onClose={() => setErr(null)} />
      <div className="pub-tabs" role="tablist">{([["sheets", "Drawings"], ["3d", "3D"], ["comments", `Comments (${d.comments.length})`]] as const).map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}</div>
      {tab === "sheets" && <>
        <label className="inl">Sheet<select value={sheet} onChange={e => setSheet(e.target.value)}>{sheets.map((s: any) => <option key={s.id} value={s.id}>{s.number} {s.title}</option>)}</select></label>
        {sheet && <img className="pub-sheet" alt="Drawing sheet" src={`/api/public/share/${token}/sheet/${sheet}.svg`} />}</>}
      {tab === "3d" && <div className="pub-3d"><View3D src={`/public/share/${token}/model3d`} /></div>}
      {(tab === "comments" || d.allow_comments) && <section>
        {tab === "comments" && (d.comments.length === 0 ? <p className="muted">No comments yet.</p> : <ul className="sh-list">{d.comments.map((c: any) => (
          <li key={c.id}><div><strong>{c.author}</strong>{c.from_owner && " (owner)"} · {ago(c.created_at)}</div><p>{c.body}</p></li>))}</ul>)}
        {d.allow_comments ? <form className="sh-form" onSubmit={send}>
          <h4>Leave a comment{tab === "sheets" && sheet ? " on this sheet" : ""}</h4>
          <label>Your name<input value={author} maxLength={80} onChange={e => setAuthor(e.target.value)} placeholder="Optional" /></label>
          <label>Comment<textarea value={body} rows={3} maxLength={2000} onChange={e => setBody(e.target.value)} /></label>
          <button className="btn primary" disabled={busy || !body.trim()}>Post comment</button></form> : <p className="muted">Comments are turned off for this link.</p>}
      </section>}
    </Shell>
  );
}
