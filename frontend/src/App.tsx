import { useEffect, useState } from "react";
import { api, AiStatus, getToken, User } from "./api";
import Auth from "./Auth";
import Settings from "./Settings";
import Sidebar from "./Sidebar";
import Workspace, { useWide } from "./Workspace";
import { Spinner } from "./ui";

export default function App() {
  const [user, setUser] = useState<User | null>(null); const [ai, setAi] = useState<AiStatus | null>(null);
  const [booting, setBooting] = useState(!!getToken());
  const [pid, setPid] = useState<string | null>(() => { try { return localStorage.getItem("drafta.pid"); } catch { return null; } });
  const [key, setKey] = useState(0); const [settings, setSettings] = useState(false); const [drawer, setDrawer] = useState(false);
  const wide = useWide();
  useEffect(() => { if (!getToken()) return; api("/auth/me").then(r => { setUser(r.user); setAi(r.ai); }).catch(() => undefined).finally(() => setBooting(false)); }, []);
  useEffect(() => { try { pid ? localStorage.setItem("drafta.pid", pid) : localStorage.removeItem("drafta.pid"); } catch { /* ignore */ } }, [pid]);
  if (booting) return <div className="pane-center"><Spinner label="Starting…" /></div>;
  if (!user || !ai) return <Auth onAuthed={(u, a) => { setUser(u); setAi(a); }} />;
  const bump = () => setKey(k => k + 1);
  const side = <Sidebar activeId={pid} onSelect={id => { setPid(id); setDrawer(false); }} refreshKey={key} onChanged={bump} onSettings={() => setSettings(true)} user={user.firm_name || user.display_name} onClose={wide ? undefined : () => setDrawer(false)} />;
  return (
    <div className="app">
      {wide ? <aside className="side-fixed">{side}</aside> : drawer && <div className="drawer-bg" onClick={() => setDrawer(false)}><aside className="drawer" onClick={e => e.stopPropagation()}>{side}</aside></div>}
      <main className="main">
        {!wide && <div className="topbar"><button className="btn ghost" aria-label="Open project list" onClick={() => setDrawer(true)}>☰ Projects</button><span className="brand small"><span className="logo-mark" aria-hidden /> Drafta</span></div>}
        {pid ? <Workspace key={pid} pid={pid} onListChanged={bump} /> : (
          <div className="pane-center welcome">
            <h2>Welcome{user.display_name ? `, ${user.display_name}` : ""}</h2>
            <p className="muted">Create a project, then describe the plot and rooms in your own words. You’ll get a dimensioned plan, elevations, section and schedules — exportable as vector PDF, DXF and PNG.</p>
            {!wide && <button className="btn primary" onClick={() => setDrawer(true)}>Open projects</button>}
            <p className="fine">Concept drawings only — not reviewed, signed or approved. Check local rules with a licensed professional.</p>
          </div>)}
      </main>
      {settings && <Settings user={user} ai={ai} onUser={setUser} onClose={() => setSettings(false)} onLogout={() => { setUser(null); setSettings(false); setPid(null); }} />}
    </div>
  );
}
