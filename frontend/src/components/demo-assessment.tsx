"use client";

import { AssessmentResult } from "@/components/assessment-result";
import { decodeAssessment } from "@/lib/assessments";
import { type JobDetail } from "@/lib/catalog";

export function DemoAssessment({ jobId, candidateId, cached, job }: { jobId: string; candidateId: string; cached: unknown; job: JobDetail }) {
  let assessment = null;
  if (cached !== null && job.id === jobId) {
    try { assessment = decodeAssessment(cached, job, "synthetic_demo", candidateId); }
    catch { assessment = null; }
  }
  return <section aria-labelledby="demo-assessment-heading" className="mt-8 min-w-0 rounded-xl border border-[#dce1d7] bg-white p-6 sm:p-7">
    <h2 id="demo-assessment-heading" className="text-xl font-semibold">Precomputed job assessment</h2>
    <p className="mt-3 text-sm leading-7 text-[#59665d]">This synthetic resume was assessed when the demo snapshot was refreshed. Review its evidence and interpretation before making any decision.</p>
    {assessment
      ? <AssessmentResult assessment={assessment} job={job} />
      : <p role="status" className="mt-4 text-sm">No current snapshot is available for this demo candidate. Refresh the demo assessments to show a score and evidence.</p>}
  </section>;
}
