import { useState } from "react";
import Auth from "./Auth";
import { AiStatus, User } from "./api";
import "./landing.css";

const FEATURES = [
  ["#efe3fb", "Create new plans", "Tell Drafta your plot size and how many bedrooms. It designs the rooms, doors, windows and stair for you.", "M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z"],
  ["#dff4f1", "Design and iterate", "Ask for a bigger kitchen or a bedroom upstairs in plain words. You confirm each change before it is applied.", "M4 20l4-1 11-11-3-3L5 16zM14 6l3 3"],
  ["#fde8dc", "Export and estimate", "Download vector PDF, DXF for CAD and an Excel bill of quantities with live formulas.", "M12 4v11M7 11l5 5 5-5M5 20h14"],
];
const SHEETS: [string, string, string][] = [
  ["G-001", "Cover and drawing index", "Project data, plot, areas, sheet list"],
  ["A-101", "Site plan", "Plot, setbacks, building footprint, north"],
  ["A-102", "Floor plans", "One sheet per level, dimensioned, to scale"],
  ["A-103", "Roof plan", "Slopes, parapet and water outlets"],
  ["A-201", "Elevations", "Four sides with levels and openings"],
  ["A-301", "Sections", "Slabs, stair and floor heights"],
  ["A-401", "Schedules", "Doors, windows and room areas"],
  ["S-101", "Structure (preliminary)", "Column grid and beam layout for review"],
];
const STEPS = [
  ["Tell us the plot", "Say it the way you would to an architect: “40×50 duplex, 4 BHK, road on the south.” English, Hindi or Hinglish."],
  ["Drafta designs the plan", "Rooms are placed and checked. Anything that does not fit is fixed before you see it."],
  ["Review and change", "Ask for edits in plain words. Each change is saved as a revision you can go back to."],
  ["Export the set", "PDF, DXF, PNG and an Excel estimate, ready to share with your engineer."],
];

export default function Landing({ onAuthed }: { onAuthed: (u: User, ai: AiStatus) => void }) {
  const [auth, setAuth] = useState(false); const [menu, setMenu] = useState(false);
  if (auth) return (
    <div className="lp-authwrap">
      <button className="lp-back" onClick={() => setAuth(false)}>Back to home</button>
      <Auth onAuthed={onAuthed} />
    </div>
  );
  const go = () => { setAuth(true); window.scrollTo(0, 0); };
  const Cta = ({ label = "Get started for free" }: { label?: string }) => (
    <button className="lp-cta" onClick={go}>{label}<span aria-hidden><svg viewBox="0 0 20 20" width="14" height="14"><path d="M4 10h11M11 5l5 5-5 5" fill="none" stroke="#111" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg></span></button>
  );
  return (
    <div className="lp">
      <header className="lp-nav">
        <a className="lp-brand" href="#top"><span className="logo-mark" aria-hidden /> Drafta</a>
        <nav className={menu ? "open" : ""} aria-label="Sections" onClick={() => setMenu(false)}>
          <a href="#features">Features</a><a href="#set">Drawing set</a><a href="#how">How it works</a><a href="#limits">Limits</a>
          <button className="lp-link" onClick={go}>Sign in</button>
        </nav>
        <button className="lp-menu" aria-label="Menu" aria-expanded={menu} onClick={() => setMenu(m => !m)}><span /><span /></button>
      </header>

      <section className="lp-hero" id="top">
        <h1>The AI house plan studio</h1>
        <p>Design residential plans with AI. Give your plot size and BHK, and get the full drawing set and an estimate.</p>
        <Cta />
        <div className="lp-frame">
          <div className="lp-win">
            <div className="lp-win-bar"><span>Projects <i>/</i> <b>40 × 50 duplex</b></span><span className="lp-pill">Export</span></div>
            <div className="lp-win-body">
              <div className="lp-chat">
                <div className="u">40×50 plot, road on south. Duplex, 4 BHK, parking.</div>
                <div className="a">Done. Ground floor has parking, living, kitchen and 1 bedroom. First floor has 3 bedrooms. Stair is checked for headroom.</div>
                <div className="in">Make the kitchen bigger</div>
              </div>
              <img src="/samples/d40x50-plan.jpg" alt="Floor plan sheet of a 40 by 50 foot duplex" width="2000" height="1413" fetchPriority="high" />
            </div>
          </div>
        </div>
      </section>

      <section className="lp-sec" id="features">
        <h2>The future of home design</h2>
        <p className="lead">Generate new layouts, refine them in plain words, and take the drawings straight to your engineer.</p>
        <div className="lp-cards">
          {FEATURES.map(f => (
            <article key={f[1]} className="lp-card">
              <span className="ic" style={{ background: f[0] }}><svg viewBox="0 0 24 24" width="18" height="18"><path d={f[3]} fill="none" stroke="#222" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg></span>
              <h3>{f[1]}</h3><p>{f[2]}</p>
            </article>))}
        </div>
      </section>

      <section className="lp-sec" id="set">
        <h2>A real drawing set</h2>
        <p className="lead">Every project comes with the sheets an architect would hand over for a house, numbered and indexed.</p>
        <div className="lp-gal">
          <figure><img loading="lazy" src="/samples/s20x50-plan.jpg" alt="Plan of a 20 by 50 foot 2 BHK house" /><figcaption>20 × 50 ft, 2 BHK plan</figcaption></figure>
          <figure><img loading="lazy" src="/samples/d40x50-elevations.jpg" alt="Elevation sheet" /><figcaption>Elevations</figcaption></figure>
          <figure><img loading="lazy" src="/samples/d40x50-section.jpg" alt="Section sheet" /><figcaption>Section</figcaption></figure>
          <figure><img loading="lazy" src="/samples/d40x50-structure.jpg" alt="Preliminary structure sheet" /><figcaption>Structure, preliminary</figcaption></figure>
        </div>
        <div className="lp-table"><table>
          <thead><tr><th scope="col">Sheet</th><th scope="col">Title</th><th scope="col">Shows</th></tr></thead>
          <tbody>{SHEETS.map(s => <tr key={s[0]}><th scope="row">{s[0]}</th><td>{s[1]}</td><td>{s[2]}</td></tr>)}</tbody>
        </table></div>
      </section>

      <section className="lp-sec" id="how">
        <h2>How it works</h2>
        <div className="lp-cards four">
          {STEPS.map((s, i) => <article key={i} className="lp-card"><span className="num" aria-hidden>{i + 1}</span><h3>{s[0]}</h3><p>{s[1]}</p></article>)}
        </div>
      </section>

      <section className="lp-sec" id="boq">
        <h2>An estimate you can edit</h2>
        <p className="lead">The bill of quantities opens in Excel. Change a rate and the totals update.</p>
        <div className="lp-table narrow" role="img" aria-label="Sample bill of quantities rows"><table>
          <thead><tr><th>Item</th><th>Unit</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead>
          <tbody>
            <tr><td>Excavation in foundation</td><td>cum</td><td>62.4</td><td>350</td><td>21,840</td></tr>
            <tr><td>RCC M25 in columns and beams</td><td>cum</td><td>31.8</td><td>9,200</td><td>292,560</td></tr>
            <tr><td>Brick masonry, 230 mm</td><td>cum</td><td>48.2</td><td>6,100</td><td>294,020</td></tr>
            <tr><td>Plaster, 12 mm cement</td><td>sqm</td><td>612</td><td>310</td><td>189,720</td></tr>
          </tbody></table></div>
        <p className="fine">Sample rows. Rates are placeholders; set your local rates in the estimate panel.</p>
      </section>

      <section className="lp-sec" id="limits">
        <h2>What Drafta is not</h2>
        <ul className="lp-limits">
          <li>These are concept drawings. They are not stamped, approved or ready for construction.</li>
          <li>Structure sheets are preliminary. A licensed structural engineer must design and sign the real thing.</li>
          <li>Check setbacks, FAR and permissions with your local authority and a licensed architect before building.</li>
        </ul>
      </section>

      <section className="lp-final">
        <h2>Start with your plot size</h2>
        <Cta />
      </section>
      <footer className="lp-foot"><span>Drafta</span><span>Concept drawings only. Not a substitute for a licensed professional.</span></footer>
    </div>
  );
}
