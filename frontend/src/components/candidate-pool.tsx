"use client";

import Link from "next/link";
import { useCallback } from "react";
import { CatalogLoading, CatalogNotFound, CatalogUnavailable, useCatalog } from "@/components/catalog-resource";
import { Icon } from "@/components/icon";
import { decodeCandidatePool } from "@/lib/candidates";

export function CandidatePoolView({ jobId }: { jobId: string }) {
  const decode = useCallback((value: unknown) => decodeCandidatePool(value, jobId), [jobId]);
  const { resource, retry } = useCatalog(`/jobs/${encodeURIComponent(jobId)}/candidates`, decode);
  if (resource.status === "loading") return <CatalogLoading label="Loading the candidate pool…" />;
  if (resource.status === "error") return resource.notFound ? <CatalogNotFound /> : <CatalogUnavailable retry={retry} subject="candidate pool" />;
  const { job, candidates } = resource.data;
  return (
    <>
      <section aria-labelledby="pool-job-heading" className="mb-7 rounded-2xl border border-[#d7dfcb] bg-[#e9eedf] p-6 sm:p-8">
        <p className="eyebrow">SELECTED DEMO JOB</p>
        <h2 id="pool-job-heading" className="mt-3 text-2xl font-semibold">{job.title}</h2>
        <p className="mt-2 text-sm text-[#475a49]">{job.client}</p>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-[#475a49]">Explore the authored profiles and resume evidence in this job’s synthetic demo pool. Candidate order is alphabetical. No matching or scoring has been performed.</p>
        <Link href={`/jobs/${jobId}`} className="mt-4 inline-flex min-h-12 items-center rounded-sm text-sm font-semibold text-[#315943] underline underline-offset-4">Review job requirements</Link>
      </section>
      <p role="status" className="mb-5 text-sm text-[#59665d]">{candidates.length} synthetic {candidates.length === 1 ? "candidate" : "candidates"} in this pool</p>
      {candidates.length === 0 ? (
        <section className="rounded-xl border border-[#dce1d7] bg-white p-8">
          <h2 className="text-xl font-semibold">No demo candidates for this job yet.</h2>
          <p className="mt-3 text-sm leading-7 text-[#59665d]">This job has no candidate profiles to review. You can review its requirements or choose another role.</p>
          <button type="button" onClick={retry} className="mt-5 min-h-12 rounded-lg border border-[#9aac8b] px-5 text-sm font-medium">Refresh candidate pool</button>
        </section>
      ) : (
        <ul className="grid gap-5 xl:grid-cols-2">
          {candidates.map((candidate) => (
            <li key={candidate.id} className="flex min-w-0 flex-col rounded-xl border border-[#dce1d7] bg-white p-6 sm:p-7">
              <span className="mb-5 w-fit rounded-full bg-[#edf1e5] px-3 py-1 text-xs font-medium text-[#466344]">Synthetic demo candidate</span>
              <h2 className="text-xl font-semibold"><Link href={`/jobs/${jobId}/candidates/${candidate.id}`} className="rounded-sm underline-offset-4 hover:underline">{candidate.display_name}</Link></h2>
              <p className="mt-2 text-sm font-medium text-[#475a49]">{candidate.headline}</p>
              <p className="mt-5 text-xs font-semibold text-[#59665d]">Authored demo summary</p>
              <p className="mt-2 text-sm leading-7 text-[#59665d]">{candidate.summary}</p>
              <p className="mt-auto flex items-center gap-2 pt-6 text-xs text-[#59665d]"><Icon name="evidence" />Open the profile to inspect the source evidence</p>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
