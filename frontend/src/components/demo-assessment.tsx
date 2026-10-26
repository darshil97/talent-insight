"use client";

import { AssessmentResult } from "@/components/assessment-result";
import { CatalogUnavailable, useCatalog } from "@/components/catalog-resource";
import { decodeAssessment } from "@/lib/assessments";
import { decodeJob } from "@/lib/catalog";

export function DemoAssessment({ jobId, candidateId, cached }: { jobId: string; candidateId: string; cached: unknown }) {
  const { resource, retry } = useCatalog(`/jobs/${encodeURIComponent(jobId)}`, decodeJob);
  let assessment = null;
  if (resource.status === "ready" && cached !== null) {
    try { assessment = decodeAssessment(cached, resource.data, "synthetic_demo", candidateId); }
    catch { assessment = null; }
  }
  return <section aria-labelledby="demo-assessment-heading" className="mt-8 min-w-0 rounded-xl border border-[#dce1d7] bg-white p-6 sm:p-7">
    <h2 id="demo-assessment-heading" className="text-xl font-semibold">Precomputed job assessment</h2>
    <p className="mt-3 text-sm leading-7 text-[#59665d]">This synthetic resume was assessed when the demo snapshot was refreshed. Review its evidence and interpretation before making any decision.</p>
    {resource.status === "loading" && <p role="status" className="mt-4 text-sm">Loading job requirements…</p>}
    {resource.status === "error" && <div className="mt-4"><CatalogUnavailable retry={retry} subject="job requirements" /></div>}
    {resource.status === "ready" && (assessment
      ? <AssessmentResult assessment={assessment} job={resource.data} />
      : <p role="status" className="mt-4 text-sm">No current snapshot is available for this demo candidate. Refresh the demo assessments to show a score and evidence.</p>)}
  </section>;
}
