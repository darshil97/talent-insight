import type { Metadata } from "next";
import Link from "next/link";
import { CandidateProfileView } from "@/components/candidate-profile";
import { CandidateNotFound } from "@/components/candidate-not-found";
import { CatalogNotFound } from "@/components/catalog-resource";
import { isJobId } from "@/lib/catalog";
import { isCandidateId } from "@/lib/candidates";

export const metadata: Metadata = { title: "Candidate profile", description: "Inspect a synthetic candidate's resume and traceable evidence excerpts." };

export default async function CandidatePage({ params }: { params: Promise<{ jobId: string; candidateId: string }> }) {
  const { jobId, candidateId } = await params;
  return (
    <>
      {isJobId(jobId) && <Link href={`/jobs/${jobId}/candidates`} className="mb-5 inline-flex min-h-12 items-center rounded-sm text-sm font-semibold text-[#315943] underline underline-offset-4">← Back to candidate pool</Link>}
      <p className="eyebrow">CANDIDATE PIPELINE</p>
      <h1 className="mt-3 mb-7 text-3xl font-semibold tracking-tight">Candidate profile</h1>
      {!isJobId(jobId) ? <CatalogNotFound /> : !isCandidateId(candidateId) ? <CandidateNotFound jobId={jobId} /> : <CandidateProfileView key={`${jobId}/${candidateId}`} jobId={jobId} candidateId={candidateId} />}
    </>
  );
}
