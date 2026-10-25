import Link from "next/link";

const steps = [
  { number: "01", title: "Start with a role", description: "Review the requirements and the candidates attached to that job." },
  { number: "02", title: "Compare evidence", description: "Use a job-specific assessment as a starting point for human review." },
  { number: "03", title: "Continue the conversation", description: "Follow up on open questions before making a decision." },
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
  </>;
}
