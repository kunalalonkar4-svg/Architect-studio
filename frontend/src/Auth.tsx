import { FormEvent, useState } from "react";
import { api, setToken, User, AiStatus } from "./api";
import { ErrorBox, Notice, Spinner, toNotice } from "./ui";

export default function Auth({ onAuthed }: { onAuthed: (u: User, ai: AiStatus) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [name, setName] = useState("");
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<Notice | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      const r = await api(mode === "login" ? "/auth/login" : "/auth/register", { json: mode === "login" ? { email, password } : { email, password, display_name: name } });
      setToken(r.token);
      const me = await api("/auth/me");
      onAuthed(me.user, me.ai);
    } catch (e2) { setErr(toNotice(e2)); } finally { setBusy(false); }
  }
  return (
    <main className="auth">
      <form onSubmit={submit} className="auth-card" aria-labelledby="auth-h">
        <div className="brand big"><span className="logo-mark" aria-hidden /> Drafta</div>
        <h1 id="auth-h">{mode === "login" ? "Sign in" : "Create your studio"}</h1>
        <p className="muted">Describe a building in English, Hindi or Hinglish. Get dimensioned, to-scale concept drawings you can export as PDF, DXF and PNG.</p>
        {mode === "register" && <label>Your name<input value={name} onChange={e => setName(e.target.value)} autoComplete="name" /></label>}
        <label>Email<input type="email" required value={email} onChange={e => setEmail(e.target.value)} autoComplete="email" /></label>
        <label>Password{mode === "register" && <small> (8+ characters)</small>}<input type="password" required minLength={mode === "register" ? 8 : 1} value={password} onChange={e => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
        <ErrorBox n={err} />
        <button className="btn primary" disabled={busy}>{busy ? <Spinner label="Please wait…" /> : mode === "login" ? "Sign in" : "Create account"}</button>
        <button type="button" className="btn link" onClick={() => { setMode(mode === "login" ? "register" : "login"); setErr(null); }}>
          {mode === "login" ? "New here? Create an account" : "Already have an account? Sign in"}
        </button>
        <p className="fine">Concept drawings only. Not reviewed, signed, stamped or approved by any professional or authority.</p>
      </form>
    </main>
  );
}
