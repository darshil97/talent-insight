import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "How it works",
  description: "The Talent Insight workflow for reviewing job-related evidence.",
};

const stages = [
  { number: "01 / SELECT", title: "Choose a job", description: "Read its requirements and open the Candidates tab." },
  { number: "02 / REVIEW", title: "Compare candidates", description: "Review synthetic demo profiles and their source evidence. Add a PDF to request a temporary assessment for the selected job." },
  { number: "03 / FOLLOW UP", title: "Talk to a person", description: "A later consent-aware screening flow will offer audio and text options. Keep the final decision with a human." },
] as const;

export default function Guide() {
  return <>
    <section className="mission-guide-heading"><p className="mission-kicker">HOW IT WORKS / 03 STEPS</p><h1>From role to review<span>.</span></h1><p>A simple job-specific path, with evidence visible to the person making the final decision.</p></section>
    <ol className="mission-guide-grid">{stages.map((stage) => <li key={stage.number}><span>{stage.number}</span><h2>{stage.title}</h2><p>{stage.description}</p></li>)}</ol>
    <Link href="/jobs" className="mission-button mt-9">Browse jobs <span aria-hidden="true">↗</span></Link>
    <section className="mission-extra-context" aria-labelledby="principles-heading"><p className="mission-kicker">EVIDENCE FIRST. PEOPLE ALWAYS.</p><h2 id="principles-heading">Review with care</h2><div className="mission-extra-grid"><section><h3>Job-related evidence</h3><p>Do not infer protected traits, personality or performance from names, photos or voice.</p></section><section><h3>Unknown stays unknown</h3><p>Missing resume evidence does not prove a skill is absent. Inspect the source and open questions.</p></section><section><h3>Temporary uploads</h3><p>PDF assessments clear on refresh or navigation. Use documents you have permission to process.</p></section></div></section>
  </>;
}
