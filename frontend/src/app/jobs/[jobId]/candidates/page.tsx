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
      <Link href="/jobs" className="mission-back-link">← All jobs</Link>
      {isJobId(jobId) ? <CandidatePoolView key={jobId} jobId={jobId} /> : <CatalogNotFound />}
    </>
  );
}
