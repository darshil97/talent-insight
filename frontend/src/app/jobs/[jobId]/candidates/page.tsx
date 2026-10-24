import type { Metadata } from "next";
import Link from "next/link";
import { CandidatePoolView } from "@/components/candidate-pool";
import { CatalogNotFound } from "@/components/catalog-resource";
import { isJobId } from "@/lib/catalog";

export const metadata: Metadata = { title: "Candidate pool", description: "Review synthetic candidate profiles for a selected demo job." };

export default async function CandidatesPage({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params;
  return (
    <>
      <Link href="/jobs" className="mb-5 inline-flex min-h-12 items-center rounded-sm text-sm font-semibold text-[#315943] underline underline-offset-4">← Back to jobs</Link>
      <p className="eyebrow">CANDIDATE PIPELINE</p>
      <h1 className="mt-3 mb-7 text-3xl font-semibold tracking-tight">Candidate pool</h1>
      {isJobId(jobId) ? <CandidatePoolView key={jobId} jobId={jobId} /> : <CatalogNotFound />}
    </>
  );
}
