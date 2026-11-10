import { useCallback, useEffect, useRef, useState } from "react";
import { api, Full } from "./api";
import BriefPanel from "./BriefPanel";
import Chat from "./Chat";
import ExportPanel from "./ExportPanel";
import Revisions from "./Revisions";
import Viewer from "./Viewer";
import { ErrorBox, Notice, Spinner, toNotice, useInterval } from "./ui";

export type Tab = "chat" | "drawing" | "brief" | "revisions" | "export";
const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "chat", label: "Chat", icon: "💬" }, { id: "drawing", label: "Drawing", icon: "📐" }, { id: "brief", label: "Brief", icon: "📝" },
  { id: "revisions", label: "Revisions", icon: "🕘" }, { id: "export", label: "Export", icon: "⬇" },
];

export function useWide() {
  const q = typeof window !== "undefined" ? window.matchMedia("(min-width: 980px)") : null;
  const [w, setW] = useState(!!q?.matches);
  useEffect(() => { if (!q) return; const f = () => setW(q.matches); q.addEventListener("change", f); return () => q.removeEventListener("change", f); }, [q]);
  return w;
}

export default function Workspace({ pid, onListChanged }: { pid: string; onListChanged: () => void }) {
  const [full, setFull] = useState<Full | null>(null); const [err, setErr] = useState<Notice | null>(null);
  const [tab, setTab] = useState<Tab>("chat"); const wide = useWide();
  const cur = useRef(pid); cur.current = pid;

  const reload = useCallback(async () => {
    const id = pid;
    try { const r: Full = await api(`/projects/${id}`); if (cur.current === id) { setFull(r); setErr(null); } } catch (e) { if (cur.current === id) setErr(toNotice(e)); }
    onListChanged();
  }, [pid]);
  useEffect(() => { setFull(null); setErr(null); setTab("chat"); reload(); }, [pid]);

  const active = !!full && (full.current?.render_status === "pending" || full.current?.render_status === "running" || full.jobs.some(j => j.state === "queued" || j.state === "running"));
  const sig = (x: { render_status: string | null; jobs: { id: string; state: string; progress: number }[] }) => x.render_status + "|" + x.jobs.map(j => j.id + j.state + Math.round(j.progress * 20)).join(",");
  useInterval(async () => {
    if (!full) return;
    try {
      const s = await api(`/projects/${pid}/status`);
      const mine = sig({ render_status: full.current?.render_status ?? null, jobs: full.jobs.slice(0, 10) });
      if (sig(s) !== mine || s.current_revision_id !== (full.current?.id ?? null)) await reload();
    } catch { /* transient; next tick retries */ }
  }, active ? 1500 : null);

  if (err && !full) return <div className="pane-center"><ErrorBox n={err} actions={<button className="btn sm" onClick={reload}>Retry</button>} /></div>;
  if (!full) return <div className="pane-center"><Spinner label="Opening project…" /></div>;

  const goTab = (t: string) => setTab(t as Tab);
  const rt: Tab = wide && tab === "chat" ? "drawing" : tab;
  const rendering = full.current && (full.current.render_status === "pending" || full.current.render_status === "running");
  const pane = (
    <div className="rightpane" role="tabpanel" id="pane" aria-label={rt}>
      {rt === "drawing" && <Viewer full={full} reload={reload} />}
      {rt === "brief" && <BriefPanel full={full} reload={reload} goTab={goTab} />}
      {rt === "revisions" && <Revisions full={full} reload={reload} goTab={goTab} />}
      {rt === "export" && <ExportPanel full={full} reload={reload} />}
    </div>
  );
  const tabs = (list: typeof TABS) => (
    <div className="tabbar" role="tablist" aria-label="Workspace sections">
      {list.map(t => (
        <button key={t.id} role="tab" aria-selected={rt === t.id || (!wide && tab === t.id)} aria-controls="pane" className={(wide ? rt : tab) === t.id ? "on" : ""} onClick={() => setTab(t.id)}>
          <span aria-hidden>{t.icon}</span><span>{t.label}</span>
          {t.id === "drawing" && rendering && <i className="dot" title="Rendering" />}
          {t.id === "chat" && full.proposals.length > 0 && <i className="dot warn" title="Awaiting your confirmation" />}
        </button>))}
    </div>
  );
  return (
    <div className="workspace">
      <header className="wshead">
        <div className="ptitle"><strong>{full.project.name}</strong>
          <small>{full.current ? `Revision ${full.current.number}` : "No drawing yet"} · {full.project.review_status === "concept_unreviewed" ? "Concept — not reviewed" : "Issued for owner’s review"}</small></div>
        <div className={"aibadge " + (full.ai.live ? "live" : "mock")} title={full.ai.message || `Model ${full.ai.model}`}>{full.ai.live ? "Claude" : "Mock AI"}</div>
      </header>
      {!full.ai.live && <div className="banner warn slim">Mock assistant active — no Anthropic key on the server. It understands simple English/Hinglish/Hindi keywords; drawings are real.</div>}
      {full.last_good && full.current?.render_status === "failed" && <div className="banner warn slim">Latest revision failed to render. Your earlier good drawing (revision {full.last_good.number}) is untouched — see Revisions.</div>}
      {wide ? (
        <div className="cols">
          <div className="col-chat"><Chat full={full} reload={reload} goTab={goTab} /></div>
          <div className="col-right">{tabs(TABS.filter(t => t.id !== "chat"))}{pane}</div>
        </div>
      ) : (
        <div className="mobile">
          <div className="mpane">{tab === "chat" ? <Chat full={full} reload={reload} goTab={goTab} /> : pane}</div>
          {tabs(TABS)}
        </div>
      )}
    </div>
  );
}
