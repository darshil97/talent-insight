"use client";

import Link from "next/link";
import { CatalogLoading, CatalogUnavailable, useCatalog } from "@/components/catalog-resource";
import { decodeJob, decodeJobs, type JobListItem } from "@/lib/catalog";
import { prefetchCatalog } from "@/lib/catalog-cache";

function JobCard({ job, index }: { job: JobListItem; index: number }) {
  const count = job.candidate_count;
  const warm = () => prefetchCatalog(`/jobs/${job.id}`, decodeJob);
  return <li><Link href={`/jobs/${job.id}`} onMouseEnter={warm} onFocus={warm} className="mission-job-card">
    <span className="mission-job-card-top"><small>{String(index + 1).padStart(2, "0")} / ROLE</small><span aria-hidden="true">↗</span></span>
    <span className="mission-job-content"><small>{job.client}</small><strong>{job.title}</strong><span>{job.description}</span></span>
    <span className="mission-job-card-bottom"><small>{count === null ? "Candidate pool" : `${count} synthetic ${count === 1 ? "candidate" : "candidates"}`}</small><b>View role ↗</b></span>
  </Link></li>;
}

export function JobsList() {
  const { resource, retry } = useCatalog("/jobs", decodeJobs);
  if (resource.status === "loading") return <CatalogLoading />;
  if (resource.status === "error") return <CatalogUnavailable retry={retry} />;
  const jobs = resource.data;
  return <>
    <section className="mission-jobs-heading">
      <div><p className="mission-kicker">THE CATALOG / {String(jobs.length).padStart(2, "0")} ROLES</p><h1>Explore jobs<span>.</span></h1><p>Select a role to review requirements and its candidate pool.</p></div>
      <div className="mission-jobs-count" aria-hidden="true">{String(jobs.length).padStart(2, "0")}<span>ROLES</span></div>
    </section>
    {jobs.length === 0 ? <section className="mission-empty"><h2>No jobs in the catalog yet.</h2><p>Check again later.</p><button type="button" className="mission-outline-button" onClick={retry}>Refresh jobs</button></section> :
      <ul className="mission-job-grid">{jobs.map((job, index) => <JobCard key={job.id} job={job} index={index} />)}</ul>}
  </>;
}
