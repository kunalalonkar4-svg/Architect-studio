import { useState } from "react";
import Auth from "./Auth";
import { AiStatus, User } from "./api";
import "./landing.css";

const SHEETS: [string, string, string][] = [
  ["G-001", "Cover and drawing index", "Project data, plot, areas, sheet list"],
  ["A-101", "Site plan", "Plot, setbacks, building footprint, north"],
  ["A-102", "Floor plans", "One sheet per level, dimensioned, to scale"],
  ["A-103", "Roof plan", "Slopes, parapet, headroom and water outlets"],
  ["A-201", "Elevations", "Four sides with levels, openings and finishes"],
  ["A-301", "Section", "Slabs, stair, floor heights through the building"],
  ["A-401", "Schedules", "Doors, windows and room areas"],
  ["S-101", "Structure (preliminary)", "Column grid and beam layout for review"],
];

const STEPS = [
  ["Tell us the plot", "Say it the way you would to an architect: “40×50 duplex, 4 BHK, road on the south.” English, Hindi or Hinglish."],
  ["Drafta designs the plan", "Rooms are placed, doors and windows are fitted, and the stair is checked for headroom. Anything that does not fit is fixed before you see it."],
  ["Review and change", "Ask for a bigger kitchen or a bedroom moved upstairs. Changes show as a proposal you confirm, and each one is saved as a revision."],
  ["Export the set", "Download a vector PDF, DXF for CAD, PNG, and an Excel bill of quantities with live formulas."],
];

export default function Landing({ onAuthed }: { onAuthed: (u: User, ai: AiStatus) => void }) {
  const [auth, setAuth] = useState(false);
  if (auth) return (
    <div className="lp-authwrap">
      <button className="lp-back" onClick={() => setAuth(false)}>Back to home</button>
      <Auth onAuthed={onAuthed} />
    </div>
  );
  const go = () => { setAuth(true); window.scrollTo(0, 0); };
  return (
    <div className="lp">
      <header className="lp-nav">
        <a className="lp-brand" href="#top"><span className="logo-mark" aria-hidden /> Drafta</a>
        <nav aria-label="Sections">
          <a href="#set">Drawing set</a><a href="#how">How it works</a><a href="#boq">Estimate</a><a href="#limits">Limits</a>
        </nav>
        <button className="lp-btn ghost" onClick={go}>Sign in</button>
      </header>

      <section className="lp-hero" id="top">
        <div className="lp-hero-copy">
          <h1>From plot size to a full drawing set in minutes</h1>
          <p>Tell Drafta your plot and how many bedrooms you need. It designs the plan, draws every sheet to scale, and prepares a cost estimate you can open in Excel.</p>
          <div className="lp-cta">
            <button className="lp-btn primary" onClick={go}>Start a project</button>
            <a className="lp-btn" href="#set">See a sample set</a>
          </div>
          <p className="lp-note">20×40, 30×50, 40×50 duplex or any other plot. 1 to 5 BHK. Concept drawings, free to try.</p>
        </div>
        <figure className="lp-sheet">
          <img src="/samples/d40x50-plan.jpg" alt="Floor plan sheet for a 40 by 50 foot duplex with dimensions and room labels" width="2000" height="1413" fetchPriority="high" />
          <figcaption>
            <span>Sheet A-102 · Floor plans</span>
            <span>40 × 50 ft duplex, 4 BHK · A1 · 1:50</span>
          </figcaption>
        </figure>
      </section>

      <section className="lp-band" aria-label="What you get">
        <dl>
          <div><dt>8+</dt><dd>sheets per project</dd></div>
          <div><dt>PDF · DXF · PNG</dt><dd>vector exports</dd></div>
          <div><dt>Excel</dt><dd>bill of quantities</dd></div>
          <div><dt>Hindi, Hinglish, English</dt><dd>type it your way</dd></div>
        </dl>
      </section>

      <section className="lp-sec" id="set">
        <div className="lp-sec-head">
          <h2>The drawing set</h2>
          <p>Every project comes with the sheets an architect would hand over for a house, numbered and indexed.</p>
        </div>
        <div className="lp-set">
          <table>
            <thead><tr><th scope="col">Sheet</th><th scope="col">Title</th><th scope="col">Shows</th></tr></thead>
            <tbody>{SHEETS.map(s => <tr key={s[0]}><th scope="row">{s[0]}</th><td>{s[1]}</td><td>{s[2]}</td></tr>)}</tbody>
          </table>
          <div className="lp-thumbs">
            <figure><img loading="lazy" src="/samples/d40x50-elevations.jpg" alt="Elevation sheet" /><figcaption>A-201 Elevations</figcaption></figure>
            <figure><img loading="lazy" src="/samples/d40x50-section.jpg" alt="Section sheet" /><figcaption>A-301 Section</figcaption></figure>
            <figure><img loading="lazy" src="/samples/s20x50-plan.jpg" alt="Plan of a 20 by 50 foot 2 BHK house" /><figcaption>20 × 50 ft, 2 BHK</figcaption></figure>
            <figure><img loading="lazy" src="/samples/d40x50-structure.jpg" alt="Preliminary structure sheet" /><figcaption>S-101 Structure, preliminary</figcaption></figure>
          </div>
        </div>
      </section>

      <section className="lp-sec alt" id="how">
        <div className="lp-sec-head"><h2>How it works</h2></div>
        <ol className="lp-steps">
          {STEPS.map((s, i) => <li key={i}><span className="n" aria-hidden>{i + 1}</span><div><h3>{s[0]}</h3><p>{s[1]}</p></div></li>)}
        </ol>
      </section>

      <section className="lp-sec" id="boq">
        <div className="lp-sec-head">
          <h2>An estimate you can edit</h2>
          <p>The bill of quantities downloads as an Excel file. Change a rate and the totals update, because the formulas are live.</p>
        </div>
        <div className="lp-xl" role="img" aria-label="Sample bill of quantities rows">
          <table>
            <thead><tr><th>Item</th><th>Unit</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead>
            <tbody>
              <tr><td>Excavation in foundation</td><td>cum</td><td>62.4</td><td>350</td><td>21,840</td></tr>
              <tr><td>RCC M25 in columns and beams</td><td>cum</td><td>31.8</td><td>9,200</td><td>292,560</td></tr>
              <tr><td>Brick masonry, 230 mm</td><td>cum</td><td>48.2</td><td>6,100</td><td>294,020</td></tr>
              <tr><td>Plaster, 12 mm cement</td><td>sqm</td><td>612</td><td>310</td><td>189,720</td></tr>
            </tbody>
          </table>
          <p className="lp-note">Sample rows only. Rates are placeholders; set your local rates in the estimate panel.</p>
        </div>
      </section>

      <section className="lp-sec alt" id="limits">
        <div className="lp-sec-head"><h2>What Drafta is not</h2></div>
        <ul className="lp-limits">
          <li>These are concept drawings. They are not stamped, approved or ready for construction.</li>
          <li>Structure sheets are preliminary. A licensed structural engineer must design and sign the real thing.</li>
          <li>Check setbacks, FAR and permissions with your local authority and a licensed architect before building.</li>
        </ul>
      </section>

      <section className="lp-final">
        <h2>Start with your plot size</h2>
        <button className="lp-btn primary" onClick={go}>Start a project</button>
      </section>
      <footer className="lp-foot"><span>Drafta</span><span>Concept drawings only. Not a substitute for a licensed professional.</span></footer>
    </div>
  );
}
