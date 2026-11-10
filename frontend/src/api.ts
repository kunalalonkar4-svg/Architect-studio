// Thin API client. The token lives in localStorage (per-browser); the Anthropic key and system prompt never reach the browser.
export type NextAction = string;
export interface ApiErr { code: string; message: string; next_actions: NextAction[]; detail?: any; status: number }

const TK = "drafta.token";
export const getToken = () => { try { return localStorage.getItem(TK); } catch { return null; } };
export const setToken = (t: string | null) => { try { t ? localStorage.setItem(TK, t) : localStorage.removeItem(TK); } catch { /* storage blocked */ } };

export class ApiError extends Error {
  err: ApiErr;
  constructor(err: ApiErr) { super(err.message); this.err = err; }
}

async function toError(r: Response): Promise<ApiError> {
  let body: any = null;
  try { body = await r.json(); } catch { /* not json */ }
  if (body?.error) return new ApiError({ ...body.error, next_actions: body.error.next_actions ?? [], status: r.status });
  if (body?.ok === false && body?.result?.error) return new ApiError({ ...body.result.error, next_actions: body.result.error.next_actions ?? [], status: r.status });
  if (body?.ok === false && body?.result?.ambiguous_dimensions) {
    return new ApiError({ code: "ambiguous_dimension", message: "A dimension has no unit. Say whether it is feet, metres or millimetres.", next_actions: ["Add a unit and save again"], status: r.status });
  }
  const msg = typeof body?.detail === "string" ? body.detail : Array.isArray(body?.detail) ? body.detail.map((d: any) => d.msg).join("; ") : `Request failed (${r.status})`;
  if (r.status === 401) { setToken(null); }
  return new ApiError({ code: r.status === 401 ? "unauthorized" : "http_" + r.status, message: msg, next_actions: r.status === 401 ? ["Sign in again"] : ["Try again"], status: r.status });
}

export async function api<T = any>(path: string, opts: { method?: string; json?: unknown; form?: FormData; signal?: AbortSignal } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const t = getToken(); if (t) headers.Authorization = `Bearer ${t}`;
  let body: BodyInit | undefined;
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.json); }
  if (opts.form) body = opts.form;
  let r: Response;
  try { r = await fetch("/api" + path, { method: opts.method ?? (body ? "POST" : "GET"), headers, body, signal: opts.signal }); }
  catch (e: any) {
    if (e?.name === "AbortError") throw e;
    throw new ApiError({ code: "network", message: "Cannot reach the server. Check your connection.", next_actions: ["Retry"], status: 0 });
  }
  if (!r.ok) throw await toError(r);
  if (r.status === 204) return undefined as T;
  return r.json();
}

export async function fetchBlobUrl(path: string): Promise<string> {
  const headers: Record<string, string> = {}; const t = getToken(); if (t) headers.Authorization = `Bearer ${t}`;
  const r = await fetch("/api" + path, { headers });
  if (!r.ok) throw await toError(r);
  return URL.createObjectURL(await r.blob());
}

export async function download(path: string, name: string) {
  const url = await fetchBlobUrl(path);
  const a = document.createElement("a"); a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

export type StreamEvent =
  | { type: "user_message"; id: string }
  | { type: "text"; delta: string }
  | { type: "event"; event: any }
  | { type: "error"; code: string; message: string; next_actions: string[]; retriable: boolean; message_id: string }
  | { type: "done"; message_id?: string; cancelled?: boolean; error?: boolean };

/** POST /chat and read the SSE stream with fetch so the Authorization header can be sent. */
export async function streamChat(pid: string, body: { content: string; attachment_ids: string[]; consent: boolean; retry_of?: string }, onEvent: (e: StreamEvent) => void, signal: AbortSignal) {
  const headers: Record<string, string> = { "Content-Type": "application/json" }; const t = getToken(); if (t) headers.Authorization = `Bearer ${t}`;
  let r: Response;
  try { r = await fetch(`/api/projects/${pid}/chat`, { method: "POST", headers, body: JSON.stringify(body), signal }); }
  catch (e: any) { if (e?.name === "AbortError") throw e; throw new ApiError({ code: "network", message: "Cannot reach the server. Check your connection.", next_actions: ["Retry"], status: 0 }); }
  if (!r.ok || !r.body) throw await toError(r);
  const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
      const line = chunk.split("\n").find(l => l.startsWith("data: "));
      if (line) { try { onEvent(JSON.parse(line.slice(6))); } catch { /* ignore malformed frame */ } }
    }
  }
}

// ---- types (subset of the server JSON)
export interface User { id: string; email: string; display_name: string; firm_name: string; firm_line: string; has_logo: boolean }
export interface AiStatus { provider: string; live: boolean; configured: boolean; model: string | null; message: string }
export interface ProjectSummary { id: string; name: string; status: string; client: string; address: string; updated_at: string; current_revision_id: string | null; review_status: string }
export interface Sheet { id: string; number: string; title: string; kind: string; paper: string; orientation: string; scale: number; rev: number; artifacts: Record<string, string>; ready: boolean }
export interface Issue { code: string; severity: "error" | "warning" | "info"; message: string; fix?: string; objects?: string[] }
export interface Revision { id: string; number: number; summary: string; changes: any[]; created_at: string; render_status: string; render_error?: any; sheets?: Sheet[]; validation?: Issue[]; brief?: any; model_summary?: any }
export interface Job { id: string; kind: string; state: string; progress: number; step: string; error?: string | null; error_detail?: any; revision_id: string; params: any; artifact?: { id: string; name: string; size: number; kind: string; checks?: any }; created_at: string }
export interface Proposal { id: string; kind: string; state: string; summary: string; changes: any[]; affected_sheets: any[]; options: any[]; issues: Issue[]; blocking: Issue[]; base_revision_id: string }
export interface Message { id: string; role: "user" | "assistant" | "system"; content: string; events: any[]; status: string; attachment_ids: string[]; created_at: string }
export interface Full {
  project: ProjectSummary; brief: any; missing: { id: string; question: string }[]; messages: Message[]; revisions: Revision[]; current: Revision | null; last_good: Revision | null;
  proposals: Proposal[]; jobs: Job[]; attachments: { id: string; filename: string; mime: string; size: number }[]; ai: AiStatus; use_assumptions: boolean;
}
