import { ReactNode, useEffect, useRef } from "react";
import { ApiError } from "./api";

export function Spinner({ label }: { label?: string }) {
  return <span className="spinner" role="status" aria-live="polite"><i aria-hidden /> {label ?? "Loading…"}</span>;
}

export interface Notice { message: string; next_actions?: string[]; code?: string; detail?: any }
export const toNotice = (e: unknown): Notice =>
  e instanceof ApiError ? { message: e.err.message, next_actions: e.err.next_actions, code: e.err.code, detail: e.err.detail } : { message: (e as Error)?.message ?? "Something went wrong", next_actions: ["Try again"] };

export function ErrorBox({ n, onClose, actions }: { n: Notice | null; onClose?: () => void; actions?: ReactNode }) {
  if (!n) return null;
  const sug = n.detail?.suggestions as { text: string }[] | undefined;
  return (
    <div className="errbox" role="alert">
      <div className="errmsg">{n.message}</div>
      {n.next_actions && n.next_actions.length > 0 && <ul className="next">{n.next_actions.map((a, i) => <li key={i}>{a}</li>)}</ul>}
      {sug && !n.next_actions?.length && <ul className="next">{sug.map((a, i) => <li key={i}>{a.text}</li>)}</ul>}
      <div className="row">{actions}{onClose && <button className="btn sm ghost" onClick={onClose}>Dismiss</button>}</div>
    </div>
  );
}

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>("input,textarea,select,button")?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab" && ref.current) {
        const f = Array.from(ref.current.querySelectorAll<HTMLElement>("button,input,textarea,select,a[href]")).filter(x => !x.hasAttribute("disabled"));
        if (!f.length) return;
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("keydown", key); prev?.focus(); };
  }, [onClose]);
  return (
    <div className="modal-bg" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={"modal" + (wide ? " wide" : "")} role="dialog" aria-modal="true" aria-label={title} ref={ref}>
        <header><h2>{title}</h2><button className="btn ghost sm" onClick={onClose} aria-label="Close dialog">✕</button></header>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export function useInterval(fn: () => void, ms: number | null) {
  const ref = useRef(fn); ref.current = fn;
  useEffect(() => { if (ms == null) return; const id = setInterval(() => ref.current(), ms); return () => clearInterval(id); }, [ms]);
}

export const ago = (iso: string) => {
  const s = Math.max(0, (Date.now() - new Date(iso + (iso.endsWith("Z") || iso.includes("+") ? "" : "Z")).getTime()) / 1000);
  if (s < 60) return "just now"; if (s < 3600) return `${Math.floor(s / 60)} min ago`; if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
};
export const kb = (n: number) => n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB";
