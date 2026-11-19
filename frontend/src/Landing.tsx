import { useEffect, useRef, useState } from "react";
import Auth from "./Auth";
import { AiStatus, User } from "./api";
import "./landing.css";

interface Feat { key: string; icon: string; title: string; text: string; points: string[]; mode: string; prompt: string; steps: string[]; img?: string; alt?: string }
const FEATS: Feat[] = [
  { key: "plan", icon: "M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z", title: "Plan", mode: "Plan",
    text: "Say your plot size and rooms the way you would to an architect. Drafta draws a dimensioned plan, to scale.",
    points: ["Feet or metres, any plot size", "English, Hindi or Hinglish", "Asks for the plot size if you forget it"],
    prompt: "20×50 plot, road on the east. 2 BHK with parking.", steps: ["Reading the plot and road side", "Placing rooms, doors and stair", "Dimensioning the sheet"],
    img: "/samples/s20x50-plan.jpg", alt: "Dimensioned floor plan of a 20 by 50 foot 2 BHK house" },
  { key: "elev", icon: "M3 20h18M5 20V9l7-5 7 5v11M10 20v-6h4v6", title: "Elevations and sections", mode: "Elevation",
    text: "Ask for the front elevation or a section. You get a 2D drawing with levels and a scale, from the same plan.",
    points: ["Four elevations with levels and openings", "Sections through slab, stair and floor heights", "Every sheet changes when the plan changes"],
    prompt: "Show me the front elevation in scale.", steps: ["Reading floor heights from the plan", "Projecting openings to the wall", "Adding levels and scale"],
    img: "/samples/d40x50-elevations.jpg", alt: "Elevation sheet of a 40 by 50 foot duplex" },
  { key: "checks", icon: "M12 3l8 3v6c0 4.5-3.3 7.8-8 9-4.7-1.2-8-4.5-8-9V6zM9 12l2 2 4-4", title: "Vastu and checks", mode: "Check",
    text: "Ask if the plan follows Vastu, or if a room gets enough light. The answer comes from the real drawing, with numbers.",
    points: ["Vastu score by room, with what to move", "Light and ventilation per room", "Column spans flagged for review"],
    prompt: "Check this plan for Vastu and tell me what to fix.", steps: ["Reading room positions", "Scoring each room against Vastu rules", "Listing fixes, nothing changed yet"] },
  { key: "cols", icon: "M6 4h12M6 20h12M9 4v16M15 4v16", title: "Column placement", mode: "Structure",
    text: "Ask for columns and a grid appears. Ask to add, remove or move one by name. Hand-placed columns are marked.",
    points: ["Column grid with labels C1, C2…", "“Move C3 300 mm east” in plain words", "Marked preliminary, for your engineer to design"],
    prompt: "Place the structural columns and show the grid.", steps: ["Snapping columns to wall corners", "Numbering the grid", "Marking the sheet preliminary"],
    img: "/samples/d40x50-structure.jpg", alt: "Preliminary structure sheet with column grid" },
  { key: "share", icon: "M12 4v11M7 9l5-5 5 5M5 20h14", title: "3D view and sharing", mode: "Share",
    text: "Turn the plan into a 3D model you can orbit. Send a link so family and your engineer can look and comment.",
    points: ["Orbit the building in 3D", "Share link with view-only access", "Comments collected on the project"],
    prompt: "Create a link I can send to my family.", steps: ["Building the 3D model", "Creating a private link", "Waiting for comments"] },
];

const MORE: [string, string, string][] = [
  ["M4 4h16v16H4zM4 12h16M12 4v16", "Drawing set", "Cover, site, floor plans, roof, elevations, sections, schedules."],
  ["M4 20l4-1 11-11-3-3L5 16z", "Plain-words edits", "Ask for a bigger kitchen. You confirm each change first."],
  ["M12 4v11M7 11l5 5 5-5M5 20h14", "PDF, DXF and PNG", "Vector PDF, DXF for CAD and PNG sheets."],
  ["M5 5h14v14H5zM9 9h6M9 13h6", "Excel estimate", "Bill of quantities with live formulas and your own rates."],
  ["M4 16l5-8 4 5 3-3 4 6z", "Irregular plots", "Enter plot corners. The building is fitted inside the setbacks."],
  ["M12 8v5l3 2M12 3a9 9 0 100 18 9 9 0 000-18z", "Revisions", "Every change is a saved revision you can go back to."],
  ["M4 6h16M4 12h16M4 18h10", "Contractor checklist", "Build stages, specification notes and questions to ask."],
  ["M3 12h4l2-6 4 12 2-6h6", "MEP concept", "Plumbing, electrical and drainage as a concept layout."],
  ["M12 3v18M3 12h18", "Hindi and Hinglish", "Write in the language you think in."],
  ["M7 4h10v16H7zM10 8h4", "Review checklist", "A list for your architect to confirm before anything is final."],
  ["M4 20V8l8-4 8 4v12M9 20v-6h6v6", "Free samples", "Open a finished sample project with no sign-up."],
  ["M12 3l8 3v6c0 4.5-3.3 7.8-8 9-4.7-1.2-8-4.5-8-9V6z", "Private by default", "Your projects are yours. Links are opt-in."],
];

const SHEETS: [string, string, string][] = [
  ["G-001", "Cover and drawing index", "Project data, plot, areas, sheet list"],
  ["A-101", "Site plan", "Plot, setbacks, building footprint, north"],
  ["A-102", "Floor plans", "One sheet per level, dimensioned, to scale"],
  ["A-103", "Roof plan", "Slopes, parapet and water outlets"],
  ["A-201", "Elevations", "Four sides with levels and openings"],
  ["A-301", "Sections", "Slabs, stair and floor heights"],
  ["A-401", "Schedules", "Doors, windows and room areas"],
  ["S-101", "Structure (preliminary)", "Column grid for your engineer to review"],
];

function Icon({ d, size = 20 }: { d: string; size?: number }) {
  return <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden><path d={d} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

function Demo({ f }: { f: Feat }) {
  const [n, setN] = useState(0); const [step, setStep] = useState(0);
  useEffect(() => {
    setN(0); setStep(0);
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setN(f.prompt.length); return; }
    let i = 0; const t = setInterval(() => { i++; setN(i); if (i >= f.prompt.length) clearInterval(t); }, 28);
    const s = setInterval(() => setStep(x => (x + 1) % f.steps.length), 1700);
    return () => { clearInterval(t); clearInterval(s); };
  }, [f.key]);
  const done = n >= f.prompt.length;
  return (
    <div className="lp-demo" aria-label={`Example: ${f.title}`}>
      <div className="lp-demo-body">
        <div className="lp-u">{f.prompt.slice(0, n)}{!done && <i className="caret" aria-hidden />}</div>
        {done && (f.img
          ? <div className="lp-r"><div className="lp-think"><span className="dotsrow" aria-hidden><i /><i /><i /></span> Drafta drew this</div><img src={f.img} alt={f.alt} loading="lazy" /></div>
          : <div className="lp-r"><div className="lp-think"><span className="dotsrow" aria-hidden><i /><i /><i /></span> Drafta is working</div><div className="lp-step" key={step}>{f.steps[step]}</div></div>)}
      </div>
      <div className="lp-compose"><span aria-hidden>+</span><em>Ask anything about your plan…</em><b>{f.mode}</b><i aria-hidden><svg viewBox="0 0 20 20" width="12" height="12"><path d="M10 16V4M5 9l5-5 5 5" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg></i></div>
    </div>
  );
}

export default function Landing({ onAuthed }: { onAuthed: (u: User, ai: AiStatus) => void }) {
  const [auth, setAuth] = useState(false); const [menu, setMenu] = useState(false); const [active, setActive] = useState(0);
  const refs = useRef<(HTMLElement | null)[]>([]);
  useEffect(() => {
    if (auth || !("IntersectionObserver" in window)) return;
    const io = new IntersectionObserver(es => {
      es.forEach(e => { if (e.isIntersecting) setActive(Number((e.target as HTMLElement).dataset.i)); });
    }, { rootMargin: "-40% 0px -45% 0px" });
    refs.current.forEach(r => r && io.observe(r));
    return () => io.disconnect();
  }, [auth]);
  if (auth) return (
    <div className="lp-authwrap">
      <button className="lp-back" onClick={() => setAuth(false)}>Back to home</button>
      <Auth onAuthed={onAuthed} />
    </div>
  );
  const go = () => { setAuth(true); window.scrollTo(0, 0); };
  const f = FEATS[active];
  return (
    <div className="lp">
      <header className="lp-nav">
        <a className="lp-brand" href="#top"><span className="logo-mark" aria-hidden /> Drafta</a>
        <nav className={menu ? "open" : ""} aria-label="Sections" onClick={() => setMenu(false)}>
          <a href="#features">Features</a><a href="#set">Drawing set</a><a href="#more">More</a><a href="#/sample">Try a sample</a><a href="#limits">Limits</a>
          <button className="lp-signin" onClick={go}>Sign in</button>
        </nav>
        <button className="lp-pillbtn dark lp-navcta" onClick={go}>Get started</button>
        <button className="lp-menu" aria-label="Menu" aria-expanded={menu} onClick={() => setMenu(m => !m)}><span /><span /></button>
      </header>

      <section className="lp-hero" id="top">
        <div className="lp-eyebrow"><span className="logo-mark" aria-hidden /> Drafta <i /> <span>AI house plan studio for the web</span></div>
        <h1>House plans, drawn<br />from a conversation.</h1>
        <p>Describe your plot in plain words. Drafta returns dimensioned plans, elevations, column grids and an estimate.<br />Works in English, Hindi and Hinglish.</p>
        <div className="lp-ctas">
          <button className="lp-pillbtn dark" onClick={go}>Start a project <svg viewBox="0 0 20 20" width="12" height="12" aria-hidden><path d="M7 4l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg></button>
          <a className="lp-pillbtn light" href="#/sample">See a sample</a>
        </div>
      </section>

      <section className="lp-feat" id="features">
        <div className="lp-feat-list">
          {FEATS.map((x, i) => (
            <article key={x.key} data-i={i} ref={el => { refs.current[i] = el; }} className={i === active ? "on" : ""}>
              <h2><Icon d={x.icon} size={30} /> {x.title}</h2>
              <p>{x.text}</p>
              <ul>{x.points.map(p => <li key={p}><svg viewBox="0 0 20 20" width="14" height="14" aria-hidden><path d="M4 10.5l4 4 8-9" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>{p}</li>)}</ul>
            </article>
          ))}
        </div>
        <div className="lp-feat-card"><div className="sticky"><Demo f={f} /></div></div>
      </section>

      <section className="lp-sec" id="set">
        <h2>A real drawing set</h2>
        <p className="lead">Every project comes with the sheets an architect would hand over for a house, numbered and indexed.</p>
        <div className="lp-gal">
          <figure><img loading="lazy" src="/samples/d40x50-plan.jpg" alt="Floor plan sheet of a 40 by 50 foot duplex" /><figcaption>Plan, 40 × 50 ft duplex</figcaption></figure>
          <figure><img loading="lazy" src="/samples/d40x50-section.jpg" alt="Section sheet" /><figcaption>Section</figcaption></figure>
        </div>
        <div className="lp-table"><table>
          <thead><tr><th scope="col">Sheet</th><th scope="col">Title</th><th scope="col">Shows</th></tr></thead>
          <tbody>{SHEETS.map(s => <tr key={s[0]}><th scope="row">{s[0]}</th><td>{s[1]}</td><td>{s[2]}</td></tr>)}</tbody>
        </table></div>
      </section>

      <section className="lp-sec" id="more">
        <h2>Also included</h2>
        <p className="lead">From a first idea to a drawing set you can hand to your engineer.</p>
        <div className="lp-more">
          {MORE.map(m => <div key={m[1]}><Icon d={m[0]} /><h3>{m[1]}</h3><p>{m[2]}</p></div>)}
        </div>
      </section>

      <section className="lp-sec" id="start">
        <h2>Begin in three steps</h2>
        <p className="lead">Create an account with your email and try your first plot.</p>
        <div className="lp-steps">
          <div><small>01</small><h3>Create an account</h3><p>Runs in your browser. Nothing to install.</p></div>
          <div><small>02</small><h3>Describe your plot</h3><p>Plot size, road side, rooms. Plain words are fine.</p></div>
          <div><small>03</small><h3>Review the drawings</h3><p>Ask for changes, a Vastu check or columns, then export.</p></div>
        </div>
        <div className="lp-ctas">
          <button className="lp-pillbtn dark" onClick={go}>Start a project <svg viewBox="0 0 20 20" width="12" height="12" aria-hidden><path d="M7 4l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg></button>
          <a className="lp-pillbtn light" href="#/sample">Try a sample</a>
        </div>
      </section>

      <section className="lp-sec" id="limits">
        <h2>What Drafta is not</h2>
        <ul className="lp-limits">
          <li>These are concept drawings. They are not stamped, approved or ready for construction.</li>
          <li>Structure sheets are preliminary. A licensed structural engineer must design and sign the real thing.</li>
          <li>Vastu, light and ventilation results are guidance. Check setbacks, FAR and permissions with your local authority and a licensed architect before building.</li>
        </ul>
      </section>

      <footer className="lp-foot">
        <div className="lp-foot-in">
          <div><span className="lp-brand"><span className="logo-mark" aria-hidden /> Drafta</span><p>Concept drawings only. Not a substitute for a licensed professional.</p></div>
          <div><h4>Product</h4><a href="#features">Features</a><a href="#set">Drawing set</a><a href="#more">More</a></div>
          <div><h4>Try</h4><a href="#/sample">Sample project</a><button className="lp-link" onClick={go}>Sign in</button></div>
          <div><h4>Good to know</h4><a href="#limits">Limits</a></div>
        </div>
      </footer>
    </div>
  );
}
