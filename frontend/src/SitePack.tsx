import { useEffect, useState } from "react";
import { api, download, Full } from "./api";
import { ErrorBox, Notice, Spinner, toNotice } from "./ui";

interface Row { text: string; source: string }
interface Pack { revision: number; notice: string; stages: { name: string; items: Row[] }[]; specification: Row[]; questions: string[]; sources: Record<string, string> }
const TAG: Record<string, string> = { to_confirm: "to confirm", assumed: "assumed", drawings: "from drawings", estimate: "from estimate" };

export default function SitePack({ full }: { full: Full }) {
  const pid = full.project.id; const revId = full.current?.id;
  const [d, setD] = useState<Pack | null>(null); const [err, setErr] = useState<Notice | null>(null);
  const [done, setDone] = useState<Set<string>>(() => { try { return new Set(JSON.parse(localStorage.getItem(`pack-${pid}`) || "[]")); } catch { return new Set(); } });
  useEffect(() => { setD(null); if (revId) api(`/projects/${pid}/site-pack`).then(setD).catch(e => setErr(toNotice(e))); }, [pid, revId]);
  const toggle = (t: string) => setDone(s => { const n = new Set(s); n.has(t) ? n.delete(t) : n.add(t); try { localStorage.setItem(`pack-${pid}`, JSON.stringify([...n])); } catch { /* storage may be blocked */ } return n; });
  const save = () => download(`/projects/${pid}/site-pack?format=md`, "site-pack.md").catch(e => setErr(toNotice(e)));
  if (!revId) return <div className="panel"><p className="muted">Make the drawings first. The site pack is built from them.</p></div>;
  if (!d) return <div className="panel"><ErrorBox n={err} />{!err && <Spinner label="Preparing…" />}</div>;
  return (
    <div className="panel">
      <ErrorBox n={err} onClose={() => setErr(null)} />
      <h3>Site pack</h3>
      <p className="notice-box">{d.notice}</p>
      <div className="row"><button className="btn" onClick={save}>Download checklist (.md)</button></div>
      {d.stages.map(st => (<section key={st.name}><h4>{st.name}</h4>
        <ul className="pk-list">{st.items.map(i => (<li key={i.text} className={done.has(i.text) ? "done" : ""}>
          <label><input type="checkbox" checked={done.has(i.text)} onChange={() => toggle(i.text)} /> <span>{i.text}</span></label>
          {TAG[i.source] && <small className={`pk-tag ${i.source}`}>{TAG[i.source]}</small>}</li>))}</ul></section>))}
      <h4>Specification notes</h4>
      <ul className="pk-list">{d.specification.map(i => <li key={i.text}><span>{i.text}</span>{TAG[i.source] && <small className={`pk-tag ${i.source}`}>{TAG[i.source]}</small>}</li>)}</ul>
      <h4>Questions to ask before you sign</h4>
      <ol>{d.questions.map(q => <li key={q}>{q}</li>)}</ol>
    </div>
  );
}
