import { useCallback, useEffect, useState } from "react";
import { api, Full } from "./api";
import { ago, ErrorBox, Notice, Spinner, toNotice } from "./ui";

interface Share { id: string; token: string; path: string; revision: number | null; allow_comments: boolean; active: boolean; created_at: string; comments: number }
interface Cmt { id: string; author: string; from_owner: boolean; body: string; sheet_id: string | null; resolved: boolean; revision: number | null; created_at: string }
interface Req { id: string; kind: string; label: string; reviewer_name: string; reviewer_contact: string; note: string; status: string; outcome_note: string; revision: number | null; created_at: string }

const link = (s: Share) => `${location.origin}${location.pathname}${s.path}`;
const STATUS: Record<string, string> = { requested: "To do", sent: "Sent to reviewer", reviewed: "Reviewer replied", cancelled: "Cancelled" };

export default function SharePanel({ full }: { full: Full }) {
  const pid = full.project.id; const ready = full.current?.render_status === "done";
  const [shares, setShares] = useState<Share[] | null>(null); const [cmts, setCmts] = useState<Cmt[]>([]);
  const [reqs, setReqs] = useState<Req[]>([]); const [info, setInfo] = useState("");
  const [err, setErr] = useState<Notice | null>(null); const [busy, setBusy] = useState(false);
  const [allow, setAllow] = useState(true); const [copied, setCopied] = useState(""); const [reply, setReply] = useState("");
  const [kind, setKind] = useState("structural"); const [rname, setRname] = useState(""); const [rcontact, setRcontact] = useState(""); const [rnote, setRnote] = useState("");

  const load = useCallback(() => Promise.all([
    api(`/projects/${pid}/shares`), api(`/projects/${pid}/comments`), api(`/projects/${pid}/review-requests`),
  ]).then(([a, b, c]) => { setShares(a.shares); setCmts(b.comments); setReqs(c.requests); setInfo(c.info); }).catch(e => setErr(toNotice(e))), [pid]);
  useEffect(() => { load(); }, [load]);

  const act = async (f: () => Promise<unknown>) => { setBusy(true); setErr(null); try { await f(); await load(); } catch (e) { setErr(toNotice(e)); } finally { setBusy(false); } };
  const copy = async (s: Share) => { try { await navigator.clipboard.writeText(link(s)); setCopied(s.id); setTimeout(() => setCopied(""), 1800); } catch { setCopied(""); window.prompt("Copy this link", link(s)); } };

  if (!shares) return <div className="panel"><ErrorBox n={err} />{!err && <Spinner label="Loading…" />}</div>;
  return (
    <div className="panel">
      <ErrorBox n={err} onClose={() => setErr(null)} />
      <h3>Share a read-only link</h3>
      <p className="muted">Anyone with the link can see the drawings and the 3D view of revision {full.current?.number ?? "–"} and leave comments. They cannot change anything, and they do not need an account. Revoke it any time.</p>
      <p className="fine">The sheets include your title block, so the client name and site address you entered will be visible on them.</p>
      <div className="row">
        <label className="chk"><input type="checkbox" checked={allow} onChange={e => setAllow(e.target.checked)} /> Allow comments</label>
        <button className="btn primary" disabled={busy || !ready} onClick={() => act(() => api(`/projects/${pid}/shares`, { json: { allow_comments: allow } }))}>Create link</button>
      </div>
      {!ready && <p className="muted">Drawings are still being prepared. You can share once they are ready.</p>}
      {shares.length > 0 && <ul className="sh-list">{shares.map(s => (
        <li key={s.id} className={s.active ? "" : "off"}>
          <div><strong>Revision {s.revision ?? "?"}</strong> · {s.active ? (s.allow_comments ? "comments on" : "view only") : "revoked"} · {ago(s.created_at)} · {s.comments} comment{s.comments === 1 ? "" : "s"}</div>
          {s.active && <input readOnly value={link(s)} aria-label="Share link" onFocus={e => e.currentTarget.select()} />}
          {s.active && <div className="row"><button className="btn sm" onClick={() => copy(s)}>{copied === s.id ? "Copied" : "Copy link"}</button>
            <button className="btn sm danger" disabled={busy} onClick={() => act(() => api(`/projects/${pid}/shares/${s.id}`, { method: "DELETE" }))}>Revoke</button></div>}
        </li>))}</ul>}

      <h3>Comments</h3>
      {cmts.length === 0 ? <p className="muted">No comments yet.</p> : <ul className="sh-list">{cmts.map(c => (
        <li key={c.id} className={c.resolved ? "off" : ""}>
          <div><strong>{c.author}</strong>{c.from_owner && " (you)"} · rev {c.revision ?? "?"} · {ago(c.created_at)}{c.resolved && " · resolved"}</div>
          <p>{c.body}</p>
          {!c.from_owner && <button className="btn sm" disabled={busy} onClick={() => act(() => api(`/projects/${pid}/comments/${c.id}/resolve`, { method: "POST" }))}>{c.resolved ? "Reopen" : "Mark resolved"}</button>}
        </li>))}</ul>}
      {ready && <form className="row" onSubmit={e => { e.preventDefault(); if (!reply.trim()) return; act(async () => { await api(`/projects/${pid}/comments`, { json: { body: reply } }); setReply(""); }); }}>
        <input value={reply} maxLength={2000} onChange={e => setReply(e.target.value)} placeholder="Reply (visible on every share link)" aria-label="Reply" />
        <button className="btn" disabled={busy || !reply.trim()}>Post</button></form>}

      <h3>Professional review checklist</h3>
      <p className="fine">{info}</p>
      <form className="sh-form" onSubmit={e => { e.preventDefault(); act(async () => { await api(`/projects/${pid}/review-requests`, { json: { kind, reviewer_name: rname, reviewer_contact: rcontact, note: rnote } }); setRname(""); setRcontact(""); setRnote(""); }); }}>
        <label>Review type<select value={kind} onChange={e => setKind(e.target.value)}><option value="architect">Architect</option><option value="structural">Structural engineer</option><option value="mep">MEP engineer</option></select></label>
        <label>Reviewer name (optional)<input value={rname} maxLength={200} onChange={e => setRname(e.target.value)} /></label>
        <label>Their email or phone (optional)<input value={rcontact} maxLength={300} onChange={e => setRcontact(e.target.value)} /></label>
        <label>What should they look at?<textarea value={rnote} maxLength={2000} rows={2} onChange={e => setRnote(e.target.value)} /></label>
        <button className="btn" disabled={busy || !ready}>Add to checklist</button>
      </form>
      {reqs.length > 0 && <ul className="sh-list">{reqs.map(r => (
        <li key={r.id} className={r.status === "cancelled" ? "off" : ""}>
          <div><strong>{r.label}</strong> · rev {r.revision ?? "?"} · {STATUS[r.status]}{r.reviewer_name && ` · ${r.reviewer_name}`}</div>
          {r.note && <p>{r.note}</p>}
          <label className="inl">Status<select value={r.status} onChange={e => act(() => api(`/projects/${pid}/review-requests/${r.id}`, { method: "PATCH", json: { status: e.target.value } }))}>
            {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        </li>))}</ul>}
    </div>
  );
}
