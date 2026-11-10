import { useEffect, useRef, useState } from "react";
import { api, ProjectSummary } from "./api";
import { ago, ErrorBox, Modal, Notice, Spinner, toNotice } from "./ui";

interface Props { activeId: string | null; onSelect: (id: string | null) => void; refreshKey: number; onChanged: () => void; onSettings: () => void; user: string; onClose?: () => void }

export default function Sidebar({ activeId, onSelect, refreshKey, onChanged, onSettings, user, onClose }: Props) {
  const [items, setItems] = useState<ProjectSummary[] | null>(null);
  const [q, setQ] = useState(""); const [archived, setArchived] = useState(false);
  const [err, setErr] = useState<Notice | null>(null);
  const [menu, setMenu] = useState<string | null>(null);
  const [dlg, setDlg] = useState<{ kind: "new" | "rename" | "delete"; p?: ProjectSummary } | null>(null);
  const t = useRef<any>();

  async function load() {
    try { const r = await api(`/projects?status=${archived ? "archived" : "active"}&q=${encodeURIComponent(q)}`); setItems(r.projects); setErr(null); }
    catch (e) { setErr(toNotice(e)); setItems([]); }
  }
  useEffect(() => { clearTimeout(t.current); t.current = setTimeout(load, q ? 250 : 0); return () => clearTimeout(t.current); }, [q, archived, refreshKey]);
  useEffect(() => { const c = () => setMenu(null); document.addEventListener("click", c); return () => document.removeEventListener("click", c); }, []);

  async function act(p: ProjectSummary, what: "archive" | "unarchive" | "duplicate") {
    setMenu(null);
    try {
      const r = await api(`/projects/${p.id}/${what}`, { method: "POST" });
      if (what === "duplicate") onSelect(r.project.id);
      if (what === "archive" && p.id === activeId) onSelect(null);
      await load(); onChanged();
    } catch (e) { setErr(toNotice(e)); }
  }

  return (
    <nav className="sidebar" aria-label="Projects">
      <div className="sb-head">
        <div className="brand"><span className="logo-mark" aria-hidden /> Drafta</div>
        {onClose && <button className="btn ghost sm" onClick={onClose} aria-label="Close project list">✕</button>}
      </div>
      <button className="btn primary block" onClick={() => setDlg({ kind: "new" })}>+ New project</button>
      <input className="search" type="search" placeholder="Search projects and chats" aria-label="Search projects" value={q} onChange={e => setQ(e.target.value)} />
      <div className="seg" role="tablist" aria-label="Project filter">
        <button role="tab" aria-selected={!archived} className={!archived ? "on" : ""} onClick={() => setArchived(false)}>Active</button>
        <button role="tab" aria-selected={archived} className={archived ? "on" : ""} onClick={() => setArchived(true)}>Archived</button>
      </div>
      <ErrorBox n={err} onClose={() => setErr(null)} actions={<button className="btn sm" onClick={load}>Retry</button>} />
      <ul className="plist">
        {items === null && <li><Spinner /></li>}
        {items && items.length === 0 && !err && <li className="empty">{q ? "No project matches your search." : archived ? "No archived projects." : "No projects yet. Start with “New project”."}</li>}
        {items?.map(p => (
          <li key={p.id} className={p.id === activeId ? "active" : ""}>
            <button className="pitem" onClick={() => { onSelect(p.id); onClose?.(); }} aria-current={p.id === activeId ? "true" : undefined}>
              <strong>{p.name}</strong><small>{p.client ? p.client + " · " : ""}{ago(p.updated_at)}</small>
            </button>
            <button className="btn ghost sm kebab" aria-label={`Actions for ${p.name}`} aria-haspopup="menu" aria-expanded={menu === p.id} onClick={e => { e.stopPropagation(); setMenu(menu === p.id ? null : p.id); }}>⋯</button>
            {menu === p.id && (
              <div className="menu" role="menu" onClick={e => e.stopPropagation()}>
                <button role="menuitem" onClick={() => { setMenu(null); setDlg({ kind: "rename", p }); }}>Rename / details</button>
                <button role="menuitem" onClick={() => act(p, "duplicate")}>Duplicate</button>
                {archived ? <button role="menuitem" onClick={() => act(p, "unarchive")}>Unarchive</button> : <button role="menuitem" onClick={() => act(p, "archive")}>Archive</button>}
                <button role="menuitem" className="danger" onClick={() => { setMenu(null); setDlg({ kind: "delete", p }); }}>Delete…</button>
              </div>
            )}
          </li>
        ))}
      </ul>
      <button className="btn ghost block userbtn" onClick={onSettings}>⚙ {user} · Branding &amp; account</button>
      {dlg?.kind === "new" && <ProjectForm title="New project" onClose={() => setDlg(null)} onSave={async v => { const r = await api("/projects", { json: v }); setDlg(null); onSelect(r.project.id); await load(); onChanged(); }} />}
      {dlg?.kind === "rename" && dlg.p && <ProjectForm title="Project details" initial={dlg.p} onClose={() => setDlg(null)} onSave={async v => { await api(`/projects/${dlg.p!.id}`, { method: "PATCH", json: v }); setDlg(null); await load(); onChanged(); }} />}
      {dlg?.kind === "delete" && dlg.p && (
        <Modal title="Delete project?" onClose={() => setDlg(null)}>
          <p>“{dlg.p.name}” with all its chat, revisions, uploads and exports will be permanently deleted. This cannot be undone. Consider archiving instead.</p>
          <div className="row end">
            <button className="btn" onClick={() => setDlg(null)}>Cancel</button>
            <button className="btn danger" onClick={async () => { const p = dlg.p!; setDlg(null); try { await api(`/projects/${p.id}`, { method: "DELETE" }); if (p.id === activeId) onSelect(null); await load(); onChanged(); } catch (e) { setErr(toNotice(e)); } }}>Delete permanently</button>
          </div>
        </Modal>
      )}
    </nav>
  );
}

function ProjectForm({ title, initial, onSave, onClose }: { title: string; initial?: ProjectSummary; onSave: (v: { name: string; client: string; address: string }) => Promise<void>; onClose: () => void }) {
  const [name, setName] = useState(initial?.name ?? ""); const [client, setClient] = useState(initial?.client ?? ""); const [address, setAddress] = useState(initial?.address ?? "");
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<Notice | null>(null);
  return (
    <Modal title={title} onClose={onClose}>
      <form onSubmit={async e => { e.preventDefault(); setBusy(true); setErr(null); try { await onSave({ name: name.trim(), client, address }); } catch (x) { setErr(toNotice(x)); setBusy(false); } }}>
        <label>Project name<input value={name} onChange={e => setName(e.target.value)} required maxLength={200} placeholder="e.g. Sharma residence, 30×50 plot" /></label>
        <label>Client <small>(optional, shown in the title block)</small><input value={client} onChange={e => setClient(e.target.value)} maxLength={200} /></label>
        <label>Site address <small>(optional)</small><input value={address} onChange={e => setAddress(e.target.value)} maxLength={400} /></label>
        <ErrorBox n={err} />
        <div className="row end"><button type="button" className="btn" onClick={onClose}>Cancel</button><button className="btn primary" disabled={busy || !name.trim()}>{busy ? "Saving…" : "Save"}</button></div>
      </form>
    </Modal>
  );
}
