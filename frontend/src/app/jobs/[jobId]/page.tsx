import type { Metadata } from "next";
import Link from "next/link";
import { JobDetailView } from "@/components/job-detail";
import { CatalogNotFound } from "@/components/catalog-resource";
import { isJobId } from "@/lib/catalog";

export const metadata: Metadata = { title: "Job details", description: "Review the requirements and screening focus for a synthetic demo role." };

export default async function JobPage({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params;
  return (
    <>
      <Link href="/jobs" className="mission-back-link">← All jobs</Link>
      {isJobId(jobId) ? <JobDetailView key={jobId} jobId={jobId} /> : <CatalogNotFound />}
    </>
  );
}
