import { useEffect, useRef, useState } from "react";
import { api, ApiError, Full, Message, Proposal, streamChat } from "./api";
import { ErrorBox, Modal, Notice, Spinner, kb, toNotice } from "./ui";

interface Props { full: Full; reload: () => Promise<void>; goTab: (t: string) => void }
interface Live { text: string; events: any[]; error?: { code: string; message: string; next_actions: string[]; retriable: boolean } }

const STARTERS = [
  "Mujhe 30 by 50 feet ka plot hai, road east side mein. 2 bedroom ghar chahiye.",
  "I have a 9 m × 15 m plot, road on the north. 2 bedrooms, open kitchen, one car parking.",
  "मेरे पास 30 फुट × 50 फुट का प्लॉट है, सड़क पूर्व में है।",
];

export default function Chat({ full, reload, goTab }: Props) {
  const pid = full.project.id;
  const [text, setText] = useState("");
  const [pending, setPending] = useState<{ id: string; filename: string; size: number; mime: string; notice?: string }[]>([]);
  const [live, setLive] = useState<Live | null>(null);
  const [liveUser, setLiveUser] = useState<string | null>(null);
  const [err, setErr] = useState<Notice | null>(null);
  const [consent, setConsent] = useState<{ message: string; retry: () => void } | null>(null);
  const abort = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const archived = full.project.status === "archived";
  const busy = live !== null;

  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [full.messages.length, live?.text, live?.events.length, full.proposals.length]);
  useEffect(() => { setPending([]); setText(""); setErr(null); }, [pid]);

  async function send(content: string, opts: { consent?: boolean; retry_of?: string; ids?: string[] } = {}) {
    if (busy) return;
    const ids = opts.ids ?? pending.map(p => p.id);
    setErr(null); setLive({ text: "", events: [] }); setLiveUser(opts.retry_of ? null : content);
    const ac = new AbortController(); abort.current = ac;
    try {
      await streamChat(pid, { content, attachment_ids: ids, consent: !!opts.consent, retry_of: opts.retry_of }, ev => {
        if (ev.type === "text") setLive(l => l && { ...l, text: l.text + ev.delta });
        else if (ev.type === "event") setLive(l => l && { ...l, events: [...l.events, ev.event] });
        else if (ev.type === "error") setLive(l => l && { ...l, error: ev });
      }, ac.signal);
      if (!opts.retry_of) { setText(""); setPending([]); }
    } catch (e: any) {
      if (e?.name === "AbortError") { /* user cancelled */ }
      else if (e instanceof ApiError && e.err.code === "consent_required") {
        setLive(null); setLiveUser(null);
        setConsent({ message: e.err.message, retry: () => send(content, { ...opts, consent: true, ids }) });
        return;
      } else setErr(toNotice(e));
    } finally {
      abort.current = null;
      await reload().catch(() => undefined);
      setLive(null); setLiveUser(null);
    }
  }

  async function onFile(files: FileList | null) {
    if (!files?.length) return;
    setErr(null);
    for (const f of Array.from(files)) {
      const fd = new FormData(); fd.append("file", f);
      try { const r = await api(`/projects/${pid}/attachments`, { form: fd }); setPending(p => [...p, { ...r.attachment, notice: r.notice }]); }
      catch (e) { setErr(toNotice(e)); }
    }
    if (fileRef.current) fileRef.current.value = "";
  }

  async function removeAttachment(id: string) {
    setPending(p => p.filter(x => x.id !== id));
    try { await api(`/attachments/${id}`, { method: "DELETE" }); } catch { /* already gone */ }
  }

  const lastMsg = full.messages[full.messages.length - 1];
  return (
    <section className="chat" aria-label="Chat">
      <div className="msgs" role="log" aria-live="polite" aria-relevant="additions text">
        {full.messages.length === 0 && !busy && (
          <div className="empty-chat">
            <h3>Tell me what you want to build</h3>
            <p className="muted">Plain language is fine — English, Hindi or Hinglish. You can attach a sketch, a PDF or notes (optional). I’ll summarise your brief and ask only what I really need.</p>
            <QuickStart disabled={busy || archived} onSend={t => send(t)} />
            <p className="muted">Ya apne shabdon mein likho:</p>
            <div className="chips">{STARTERS.map(s => <button key={s} className="chip" onClick={() => setText(s)}>{s}</button>)}</div>
          </div>
        )}
        {full.messages.map(m => <Bubble key={m.id} m={m} full={full} onRetry={() => send(m.content, { retry_of: m.id, ids: [] })} canRetry={!busy && !archived && m === lastMsg}
          onReply={t => send(t)} goTab={goTab} />)}
        {liveUser && <div className="msg user"><div className="bubble">{liveUser}</div></div>}
        {live && (
          <div className="msg assistant">
            <div className="bubble">
              {live.text ? <div className="txt">{live.text}</div> : !live.error && <Spinner label="Thinking…" />}
              {live.events.map((e, i) => <EventView key={i} e={e} full={full} onReply={t => send(t)} goTab={goTab} />)}
              {live.error && <ErrorBox n={live.error} />}
            </div>
          </div>
        )}
        {full.proposals.map(p => <ProposalCard key={p.id} p={p} full={full} reload={reload} goTab={goTab} />)}
        <div ref={endRef} />
      </div>
      <ErrorBox n={err} onClose={() => setErr(null)} />
      {archived && <div className="banner warn">This project is archived (read-only). Unarchive it from the project menu to continue.</div>}
      <form className="composer" onSubmit={e => { e.preventDefault(); if (text.trim()) send(text.trim()); }}>
        {pending.length > 0 && (
          <ul className="attachments" aria-label="Attached files">
            {pending.map(a => <li key={a.id}>📎 {a.filename} <small>{kb(a.size)}</small><button type="button" className="btn ghost sm" aria-label={`Remove ${a.filename}`} onClick={() => removeAttachment(a.id)}>✕</button></li>)}
          </ul>
        )}
        <div className="compose-row">
          <input ref={fileRef} type="file" hidden multiple accept="image/png,image/jpeg,application/pdf,text/plain,.txt" onChange={e => onFile(e.target.files)} />
          <button type="button" className="btn icon" aria-label="Attach file (PNG, JPEG, PDF or text)" title="Attach file" disabled={busy || archived} onClick={() => fileRef.current?.click()}>📎</button>
          <textarea aria-label="Message" rows={2} value={text} maxLength={6000} disabled={archived} placeholder="Describe the plot, rooms or a change… (Enter to send, Shift+Enter for a new line)"
            onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); if (text.trim() && !busy) send(text.trim()); } }} />
          {busy
            ? <button type="button" className="btn danger" onClick={() => abort.current?.abort()}>Stop</button>
            : <button className="btn primary" disabled={!text.trim() || archived}>Send</button>}
        </div>
      </form>
      {consent && (
        <Modal title="Send files to the AI provider?" onClose={() => setConsent(null)}>
          <p>{consent.message}</p>
          <div className="row end"><button className="btn" onClick={() => setConsent(null)}>Cancel</button>
            <button className="btn primary" onClick={() => { const c = consent; setConsent(null); c.retry(); }}>Confirm and send</button></div>
        </Modal>
      )}
    </section>
  );
}

function Bubble({ m, full, onRetry, canRetry, onReply, goTab }: { m: Message; full: Full; onRetry: () => void; canRetry: boolean; onReply: (t: string) => void; goTab: (t: string) => void }) {
  const atts = m.attachment_ids?.map(id => full.attachments.find(a => a.id === id)).filter(Boolean) as Full["attachments"];
  if (m.role === "system") return <div className="sysnote">{m.content}{m.events.map((e, i) => <EventView key={i} e={e} full={full} onReply={onReply} goTab={goTab} />)}</div>;
  return (
    <div className={"msg " + m.role}>
      <div className="bubble">
        {m.content && <div className="txt">{m.content}</div>}
        {atts?.length > 0 && <div className="attach-line">{atts.map(a => <span key={a.id}>📎 {a.filename}</span>)}</div>}
        {m.role === "assistant" && m.events.map((e, i) => <EventView key={i} e={e} full={full} onReply={onReply} goTab={goTab} />)}
        {m.status === "cancelled" && <div className="note">Stopped. {canRetry && <button className="btn sm" onClick={onRetry}>Retry</button>}</div>}
        {m.status === "error" && !m.events.some(e => e.type === "error") && <div className="note err">This reply failed. {canRetry && <button className="btn sm" onClick={onRetry}>Retry</button>}</div>}
        {m.status === "error" && m.events.some(e => e.type === "error") && canRetry && <button className="btn sm" onClick={onRetry}>Retry</button>}
      </div>
    </div>
  );
}

function EventView({ e, full, onReply, goTab }: { e: any; full: Full; onReply: (t: string) => void; goTab: (t: string) => void }) {
  switch (e.type) {
    case "brief": return <div className="evt">📝 Brief updated. <button className="link" onClick={() => goTab("brief")}>Review and edit</button></div>;
    case "clarification": return (
      <div className="evt q">
        <strong>Questions</strong>
        <ol>{e.questions.map((q: any) => <li key={q.id}>{q.question}{q.why && <small> — {q.why}</small>}
          {q.options && <div className="chips">{q.options.map((o: string) => <button key={o} className="chip" onClick={() => onReply(o)}>{o}</button>)}</div>}</li>)}</ol>
        {full.brief && full.missing.length === 0 ? null : <div className="chips"><button className="chip" onClick={() => onReply("Proceed with labelled concept assumptions for the missing items.")}>Proceed with labelled assumptions</button></div>}
      </div>);
    case "revision": return <div className="evt">📐 Revision {e.number}: {e.summary} <button className="link" onClick={() => goTab("drawing")}>View drawing</button></div>;
    case "options": case "proposal": return <div className="evt">⏳ Waiting for your confirmation below — nothing has been changed yet.</div>;
    case "export": return <div className="evt">📦 Export started ({String(e.format).toUpperCase()}). <button className="link" onClick={() => goTab("export")}>See progress</button></div>;
    case "validation": return (
      <div className="evt"><strong>Checks</strong>
        {e.issues?.length ? <ul>{e.issues.slice(0, 8).map((i: any, k: number) => <li key={k} className={"sev-" + i.severity}>{i.message}{i.fix && <small> Next: {i.fix}</small>}</li>)}</ul> : " All checks passed."}
      </div>);
    case "info": return <div className="evt">ℹ️ {e.message}</div>;
    case "error": return <ErrorBox n={{ message: e.message, next_actions: e.next_actions, code: e.code, detail: e.detail }} />;
    default: return null;
  }
}

export function ProposalCard({ p, full, reload, goTab }: { p: Proposal; full: Full; reload: () => Promise<void>; goTab: (t: string) => void }) {
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<Notice | null>(null); const [opt, setOpt] = useState<number | null>(null);
  const isOptions = p.kind === "options";
  async function confirm() {
    setBusy(true); setErr(null);
    try { await api(`/proposals/${p.id}/confirm`, { json: isOptions ? { option: opt } : {} }); await reload(); goTab("drawing"); }
    catch (e) { setErr(toNotice(e)); } finally { setBusy(false); }
  }
  async function reject() {
    setBusy(true);
    try { await api(`/proposals/${p.id}/reject`, { method: "POST" }); await reload(); } catch (e) { setErr(toNotice(e)); } finally { setBusy(false); }
  }
  const stale = p.base_revision_id !== (full.current?.id ?? "");
  return (
    <div className="proposal" role="group" aria-label="Proposed change">
      <h4>{isOptions ? "Choose a layout" : "Proposed change"}</h4>
      <p>{p.summary}</p>
      {isOptions && (
        <div className="opts" role="radiogroup" aria-label="Layout options">
          {p.options.map((o, i) => (
            <label key={i} className={"opt" + (opt === i ? " on" : "")}>
              <input type="radio" name={"opt" + p.id} checked={opt === i} onChange={() => setOpt(i)} />
              <div><strong>{o.label}</strong>{o.tradeoff && <div className="muted">{o.tradeoff}</div>}
                <ul className="mini">{(o.rooms || []).slice(0, 8).map((r: any, k: number) => <li key={k}>{r.name}: {r.clear_w}×{r.clear_d} mm, {r.area_m2} m²</li>)}</ul>
                {o.issues?.length > 0 && <div className="note err">{o.issues.map((x: any) => x.message).join(" · ")}</div>}
                {o.stair && <small>Stair: {o.stair.risers} risers × {Math.round(o.stair.riser_mm)} mm, tread {Math.round(o.stair.tread_mm)} mm</small>}
              </div>
            </label>
          ))}
        </div>
      )}
      {p.changes?.length > 0 && <ul className="changes">{p.changes.map((c, i) => <li key={i}>{c.text ?? c.summary ?? JSON.stringify(c)}</li>)}</ul>}
      {p.affected_sheets?.length > 0 && <p className="aff"><strong>Drawings affected:</strong> {p.affected_sheets.map((s: any) => s.number ?? s).join(", ")}. Others stay unchanged.</p>}
      {p.issues?.filter(i => i.severity !== "info").map((i, k) => <div key={k} className={"note " + (i.severity === "error" ? "err" : "warn")}>{i.message}{i.fix && <> — {i.fix}</>}</div>)}
      {stale && <div className="note warn">The drawing has changed since this was proposed. Ask again to refresh it.</div>}
      <ErrorBox n={err} onClose={() => setErr(null)} />
      <div className="row end">
        <button className="btn" onClick={reject} disabled={busy}>{isOptions ? "Dismiss" : "Discard"}</button>
        <button className="btn primary" onClick={confirm} disabled={busy || p.blocking.length > 0 || (isOptions && opt === null)}>
          {busy ? "Working…" : isOptions ? "Use this layout" : "Confirm and save revision"}
        </button>
      </div>
      {p.blocking.length > 0 && <small className="muted">Blocked by the error above. Ask for a different change.</small>}
    </div>
  );
}

function QuickStart({ onSend, disabled }: { onSend: (t: string) => void; disabled: boolean }) {
  const [w, setW] = useState("30"); const [d, setD] = useState("50"); const [u, setU] = useState("ft"); const [road, setRoad] = useState("east"); const [bed, setBed] = useState("2");
  const ok = parseFloat(w) > 0 && parseFloat(d) > 0;
  return (
    <form className="quick-start" onSubmit={e => { e.preventDefault(); if (ok) onSend(`I have a ${w} ${u} x ${d} ${u} plot, road on the ${road}. ${bed} bedroom${bed === "1" ? "" : "s"}, open kitchen, parking and a staircase.`); }}>
      <strong>Quick start</strong>
      <div className="grid2">
        <label>Plot width<input inputMode="decimal" value={w} onChange={e => setW(e.target.value)} /></label>
        <label>Plot depth<input inputMode="decimal" value={d} onChange={e => setD(e.target.value)} /></label>
        <label>Unit<select value={u} onChange={e => setU(e.target.value)}><option value="ft">feet</option><option value="m">metres</option></select></label>
        <label>Road side<select value={road} onChange={e => setRoad(e.target.value)}>{["north", "east", "south", "west"].map(s => <option key={s}>{s}</option>)}</select></label>
        <label>Bedrooms<select value={bed} onChange={e => setBed(e.target.value)}><option>1</option><option>2</option></select></label>
      </div>
      <button className="btn primary block" disabled={!ok || disabled}>Start my plan</button>
    </form>
  );
}
