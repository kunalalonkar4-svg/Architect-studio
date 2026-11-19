import { useEffect, useRef, useState } from "react";
import { api, Full } from "./api";
import { ErrorBox, Notice, Spinner, toNotice } from "./ui";

interface Wall { id: string; level: string; x1: number; y1: number; x2: number; y2: number; t: number; kind: string }
interface Op { mark: string; level: string; type: "door" | "window"; cx: number; cy: number; w: number; h: number; sill: number; host: string | null }
interface Sp { key: string; name: string; kind: string; level: string; x: number; y: number; w: number; h: number; open: boolean }
interface Lv { id: string; name: string; elevation: number; height: number; slab: number; plinth: number; parapet: number }
interface M3 { revision: number; plot: { w: number; h: number } | null; ext_t: number; levels: Lv[]; walls: Wall[]; openings: Op[]; spaces: Sp[]; stairs: any[] }

type V3 = [number, number, number];
const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a: V3, b: V3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];

interface Face { pts: V3[]; color: [number, number, number]; edge?: boolean }
interface Item { c: V3; faces: Face[] }

/** Axis-aligned box faces (millimetres, z up). */
function box(x0: number, y0: number, z0: number, x1: number, y1: number, z1: number, col: [number, number, number]): Face[] {
  const p = (x: number, y: number, z: number): V3 => [x, y, z];
  return [
    { pts: [p(x0, y0, z1), p(x1, y0, z1), p(x1, y1, z1), p(x0, y1, z1)], color: col },
    { pts: [p(x0, y0, z0), p(x0, y1, z0), p(x1, y1, z0), p(x1, y0, z0)], color: col },
    { pts: [p(x0, y0, z0), p(x1, y0, z0), p(x1, y0, z1), p(x0, y0, z1)], color: col },
    { pts: [p(x1, y0, z0), p(x1, y1, z0), p(x1, y1, z1), p(x1, y0, z1)], color: col },
    { pts: [p(x1, y1, z0), p(x0, y1, z0), p(x0, y1, z1), p(x1, y1, z1)], color: col },
    { pts: [p(x0, y1, z0), p(x0, y0, z0), p(x0, y0, z1), p(x0, y1, z1)], color: col },
  ];
}

export function buildScene(m: M3): Item[] {
  const items: Item[] = [];
  const lv = Object.fromEntries(m.levels.map(l => [l.id, l]));
  const wallById = Object.fromEntries(m.walls.map(w => [w.id, w]));
  const top = m.levels[m.levels.length - 1];
  for (const w of m.walls) {
    const L = lv[w.level]; if (!L) continue;
    const t = w.t / 2; const hz = w.y1 === w.y2;
    const x0 = Math.min(w.x1, w.x2) - (hz ? t : t), x1 = Math.max(w.x1, w.x2) + (hz ? t : t);
    const y0 = Math.min(w.y1, w.y2) - t, y1 = Math.max(w.y1, w.y2) + t;
    const z0 = L.elevation + (L.id === m.levels[0].id ? 0 : 0), z1 = L.elevation + L.height - L.slab;
    const col: [number, number, number] = w.kind === "ext" ? [236, 230, 214] : [222, 222, 218];
    items.push({ c: [(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2], faces: box(x0, y0, z0, x1, y1, z1, col) });
  }
  for (const o of m.openings) {                                        // doors and windows as panels just proud of both wall faces
    const w = o.host ? wallById[o.host] : undefined; const L = lv[o.level]; if (!w || !L) continue;
    const hz = w.y1 === w.y2; const t = w.t / 2 + 8;
    const z0 = L.elevation + o.sill, z1 = z0 + o.h; const half = o.w / 2;
    const col: [number, number, number] = o.type === "door" ? [120, 84, 52] : [150, 200, 230];
    const faces: Face[] = [];
    for (const s of [-1, 1]) {
      const p = (a: number, z: number): V3 => hz ? [o.cx + a, w.y1 + s * t, z] : [w.x1 + s * t, o.cy + a, z];
      const pts = [p(-half, z0), p(half, z0), p(half, z1), p(-half, z1)];
      faces.push({ pts: s > 0 ? pts : pts.slice().reverse(), color: col, edge: true });
    }
    items.push({ c: [o.cx, o.cy, (z0 + z1) / 2 + 1], faces });
  }
  for (const L of m.levels) {                                          // slabs: floor of each level above ground, and the roof
    const sps = m.spaces.filter(s => s.level === L.id && !s.open);
    if (!sps.length) continue;
    const x0 = Math.min(...sps.map(s => s.x)) - m.ext_t / 2, x1 = Math.max(...sps.map(s => s.x + s.w)) + m.ext_t / 2;
    const y0 = Math.min(...sps.map(s => s.y)) - m.ext_t / 2, y1 = Math.max(...sps.map(s => s.y + s.h)) + m.ext_t / 2;
    const zr = L.elevation + L.height;
    items.push({ c: [(x0 + x1) / 2, (y0 + y1) / 2, zr], faces: box(x0 - 100, y0 - 100, zr - L.slab, x1 + 100, y1 + 100, zr, [190, 190, 186]) });
    if (L.id === top.id && L.parapet > 0) {
      const t = 115, ph = L.parapet; const col: [number, number, number] = [206, 200, 186];
      for (const [a, b, c, d] of [[x0 - 100, y0 - 100, x1 + 100, y0 - 100 + t], [x0 - 100, y1 + 100 - t, x1 + 100, y1 + 100], [x0 - 100, y0 - 100, x0 - 100 + t, y1 + 100], [x1 + 100 - t, y0 - 100, x1 + 100, y1 + 100]])
        items.push({ c: [(a + c) / 2, (b + d) / 2, zr + ph / 2], faces: box(a, b, zr, c, d, zr + ph, col) });
    }
  }
  const g0 = m.levels[0];
  const gsp = m.spaces.filter(s => s.level === g0.id && !s.open);
  if (gsp.length) {                                                    // plinth
    const x0 = Math.min(...gsp.map(s => s.x)) - m.ext_t / 2 - 150, x1 = Math.max(...gsp.map(s => s.x + s.w)) + m.ext_t / 2 + 150;
    const y0 = Math.min(...gsp.map(s => s.y)) - m.ext_t / 2 - 150, y1 = Math.max(...gsp.map(s => s.y + s.h)) + m.ext_t / 2 + 150;
    items.push({ c: [(x0 + x1) / 2, (y0 + y1) / 2, -g0.plinth / 2], faces: box(x0, y0, -g0.plinth, x1, y1, 0, [170, 168, 160]) });
  }
  for (const s of m.spaces) if (s.kind === "parking") {                // marked parking bay on the ground
    items.push({ c: [s.x + s.w / 2, s.y + s.h / 2, 5], faces: box(s.x, s.y, -g0.plinth, s.x + s.w, s.y + s.h, 5, [200, 200, 196]) });
  }
  return items;
}

interface Cam { yaw: number; pitch: number; dist: number; tx: number; ty: number; tz: number; walk: boolean; px: number; py: number }

function project(p: V3, c: Cam, W: number, H: number, near = 80): [number, number, number] | null {
  const eye: V3 = c.walk ? [c.px, c.py, 1600] : [c.tx - Math.sin(c.yaw) * Math.cos(c.pitch) * c.dist, c.ty - Math.cos(c.yaw) * Math.cos(c.pitch) * c.dist, c.tz + Math.sin(c.pitch) * c.dist];
  const fwd: V3 = [Math.sin(c.yaw) * Math.cos(c.pitch), Math.cos(c.yaw) * Math.cos(c.pitch), -Math.sin(c.pitch)];
  const right: V3 = [Math.cos(c.yaw), -Math.sin(c.yaw), 0];
  const up = cross(right, fwd);
  const d = sub(p, eye); const z = dot(d, fwd);
  if (z < near) return null;
  const f = (H * 0.5) / Math.tan((c.walk ? 70 : 38) * Math.PI / 360);
  return [W / 2 + dot(d, right) / z * f, H / 2 - dot(d, up) / z * f, z];
}

function eyeOf(c: Cam): V3 {
  return c.walk ? [c.px, c.py, 1600] : [c.tx - Math.sin(c.yaw) * Math.cos(c.pitch) * c.dist, c.ty - Math.cos(c.yaw) * Math.cos(c.pitch) * c.dist, c.tz + Math.sin(c.pitch) * c.dist];
}

/** Clip a polygon in camera space against the near plane by projecting only the part in front of the camera. */
function clipProject(pts: V3[], c: Cam, W: number, H: number): [number, number][] | null {
  const eye = eyeOf(c);
  const fwd: V3 = [Math.sin(c.yaw) * Math.cos(c.pitch), Math.cos(c.yaw) * Math.cos(c.pitch), -Math.sin(c.pitch)];
  const near = 80; const out: V3[] = [];
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[(i + 1) % pts.length];
    const da = dot(sub(a, eye), fwd) - near, db = dot(sub(b, eye), fwd) - near;
    if (da >= 0) out.push(a);
    if ((da >= 0) !== (db >= 0)) { const t = da / (da - db); out.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]); }
  }
  if (out.length < 3) return null;
  const r = out.map(p => project(p, c, W, H, near - 1)); if (r.some(x => !x)) return null;
  return r.map(x => [x![0], x![1]] as [number, number]);
}

function draw(ctx: CanvasRenderingContext2D, W: number, H: number, items: Item[], m: M3, c: Cam, dark: boolean) {
  const sky = ctx.createLinearGradient(0, 0, 0, H); sky.addColorStop(0, dark ? "#1b2a3d" : "#cfe3f3"); sky.addColorStop(1, dark ? "#2b3a2f" : "#e9efe4");
  ctx.fillStyle = sky; ctx.fillRect(0, 0, W, H);
  const eye = eyeOf(c); const light: V3 = [-0.4, -0.6, 0.7];
  if (m.plot) {                                                         // ground and plot boundary
    const g: V3[] = [[-6000, -6000, -m.levels[0].plinth], [m.plot.w + 6000, -6000, -m.levels[0].plinth], [m.plot.w + 6000, m.plot.h + 6000, -m.levels[0].plinth], [-6000, m.plot.h + 6000, -m.levels[0].plinth]];
    const q = clipProject(g, c, W, H);
    if (q) { ctx.beginPath(); q.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.closePath(); ctx.fillStyle = dark ? "#33432f" : "#cfdcc0"; ctx.fill(); }
    const pl: V3[] = [[0, 0, -m.levels[0].plinth + 2], [m.plot.w, 0, -m.levels[0].plinth + 2], [m.plot.w, m.plot.h, -m.levels[0].plinth + 2], [0, m.plot.h, -m.levels[0].plinth + 2]];
    const q2 = clipProject(pl, c, W, H);
    if (q2) { ctx.beginPath(); q2.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.closePath(); ctx.fillStyle = dark ? "#3d4f38" : "#dfe9d0"; ctx.fill(); ctx.setLineDash([8, 5]); ctx.strokeStyle = dark ? "#9fb08f" : "#6c7d5c"; ctx.lineWidth = 1.5; ctx.stroke(); ctx.setLineDash([]); }
  }
  const sorted = items.slice().sort((a, b) => dot(sub(b.c, eye), sub(b.c, eye)) - dot(sub(a.c, eye), sub(a.c, eye)));
  for (const it of sorted) for (const f of it.faces) {
    const n = cross(sub(f.pts[1], f.pts[0]), sub(f.pts[2], f.pts[0])); const nl = Math.hypot(...n) || 1;
    if (dot(n, sub(f.pts[0], eye)) >= 0) continue;                       // back face
    const q = clipProject(f.pts, c, W, H); if (!q) continue;
    const sh = 0.62 + 0.38 * Math.max(0, dot([n[0] / nl, n[1] / nl, n[2] / nl], light));
    const k = dark ? 0.78 : 1;
    ctx.beginPath(); q.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.closePath();
    ctx.fillStyle = `rgb(${Math.round(f.color[0] * sh * k)},${Math.round(f.color[1] * sh * k)},${Math.round(f.color[2] * sh * k)})`; ctx.fill();
    ctx.strokeStyle = f.edge ? "rgba(40,30,20,.55)" : "rgba(60,60,60,.28)"; ctx.lineWidth = f.edge ? 1.2 : 0.7; ctx.stroke();
  }
}

export default function View3D({ full }: { full: Full }) {
  const pid = full.project.id; const revId = full.current?.id;
  const [m, setM] = useState<M3 | null>(null); const [err, setErr] = useState<Notice | null>(null);
  const [walk, setWalk] = useState(false);
  const cv = useRef<HTMLCanvasElement>(null); const cam = useRef<Cam>({ yaw: -0.7, pitch: 0.5, dist: 20000, tx: 0, ty: 0, tz: 1500, walk: false, px: 0, py: 0 });
  const scene = useRef<Item[]>([]); const raf = useRef(0); const keys = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!revId) { setM(null); return; }
    let off = false; setErr(null);
    api<M3>(`/projects/${pid}/model3d`).then(x => { if (!off) setM(x); }).catch(e => !off && setErr(toNotice(e)));
    return () => { off = true; };
  }, [pid, revId]);

  useEffect(() => {
    if (!m) return;
    scene.current = buildScene(m);
    const all = m.spaces; const x0 = Math.min(...all.map(s => s.x)), x1 = Math.max(...all.map(s => s.x + s.w)), y0 = Math.min(...all.map(s => s.y)), y1 = Math.max(...all.map(s => s.y + s.h));
    const top = m.levels[m.levels.length - 1]; const span = Math.max(x1 - x0, y1 - y0, top.elevation + top.height);
    const c = cam.current; c.tx = (x0 + x1) / 2; c.ty = (y0 + y1) / 2; c.tz = (top.elevation + top.height) / 2; c.dist = span * 3.2;
    const d1 = m.openings.find(o => o.mark === "D1");
    if (d1) { const dx = d1.cx - c.tx, dy = d1.cy - c.ty; const L = Math.hypot(dx, dy) || 1; c.px = d1.cx + dx / L * 3200; c.py = d1.cy + dy / L * 3200; } else { c.px = c.tx; c.py = y0 - 3000; }
    paint();
  }, [m]);

  function paint() {
    cancelAnimationFrame(raf.current);
    raf.current = requestAnimationFrame(() => {
      const el = cv.current; if (!el || !m) return;
      const r = el.getBoundingClientRect(); const dpr = Math.min(2, window.devicePixelRatio || 1);
      if (el.width !== Math.round(r.width * dpr) || el.height !== Math.round(r.height * dpr)) { el.width = Math.round(r.width * dpr); el.height = Math.round(r.height * dpr); }
      const ctx = el.getContext("2d"); if (!ctx) return; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      cam.current.walk = walk;
      draw(ctx, r.width, r.height, scene.current, m, cam.current, window.matchMedia("(prefers-color-scheme: dark)").matches);
    });
  }
  useEffect(() => { paint(); }, [walk, m]);
  useEffect(() => { const f = () => paint(); window.addEventListener("resize", f); return () => { window.removeEventListener("resize", f); cancelAnimationFrame(raf.current); }; }, [m, walk]);

  const drag = useRef<{ x: number; y: number } | null>(null);
  const onDown = (e: React.PointerEvent) => { drag.current = { x: e.clientX, y: e.clientY }; (e.target as Element).setPointerCapture(e.pointerId); };
  const onMove = (e: React.PointerEvent) => {
    if (!drag.current) return; const c = cam.current; const dx = e.clientX - drag.current.x, dy = e.clientY - drag.current.y; drag.current = { x: e.clientX, y: e.clientY };
    if (walk) { c.yaw += dx * 0.005; c.pitch = Math.max(-0.5, Math.min(0.5, c.pitch - dy * 0.004)); }
    else { c.yaw -= dx * 0.006; c.pitch = Math.max(0.05, Math.min(1.45, c.pitch + dy * 0.005)); }
    paint();
  };
  const onWheel = (e: React.WheelEvent) => { if (!walk) { const c = cam.current; c.dist = Math.max(3000, Math.min(120000, c.dist * (1 + e.deltaY * 0.001))); paint(); } };
  function step(f: number, s: number) {
    const c = cam.current; const nx = c.px + (Math.sin(c.yaw) * f + Math.cos(c.yaw) * s) * 450, ny = c.py + (Math.cos(c.yaw) * f - Math.sin(c.yaw) * s) * 450;
    c.px = nx; c.py = ny; paint();
  }
  const onKey = (e: React.KeyboardEvent) => {
    const k = e.key.toLowerCase();
    if (walk) { if (k === "arrowup" || k === "w") step(1, 0); else if (k === "arrowdown" || k === "s") step(-1, 0); else if (k === "a") step(0, -1); else if (k === "d") step(0, 1); else if (k === "arrowleft") { cam.current.yaw -= 0.12; paint(); } else if (k === "arrowright") { cam.current.yaw += 0.12; paint(); } else return; }
    else { if (k === "arrowleft") cam.current.yaw += 0.1; else if (k === "arrowright") cam.current.yaw -= 0.1; else if (k === "+" || k === "=") cam.current.dist *= 0.9; else if (k === "-") cam.current.dist *= 1.1; else return; paint(); }
    e.preventDefault();
  };
  function toggleWalk() {
    const c = cam.current; const next = !walk;
    if (next) { c.pitch = 0; c.yaw = Math.atan2(c.tx - c.px, c.ty - c.py); } else { c.pitch = 0.5; c.yaw = -0.7; }
    setWalk(next);
  }

  if (!full.current) return <div className="empty-pane"><h3>No 3D view yet</h3><p className="muted">Generate the drawings first. The 3D view uses the same model.</p></div>;
  if (err) return <div className="panel"><ErrorBox n={err} /></div>;
  if (!m) return <div className="empty-pane"><Spinner label="Building the 3D view…" /></div>;
  return (
    <div className="v3">
      <div className="v3bar">
        <div className="seg" role="group" aria-label="3D mode"><button className={!walk ? "on" : ""} onClick={() => walk && toggleWalk()}>Orbit</button><button className={walk ? "on" : ""} onClick={() => !walk && toggleWalk()}>Walk</button></div>
        <small className="muted">{walk ? "Drag to look. W A S D or arrow keys to move." : "Drag to rotate. Scroll or + − to zoom."}</small>
      </div>
      <canvas ref={cv} className="v3cv" tabIndex={0} role="img" aria-label="3D view of the house: massing with doors and windows"
        onPointerDown={onDown} onPointerMove={onMove} onPointerUp={() => (drag.current = null)} onWheel={onWheel} onKeyDown={onKey} />
      {walk && <div className="v3pad" aria-label="Walk controls"><button className="btn" onClick={() => step(1, 0)} aria-label="Forward">▲</button><div><button className="btn" onClick={() => { cam.current.yaw -= 0.2; paint(); }} aria-label="Turn left">◀</button><button className="btn" onClick={() => step(-1, 0)} aria-label="Back">▼</button><button className="btn" onClick={() => { cam.current.yaw += 0.2; paint(); }} aria-label="Turn right">▶</button></div></div>}
      <p className="fine v3note">Massing view from the drawing model, for understanding the form. Finishes, roof shape and landscaping are not shown.</p>
    </div>
  );
}
