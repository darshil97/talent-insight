"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AssessmentResult } from "@/components/assessment-result";
import { CatalogUnavailable, useCatalog } from "@/components/catalog-resource";
import { assessDemo, AssessmentError, type Assessment } from "@/lib/assessments";
import { decodeJob } from "@/lib/catalog";

export function DemoAssessment({ jobId, candidateId }: { jobId: string; candidateId: string }) {
  const { resource, retry } = useCatalog(`/jobs/${encodeURIComponent(jobId)}`, decodeJob);
  const [result, setResult] = useState<Assessment | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  const discard = useCallback(() => { request.current?.abort(); setResult(null); setBusy(false); setError(""); }, []);

  useEffect(() => {
    window.addEventListener("pagehide", discard);
    function restored(event: PageTransitionEvent) { if (event.persisted) discard(); }
    window.addEventListener("pageshow", restored);
    return () => { request.current?.abort(); window.removeEventListener("pagehide", discard); window.removeEventListener("pageshow", restored); };
  }, [discard]);

  async function assess() {
    if (resource.status !== "ready") return;
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setResult(null); setError(""); setBusy(true);
    try {
      const data = await assessDemo(resource.data, candidateId, controller.signal);
      if (!controller.signal.aborted) setResult(data);
    } catch (failure) {
      if (!controller.signal.aborted) setError(failure instanceof AssessmentError ? failure.message : "Assessment could not be completed. Check the connection and try again.");
    } finally { if (!controller.signal.aborted) setBusy(false); }
  }

  return <section aria-labelledby="demo-assessment-heading" className="mt-8 min-w-0 rounded-xl border border-[#dce1d7] bg-white p-6 sm:p-7">
    <h2 id="demo-assessment-heading" className="text-xl font-semibold">Assess this synthetic candidate</h2>
    <p className="mt-3 text-sm leading-7 text-[#59665d]">Compare the authored demo resume with this job. In Bedrock mode, its text is sent to the configured AI provider. The backend verifies citations and calculates the rubric; a person must review the interpretation.</p>
    {resource.status === "loading" && <p role="status" className="mt-4 text-sm">Loading job requirements…</p>}
    {resource.status === "error" && <div className="mt-4"><CatalogUnavailable retry={retry} subject="job requirements" /></div>}
    <div className="mt-5 flex flex-wrap gap-3">
      <button type="button" onClick={assess} disabled={busy || resource.status !== "ready"} className="min-h-12 rounded-lg bg-[#203e31] px-5 py-3 text-sm font-medium text-white enabled:hover:bg-[#315943] disabled:opacity-50">{busy ? "Assessing candidate…" : "Assess candidate"}</button>
      <button type="button" onClick={discard} className="min-h-12 rounded-lg border border-[#cbd3c3] px-5 py-3 text-sm font-medium hover:bg-[#f1f4ec]">{busy ? "Cancel and clear" : "Clear"}</button>
    </div>
    <p role="status" className="mt-3 text-sm text-[#59665d]">{busy ? "Assessing the demo resume. You can cancel and clear at any time." : result ? "Assessment ready for human review." : ""}</p>
    {error && <p role="alert" className="mt-3 rounded-lg border border-[#dfc7bc] bg-[#fff7f2] p-4 text-sm leading-6 text-[#793d29]">{error}</p>}
    {result && resource.status === "ready" && <AssessmentResult assessment={result} job={resource.data} />}
  </section>;
}
