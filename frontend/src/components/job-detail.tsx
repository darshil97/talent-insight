"use client";

import Link from "next/link";
import { CatalogLoading, CatalogNotFound, CatalogUnavailable, useCatalog } from "@/components/catalog-resource";
import { JobTabs } from "@/components/job-tabs";
import { decodeJob, decodeJobs, type RequirementCategory } from "@/lib/catalog";

const otherCategories: { key: RequirementCategory; label: string }[] = [
  { key: "experience", label: "Experience" },
  { key: "preferred", label: "Preferred skills" },
  { key: "qualification", label: "Qualifications" },
];

export function JobDetailView({ jobId }: { jobId: string }) {
  const { resource, retry } = useCatalog(`/jobs/${encodeURIComponent(jobId)}`, decodeJob);
  const jobs = useCatalog("/jobs", decodeJobs);
  if (resource.status === "loading") return <CatalogLoading />;
  if (resource.status === "error") return resource.notFound ? <CatalogNotFound /> : <CatalogUnavailable retry={retry} />;
  const job = resource.data;
  const candidateCount = jobs.resource.status === "ready" ? jobs.resource.data.find((row) => row.id === jobId)?.candidate_count : undefined;
  const mandatory = job.requirements.filter((row) => row.category === "mandatory");
  return <>
    <p role="status" className="sr-only">{job.title} loaded.</p>
    <section aria-labelledby="role-heading" className="mission-role-heading"><div><p className="mission-kicker">SYNTHETIC DEMO ROLE / {job.client}</p><h1 id="role-heading">{job.title}<span>.</span></h1><p>{job.description}</p></div><div className="mission-role-stamp"><small>ROLE FILE</small><strong>{job.id.replace("demo_", "").toUpperCase()}</strong><small>{candidateCount === undefined ? "CANDIDATE POOL" : `${candidateCount} DEMO PROFILES`}</small></div></section>
    <JobTabs jobId={job.id} active="details" count={candidateCount} />
    <div className="mission-details-grid">
      <section aria-labelledby="requirements-heading" className="mission-panel mission-requirements-panel">
        <div className="mission-panel-top"><p className="mission-kicker">ROLE BRIEF</p><span>01 / REQUIREMENTS</span></div>
        <h2 id="requirements-heading">What the role calls for</h2>
        {mandatory.length ? <ul>{mandatory.map((row) => <li key={row.id}><span aria-hidden="true">↗</span>{row.description}</li>)}</ul> : <p className="mission-muted">No mandatory requirements specified.</p>}
      </section>
      <aside className="mission-panel mission-workflow-panel" aria-labelledby="workflow-heading">
        <p className="mission-kicker">CANDIDATE WORKFLOW</p><h2 id="workflow-heading">Review the pool in context.</h2>
        <p>Open Candidates to compare job-related evidence and add a temporary resume for this role.</p>
        <Link href={`/jobs/${job.id}/candidates`} className="mission-button">View candidates <span aria-hidden="true">↗</span></Link>
        <ul aria-label="Job skills" className="mission-skill-cloud">{job.skills.map((skill, index) => <li key={`${skill}-${index}`}>{skill}</li>)}</ul>
      </aside>
    </div>
    <section className="mission-extra-context" aria-labelledby="more-requirements-heading">
      <p className="mission-kicker">ADDITIONAL CONTEXT</p><h2 id="more-requirements-heading">The full role brief</h2>
      <div className="mission-extra-grid">{otherCategories.map(({ key, label }) => { const items = job.requirements.filter((row) => row.category === key); return <section key={key}><h3>{label}</h3>{items.length ? <ul>{items.map((row) => <li key={row.id}>{row.description}{row.minimum_years !== null && ` · Minimum ${row.minimum_years} years`}</li>)}</ul> : <p>No requirements specified.</p>}</section>; })}</div>
      <div className="mission-extra-grid mission-questions-grid"><section><h3>Screening focus</h3><ul>{job.screening_criteria.map((criterion, index) => <li key={index}>{criterion}</li>)}</ul></section><section><h3>Questions to explore</h3><ol>{job.questions.map((question) => <li key={question.id}>{question.text}</li>)}</ol></section></div>
    </section>
    <p className="mission-review-note">Assessment evidence and scores support review of this role. People make final hiring decisions.</p>
  </>;
}
