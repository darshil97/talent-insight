import Link from "next/link";

const steps = [
  { number: "01", title: "Start with a role", description: "Review the requirements and the candidates attached to that job." },
  { number: "02", title: "Compare evidence", description: "Use a job-specific assessment as a starting point for human review." },
  { number: "03", title: "Continue the conversation", description: "Follow up on open questions before making a decision." },
] as const;

const features = [
  { tag: "EVIDENCE", title: "Every fact has a source", description: "Each extracted fact links to an exact quote in the resume. Facts that cannot be found in the source are dropped, never repaired." },
  { tag: "COMPARABLE", title: "Similar experience counts", description: "Comparable tools or adjacent work, such as GCP for an AWS role, earn 0.75 credit instead of nothing. The reason names what substitutes for what." },
  { tag: "APPLIED", title: "Work over keywords", description: "A skill shown in a real role or project counts more than one that is only listed in a skills section." },
  { tag: "UNKNOWN", title: "Missing is not a zero", description: "When the resume is silent, the requirement stays unknown: it counts at half credit in the estimate and lowers the confidence shown beside it, instead of counting as a failure." },
  { tag: "AVAILABILITY", title: "Time to join, gently", description: "A shorter notice period adds a small ranking bonus of up to +5. Not provided never lowers a candidate, and the match score itself is unchanged." },
] as const;

const credits = [
  { label: "Met", detail: "shown in actual work", value: "1.0", width: 100 },
  { label: "Comparable", detail: "similar tool or adjacent work", value: "0.75", width: 75 },
  { label: "Partial", detail: "narrower, below threshold or only listed", value: "0.5", width: 50 },
  { label: "Not met", detail: "the resume states otherwise", value: "0", width: 0 },
] as const;

export default function Home() {
  return <>
    <section className="mission-intro" aria-labelledby="overview-heading">
      <div className="mission-intro-copy">
        <p className="mission-kicker">RECRUITING, WITH CONTEXT</p>
        <h1 id="overview-heading">A clearer view of<br />every candidate<span>.</span></h1>
        <p>Bring job requirements, candidate evidence and thoughtful questions into one place.</p>
        <Link href="/jobs" className="mission-button mission-intro-button">Explore jobs <span aria-hidden="true">↗</span></Link>
      </div>
      <div className="mission-hero-visual" aria-hidden="true">
        <div className="mission-orbit mission-orbit-inner" />
        <div className="mission-orbit mission-orbit-outer" />
        <div className="mission-hero-center">TI<span>↗</span></div>
        <span className="mission-visual-chip mission-chip-evidence">EVIDENCE</span>
        <span className="mission-visual-chip mission-chip-human">HUMAN REVIEW</span>
      </div>
    </section>
    <section className="mission-overview-workflow" aria-labelledby="workflow-heading">
      <div className="mission-section-line"><h2 id="workflow-heading" className="mission-kicker">THE WORKFLOW</h2><span>01 / 03</span></div>
      <ol className="mission-step-grid">{steps.map((step) => <li key={step.number}><span>{step.number}</span><h3>{step.title}</h3><p>{step.description}</p></li>)}</ol>
    </section>
    <section className="mission-overview-features" aria-labelledby="features-heading">
      <div className="mission-section-line"><h2 id="features-heading" className="mission-kicker">WHAT IT CHECKS</h2><span>{String(features.length).padStart(2, "0")} FEATURES</span></div>
      <div className="mission-checks-layout">
        <ul className="mission-check-list">{features.map((feature) => <li key={feature.tag}><span>{feature.tag}</span><div><h3>{feature.title}</h3><p>{feature.description}</p></div></li>)}</ul>
        <aside className="mission-credit-panel" aria-labelledby="credits-heading">
          <h3 id="credits-heading">How each requirement is credited</h3>
          <p>The model judges each requirement against cited evidence; the estimate itself is plain arithmetic. Confidence falls as more of the estimate rests on unknowns. These are default values, and every result needs human review.</p>
          <ol className="mission-credit-scale" aria-label="Default requirement credits">
            {credits.map((credit) => <li key={credit.label}><span className="mission-credit-label">{credit.label}<small>{credit.detail}</small></span><span className="mission-credit-bar" aria-hidden="true"><i style={{ width: `${credit.width}%` }} /></span><strong>{credit.value}</strong></li>)}
            <li><span className="mission-credit-label">Unknown<small>no evidence either way; lowers confidence</small></span><span className="mission-credit-bar mission-credit-range" aria-hidden="true"><i /></span><strong>0.5</strong></li>
          </ol>
        </aside>
      </div>
    </section>
  </>;
}
