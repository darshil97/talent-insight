"use client";

import Link from "next/link";
import { decodeCandidatePool } from "@/lib/candidates";
import { decodeJob } from "@/lib/catalog";
import { prefetchCatalog } from "@/lib/catalog-cache";

export function JobTabs({ jobId, active, count }: { jobId: string; active: "details" | "candidates"; count?: number }) {
  const warmJob = () => prefetchCatalog(`/jobs/${jobId}`, decodeJob);
  const warmPool = () => prefetchCatalog(`/jobs/${jobId}/candidates`, (value) => decodeCandidatePool(value, jobId));
  return <nav className="mission-tabs" aria-label="Job sections">
    <Link href={`/jobs/${jobId}`} onMouseEnter={warmJob} onFocus={warmJob} aria-current={active === "details" ? "page" : undefined}>Job details</Link>
    <Link href={`/jobs/${jobId}/candidates`} onMouseEnter={warmPool} onFocus={warmPool} aria-current={active === "candidates" ? "page" : undefined}>Candidates{count !== undefined && <span>{count}</span>}</Link>
  </nav>;
}
