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
      <Link href="/jobs" className="mb-5 inline-flex min-h-12 items-center rounded-sm text-sm font-semibold text-[#315943] underline underline-offset-4">← Back to jobs</Link>
      <p className="eyebrow">JOB CATALOG</p>
      <h1 className="mt-3 mb-7 text-3xl font-semibold tracking-tight">Job details</h1>
      {isJobId(jobId) ? <JobDetailView key={jobId} jobId={jobId} /> : <CatalogNotFound />}
    </>
  );
}
