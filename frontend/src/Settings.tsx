import { useEffect, useState } from "react";
import { api, AiStatus, fetchBlobUrl, setToken, User } from "./api";
import { ErrorBox, Modal, Notice, toNotice } from "./ui";

export default function Settings({ user, ai, onUser, onClose, onLogout }: { user: User; ai: AiStatus; onUser: (u: User) => void; onClose: () => void; onLogout: () => void }) {
  const [name, setName] = useState(user.display_name); const [firm, setFirm] = useState(user.firm_name); const [line, setLine] = useState(user.firm_line);
  const [logo, setLogo] = useState<string | null>(null); const [err, setErr] = useState<Notice | null>(null); const [msg, setMsg] = useState("");
  useEffect(() => { let u: string | null = null, off = false; if (user.has_logo) fetchBlobUrl("/auth/logo").then(x => { if (off) URL.revokeObjectURL(x); else { u = x; setLogo(x); } }).catch(() => undefined); else setLogo(null); return () => { off = true; if (u) URL.revokeObjectURL(u); }; }, [user.has_logo]);
  async function save() { setErr(null); setMsg(""); try { const r = await api("/auth/me", { method: "PATCH", json: { display_name: name, firm_name: firm, firm_line: line } }); onUser(r.user); setMsg("Saved. New drawing revisions will use these title-block details."); } catch (e) { setErr(toNotice(e)); } }
  async function upload(f: File | undefined) { if (!f) return; setErr(null); const fd = new FormData(); fd.append("file", f); try { const r = await api("/auth/logo", { form: fd }); onUser(r.user); } catch (e) { setErr(toNotice(e)); } }
  return (
    <Modal title="Branding & account" onClose={onClose}>
      <div className={"banner " + (ai.live ? "ok" : "warn")}><strong>AI assistant: {ai.live ? `Claude (${ai.model})` : "mock (no API key on server)"}</strong>
        <div>{ai.live ? "Your messages and any files you explicitly send are processed by Anthropic’s API. Files ask for your confirmation first." : ai.message}</div></div>
      <h4>Title block</h4>
      <p className="muted">Shown on every sheet as the drafting office. Leave empty for none. No signature, stamp or approval is ever added.</p>
      <label>Your name<input value={name} onChange={e => setName(e.target.value)} maxLength={200} /></label>
      <label>Firm / studio name<input value={firm} onChange={e => setFirm(e.target.value)} maxLength={200} /></label>
      <label>Address / contact line<input value={line} onChange={e => setLine(e.target.value)} maxLength={300} /></label>
      <div className="logo-row">
        {logo ? <img src={logo} alt="Your logo" className="logo-prev" /> : <div className="logo-prev none">No logo</div>}
        <div className="col">
          <label className="btn">Upload logo (PNG/JPEG, ≤1 MB)<input type="file" hidden accept="image/png,image/jpeg" onChange={e => upload(e.target.files?.[0])} /></label>
          {user.has_logo && <button className="btn ghost" onClick={async () => { try { onUser((await api("/auth/logo", { method: "DELETE" })).user); } catch (e) { setErr(toNotice(e)); } }}>Remove logo</button>}
        </div>
      </div>
      <ErrorBox n={err} onClose={() => setErr(null)} />
      {msg && <div className="note ok" role="status">{msg}</div>}
      <div className="row end"><button className="btn" onClick={() => { setToken(null); onLogout(); }}>Sign out</button><button className="btn primary" onClick={save}>Save</button></div>
    </Modal>
  );
}
